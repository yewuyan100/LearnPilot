"""Run the frozen 72-case Real-world Gold V1 through production-equivalent RAG."""

from __future__ import annotations

from argparse import ArgumentParser
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import platform
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import time
from typing import Any, Iterator
from uuid import uuid4

import faiss
import httpx

from dense_baseline_metrics import build_artifacts


ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
V1 = HERE.parent
BACKEND = ROOT / "backend"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
ALEMBIC = ROOT / ".venv" / "Scripts" / "alembic.exe"
CORPUS_MANIFEST = V1 / "corpus_manifest.json"
GOLD_DIR = V1 / "gold" / "v1"
GOLD_PATH = GOLD_DIR / "gold_cases.json"
FREEZE_MANIFEST = GOLD_DIR / "gold_dataset_v1_freeze_manifest.json"
ANCHORS_PATH = GOLD_DIR / "evidence_anchors.json"
RESULTS_ROOT = V1 / "results" / "dense_only_baseline_v1"
ROOT_REPORT = V1 / "RAG_REAL_WORLD_DENSE_ONLY_BASELINE_V1_REPORT.md"

EXPECTED = {
    "corpus_manifest_sha256": "6f67d510cd35197f107400d33033972c0c3c84478174e4991e491f6c8e4ab563",
    "gold_sha256": "33a0b69901fa47e3fe45be0277228cd4a5519fe780fe5b9d2c52b1bfe614927a",
    "freeze_manifest_sha256": "d979079be4eb901a825ab29414dd7b5124d030182e09b55eea1e93749c12a5c2",
}
MIME_TYPES = {"md": "text/markdown", "txt": "text/plain", "pdf": "application/pdf"}
PRODUCTION_CODE = (
    BACKEND / "app/api/routes/materials.py",
    BACKEND / "app/api/routes/rag.py",
    BACKEND / "app/core/config.py",
    BACKEND / "app/services/material_processing/pipeline.py",
    BACKEND / "app/services/material_processing/chunking.py",
    BACKEND / "app/services/vector_store/service.py",
    BACKEND / "app/services/vector_store/faiss_store.py",
    BACKEND / "app/services/embedding/bge_m3.py",
    BACKEND / "app/services/rag/query_rewriter.py",
    BACKEND / "app/services/rag/retrieval.py",
    BACKEND / "app/services/rag/grounding.py",
    BACKEND / "app/services/rag/prompts.py",
    BACKEND / "app/services/rag/validation.py",
    BACKEND / "app/services/rag/service.py",
    BACKEND / "app/services/llm/openai_compatible.py",
)
PRODUCTION_STATE = (
    BACKEND / "data" / "personal_learning.sqlite3",
    BACKEND / "data" / "materials.faiss",
    BACKEND / "data" / "materials.faiss.manifest.json",
    BACKEND / "data" / "agent_checkpoints.sqlite",
    ROOT / "data" / "agent_checkpoints.sqlite",
    BACKEND / "uploads",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, value: Any) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


def relative(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def snapshot(paths: tuple[Path, ...] | list[Path], *, exclude_cache: bool = True) -> dict[str, Any]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(item for item in path.rglob("*") if item.is_file())
        else:
            files.append(path)
    if exclude_cache:
        files = [item for item in files if "__pycache__" not in item.parts and item.suffix != ".pyc"]
    return {
        str(path.resolve()): {
            "exists": path.is_file(),
            "size": path.stat().st_size if path.is_file() else None,
            "mtime_ns": path.stat().st_mtime_ns if path.is_file() else None,
            "sha256": file_hash(path) if path.is_file() else None,
        }
        for path in sorted(set(files))
    }


def identities() -> dict[str, Any]:
    actual = {
        "corpus_manifest_sha256": file_hash(CORPUS_MANIFEST),
        "gold_sha256": file_hash(GOLD_PATH),
        "freeze_manifest_sha256": file_hash(FREEZE_MANIFEST),
    }
    return {"expected": EXPECTED, "actual": actual, "all_match": actual == EXPECTED}


def environment_for(runtime_dir: Path, telemetry_path: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "DATABASE_URL": f"sqlite:///{(runtime_dir / 'evaluation.sqlite3').as_posix()}",
            "UPLOAD_DIR": str(runtime_dir / "uploads"),
            "FAISS_INDEX_PATH": str(runtime_dir / "materials.faiss"),
            "FAISS_MANIFEST_PATH": str(runtime_dir / "materials.faiss.manifest.json"),
            "AGENT_CHECKPOINT_DB_PATH": str(runtime_dir / "agent_checkpoints.sqlite"),
            "DEMO_DATA_ENABLED": "false",
            "EMBEDDING_LOCAL_FILES_ONLY": "true",
            "RAG_BASELINE_TELEMETRY_PATH": str(telemetry_path),
            "PYTHONPATH": os.pathsep.join(
                [str(HERE), str(BACKEND), environment.get("PYTHONPATH", "")]
            ).rstrip(os.pathsep),
        }
    )
    return environment


def wait_ready(base_url: str, process: subprocess.Popen[str], log_path: Path) -> None:
    deadline = time.monotonic() + 240
    last_error = ""
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        try:
            response = httpx.get(f"{base_url}/health", timeout=2)
            if response.status_code == 200:
                return
            last_error = response.text[:300]
        except httpx.HTTPError as exc:
            last_error = type(exc).__name__
        time.sleep(0.25)
    tail = ""
    if log_path.is_file():
        tail = "\n".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-50:])
    raise RuntimeError(f"isolated backend failed to start: {last_error}\n{tail}")


@contextmanager
def live_backend(port: int, environment: dict[str, str], log_path: Path) -> Iterator[str]:
    with log_path.open("a", encoding="utf-8") as log_handle:
        process = subprocess.Popen(
            [str(PYTHON), "-m", "uvicorn", "instrumented_app:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=BACKEND,
            env=environment,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        base_url = f"http://127.0.0.1:{port}/api"
        try:
            wait_ready(base_url, process, log_path)
            yield base_url
        finally:
            process.terminate()
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


def request(client: httpx.Client, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = client.request(method, url, **kwargs)
        elapsed = round((time.perf_counter() - started) * 1000, 2)
        try:
            body: Any = response.json()
        except ValueError:
            body = response.text[:2000]
        return {"status_code": response.status_code, "elapsed_ms": elapsed, "body": body}
    except Exception as exc:
        return {
            "status_code": 0,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            "body": {"error_type": type(exc).__name__, "message": str(exc)},
        }


def require(result: dict[str, Any], expected: int, label: str) -> Any:
    if result["status_code"] != expected:
        raise RuntimeError(f"{label} returned {result['status_code']}: {result['body']}")
    return result["body"]


def trace_offset(path: Path) -> int:
    return path.stat().st_size if path.is_file() else 0


def trace_since(path: Path, offset: int) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    with path.open("rb") as handle:
        handle.seek(offset)
        return [json.loads(line) for line in handle.read().decode("utf-8").splitlines() if line.strip()]


def normalize(value: str) -> str:
    return " ".join(value.split())


def substantial_overlap(left: str, right: str) -> bool:
    a, b = normalize(left), normalize(right)
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    max_width = min(240, len(a), len(b))
    for width in range(max_width, 59, -1):
        if a[-width:] == b[:width] or b[-width:] == a[:width]:
            return True
    return False


def reconstruct_selection(candidates: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    ranked = sorted(candidates, key=lambda item: (-item["score"], item["material_id"], item["chunk_index"], item["chunk_id"]))
    above = [item for item in ranked if item["score"] >= config["rag_min_score"]]
    threshold_rejected = [item["chunk_id"] for item in ranked if item not in above]
    unique = []
    dedup_rejected = []
    for item in above:
        if any(
            prior["material_id"] == item["material_id"]
            and abs(prior["chunk_index"] - item["chunk_index"]) <= 1
            and substantial_overlap(prior["content"], item["content"])
            for prior in unique
        ):
            dedup_rejected.append(item["chunk_id"])
        else:
            unique.append(item)
    limit = min(config["rag_top_k_default"], config["rag_max_sources"])
    per_material_cap = max(1, math.ceil(config["rag_max_sources"] / 2))
    selected = []
    counts: dict[int, int] = {}
    diversity_deferred = []
    for item in unique:
        if counts.get(item["material_id"], 0) >= per_material_cap:
            diversity_deferred.append(item["chunk_id"])
            continue
        selected.append(item)
        counts[item["material_id"]] = counts.get(item["material_id"], 0) + 1
        if len(selected) >= limit:
            break
    diversity_first_pass = [item["chunk_id"] for item in selected]
    if len(selected) < limit:
        for item in unique:
            if item in selected:
                continue
            selected.append(item)
            if len(selected) >= limit:
                break
    before_budget = [item["chunk_id"] for item in selected]
    context_chars = 0
    budget_rows = []
    for item in selected:
        content = item["content"][: config["rag_max_chunk_chars"]]
        remaining = config["rag_max_context_chars"] - context_chars
        if remaining <= 0:
            break
        content = content[:remaining]
        if not content.strip():
            continue
        budget_rows.append({**item, "content": content, "context_chars": len(content)})
        context_chars += len(content)
    return {
        "candidate_count": len(ranked),
        "ranked_chunk_ids": [item["chunk_id"] for item in ranked],
        "threshold": config["rag_min_score"],
        "above_threshold_chunk_ids": [item["chunk_id"] for item in above],
        "threshold_rejected_chunk_ids": threshold_rejected,
        "deduplicated_chunk_ids": [item["chunk_id"] for item in unique],
        "dedup_rejected_chunk_ids": dedup_rejected,
        "per_material_cap": per_material_cap,
        "diversity_first_pass_chunk_ids": diversity_first_pass,
        "diversity_deferred_chunk_ids": diversity_deferred,
        "selected_before_context_budget_chunk_ids": before_budget,
        "selected_after_context_budget_chunk_ids": [item["chunk_id"] for item in budget_rows],
        "context_character_count": context_chars,
    }


def anchor_material(anchors: dict[str, Any]) -> dict[str, str]:
    texts = {}
    for anchor in anchors["anchors"]:
        locator = anchor["locator"]
        if locator["kind"] != "SOURCE_LINES":
            continue
        lines = (ROOT / locator["source_path"]).read_text(encoding="utf-8").splitlines()
        texts[anchor["evidence_id"]] = "\n".join(
            normalize(line) for line in lines[locator["start_line"] - 1 : locator["end_line"]]
        )
    return texts


def annotate_source(
    source: dict[str, Any], filename_map: dict[str, str], anchors: dict[str, Any], anchor_texts: dict[str, str]
) -> dict[str, Any]:
    document_id = filename_map.get(source.get("original_filename", ""))
    content = normalize(source.get("content") or source.get("content_excerpt") or "")
    evidence_ids = []
    for anchor in anchors["anchors"]:
        if anchor["document_id"] != document_id:
            continue
        locator = anchor["locator"]
        matched = False
        if locator["kind"] == "PDF_PAGE":
            matched = source.get("page_number") == locator["page_number"]
        else:
            anchor_material_text = anchor_texts[anchor["evidence_id"]]
            anchor_text = normalize(anchor_material_text)
            if len(content) >= 60 and (content in anchor_text or anchor_text in content):
                matched = True
            elif content:
                source_lines = anchor_material_text.splitlines()
                matched = any(len(line) >= 60 and line in content for line in source_lines)
        if matched:
            evidence_ids.append(anchor["evidence_id"])
    return {**source, "document_id": document_id, "evidence_ids": sorted(evidence_ids)}


def sqlite_audit(database: Path, filename_map: dict[str, str]) -> dict[str, Any]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    tables = ("materials", "material_chunks", "rag_conversations", "rag_messages", "rag_citations")
    counts = {table: connection.execute(f"select count(*) from {table}").fetchone()[0] for table in tables}
    messages = [dict(row) for row in connection.execute(
        "select request_id,input_tokens,output_tokens,answerable,refusal_reason,status from rag_messages where role='assistant' order by id"
    )]
    connection.close()
    return {
        "counts": counts,
        "assistant_messages": messages,
        "all_case_run_ids_unique": len({item["request_id"] for item in messages}) == len(messages),
        "filename_document_map": filename_map,
    }


def package_versions() -> dict[str, str]:
    script = (
        "import fastapi,pydantic,sqlalchemy,numpy,faiss,sentence_transformers,httpx,json;"
        "print(json.dumps({'fastapi':fastapi.__version__,'pydantic':pydantic.__version__,"
        "'sqlalchemy':sqlalchemy.__version__,'numpy':numpy.__version__,'faiss':faiss.__version__,"
        "'sentence_transformers':sentence_transformers.__version__,'httpx':httpx.__version__}))"
    )
    output = subprocess.run([str(PYTHON), "-c", script], check=True, capture_output=True, text=True).stdout
    return json.loads(output)


def render_root_report(run_dir: Path, raw: dict[str, Any], metrics: dict[str, Any], validation: dict[str, Any]) -> str:
    r, c = metrics["retrieval_metrics"], metrics["claim_metrics"]
    ci, a, l = metrics["citation_metrics"], metrics["answerability_metrics"], metrics["latency_metrics"]
    return f"""# LearnPilot RAG — Real-world Dense-only Baseline V1

## Outcome

`RAG_REAL_WORLD_DENSE_ONLY_BASELINE_V1 = {validation['terminal_status']}`

The frozen 72-case Gold V1 was executed exactly once per case through the current
production-equivalent dense-only path: BGE-M3, FAISS `IndexFlatIP`, current threshold /
deduplication / diversity / context-budget rules, DeepSeek grounded generation, and
deterministic citation rendering. No retrieval, prompt, chunking, model, Gold, Corpus,
or production-code optimization was made.

## Frozen bindings

- Corpus: `learnpilot-rag-real-world-corpus@v1` — `{EXPECTED['corpus_manifest_sha256']}`
- Gold: `learnpilot-rag-real-world-gold-v1` — `{EXPECTED['gold_sha256']}`
- Freeze manifest: `{EXPECTED['freeze_manifest_sha256']}`
- Model: `{raw['effective_configuration']['structured_model']}` at `{raw['effective_configuration']['host']}`
- Embedding: `{raw['effective_configuration']['embedding_model']}` / `{raw['effective_configuration']['embedding_revision']}`
- Prompt: `{raw['effective_configuration']['rag_prompt_version']}`
- Run: `{raw['run_id']}`

## Machine-computable baseline

- Candidate required-document group pass: `{r['candidate_document_group_pass_count']}/{r['case_count']}`
- Selected required-document group pass: `{r['selected_document_group_pass_count']}/{r['case_count']}`
- Selected diagnostic-anchor group pass: `{r['selected_anchor_group_pass_count']}/{r['case_count']}`
- Deterministic exact / answerability claim pass: `{c['deterministic_pass_count']}/{c['deterministic_claim_count']}`
- Semantic claims queued for review: `{c['semantic_review_claim_count']}`; no lexical correctness proxy
- Citation machine-contract pass: `{ci['machine_contract_pass_count']}/{ci['case_count']}`
- Answerability accuracy: `{a['accuracy_count']}/{a['case_count']}`
- Ask latency p50 / p95: `{l['ask_http_ms']['median']} / {l['ask_http_ms']['p95']} ms`
- Tokens: `{l['tokens']['total']}`

## Evidence and boundaries

Raw model drafts were frozen before metrics in `{relative(run_dir / 'raw_results.json')}` and
bound by `{relative(run_dir / 'raw_results.sha256')}`. Candidate and selected-context metrics
follow Gold V2 OR-within / AND-across evidence-group semantics. Anchor-level chunk mapping is
reported as a diagnostic layer; document-level coverage is the stable primary retrieval layer.
Semantic correctness and citation support remain `REVIEW_REQUIRED` where deterministic modes do
not apply. Failure traces contain preliminary signals only and deliberately do not classify root
causes. The next authorized stage is failure analysis, not optimization.

## Isolation and immutability

Only the frozen 11 project-owned documents, 72 questions, and their selected corpus fragments
were in scope. Runtime SQLite, uploads, FAISS, and checkpoint storage were isolated and removed
after audit. No credential, environment dump, personal knowledge-base content, production
database content, or unrelated repository file is present in artifacts. Gold, Corpus, freeze
manifest, production RAG code, and production runtime state matched before/after snapshots.
"""


def main() -> int:
    parser = ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=RESULTS_ROOT)
    parser.add_argument("--port", type=int)
    args = parser.parse_args()

    pre_identities = identities()
    if not pre_identities["all_match"]:
        raise RuntimeError(f"frozen identity mismatch: {pre_identities}")
    freeze_check = subprocess.run(
        [str(PYTHON), str(GOLD_DIR / "final_freeze_v1.py"), "verify"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if freeze_check.returncode != 0:
        raise RuntimeError(f"final freeze preflight failed:\n{freeze_check.stdout}\n{freeze_check.stderr}")

    corpus = json.loads(CORPUS_MANIFEST.read_text(encoding="utf-8"))
    gold = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
    anchors = json.loads(ANCHORS_PATH.read_text(encoding="utf-8"))
    if corpus["document_count"] != 11 or gold["case_count"] != 72 or len(gold["cases"]) != 72:
        raise RuntimeError("frozen counts are not 11 documents / 72 cases")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    run_dir = args.output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    telemetry_path = run_dir / "telemetry.jsonl"
    checkpoint_path = run_dir / "case_checkpoints.jsonl"
    runtime_parent = Path(tempfile.mkdtemp(prefix="learnpilot-rag-real-world-dense-v1-"))
    runtime_dir = runtime_parent / "runtime"
    runtime_dir.mkdir()
    environment = environment_for(runtime_dir, telemetry_path)
    production_before = snapshot(list(PRODUCTION_STATE))
    protected_before = snapshot([CORPUS_MANIFEST, V1 / "corpus", GOLD_DIR])
    code_before = snapshot(list(PRODUCTION_CODE))
    imports = []
    case_records = []
    config: dict[str, Any] = {}
    index_status: dict[str, Any] = {}
    started_at = utc_now()

    try:
        write_json(
            run_dir / "preflight.json",
            {
                "at": started_at,
                "freeze_verifier_command": "final_freeze_v1.py verify",
                "freeze_verifier_returncode": freeze_check.returncode,
                "freeze_verifier_stdout": freeze_check.stdout,
                "identities": pre_identities,
                "authorized_external_scope": "72 frozen questions plus production-retrieved project-owned frozen-corpus context only",
                "production_code_sha256": {relative(path): file_hash(path) for path in PRODUCTION_CODE},
            },
        )
        migration = subprocess.run(
            [str(ALEMBIC), "upgrade", "head"], cwd=BACKEND, env=environment, capture_output=True, text=True
        )
        if migration.returncode != 0:
            raise RuntimeError(f"isolated migration failed: {migration.stderr}")

        port = args.port or available_port()
        with live_backend(port, environment, run_dir / "backend.log") as base_url:
            with httpx.Client(base_url=base_url, timeout=420) as client:
                config = require(request(client, "GET", "/eval/dense-baseline-config"), 200, "effective config")
                if not config["llm_configured"] or config["host"] != "api.deepseek.com" or config["structured_model"] != "deepseek-v4-flash":
                    raise RuntimeError(f"unexpected answer provider binding: {config}")
                if config["embedding_model"] != "BAAI/bge-m3" or not config["embedding_local_files_only"]:
                    raise RuntimeError(f"unexpected embedding binding: {config}")
                if config["rag_top_k_default"] != 6 or config["rag_min_score"] != 0.35:
                    raise RuntimeError(f"unexpected production retrieval binding: {config}")

                filename_map: dict[str, str] = {}
                material_map: dict[str, int] = {}
                for position, document in enumerate(corpus["documents"], 1):
                    source_path = ROOT / document["repository_path"]
                    actual_hash = file_hash(source_path)
                    if actual_hash != document["corpus_sha256"]:
                        raise RuntimeError(f"corpus document hash mismatch: {document['document_id']}")
                    upload_call = request(
                        client,
                        "POST",
                        "/materials/upload",
                        files={"file": (source_path.name, source_path.read_bytes(), MIME_TYPES[document["source_format"]])},
                    )
                    uploaded = require(upload_call, 201, f"upload {document['document_id']}")
                    process_call = request(client, "POST", f"/materials/{uploaded['id']}/process")
                    processed = require(process_call, 200, f"process {document['document_id']}")
                    chunks = require(
                        request(client, "GET", f"/materials/{uploaded['id']}/chunks", params={"page": 1, "page_size": 100}),
                        200,
                        f"chunks {document['document_id']}",
                    )
                    total = chunks["total"]
                    filename_map[source_path.name] = document["document_id"]
                    material_map[document["document_id"]] = uploaded["id"]
                    imports.append(
                        {
                            "position": position,
                            "document_id": document["document_id"],
                            "original_filename": source_path.name,
                            "source_sha256": actual_hash,
                            "material_id": uploaded["id"],
                            "upload_status": upload_call["status_code"],
                            "upload_elapsed_ms": upload_call["elapsed_ms"],
                            "process_status": process_call["status_code"],
                            "process_elapsed_ms": process_call["elapsed_ms"],
                            "ingestion_status": processed["ingestion_status"],
                            "indexing_status": processed["indexing_status"],
                            "chunk_count": total,
                        }
                    )
                    print(f"INGEST {position:02d}/11 {document['document_id']} chunks={total}", flush=True)
                write_json(run_dir / "imports.json", imports)
                if sum(item["chunk_count"] for item in imports) != 442:
                    raise RuntimeError(f"installed chunk count mismatch: {sum(item['chunk_count'] for item in imports)}")
                index_status = require(request(client, "GET", "/materials/index/status"), 200, "index status")
                local_index = faiss.read_index(str(runtime_dir / "materials.faiss"))
                index_binding = {
                    "faiss_type": type(local_index).__name__,
                    "ntotal": int(local_index.ntotal),
                    "dimension": int(local_index.d),
                    "status": index_status,
                }
                write_json(run_dir / "index_binding.json", index_binding)
                if index_binding["faiss_type"] != "IndexFlatIP" or index_binding["ntotal"] != 442:
                    raise RuntimeError(f"unexpected FAISS binding: {index_binding}")

                anchor_texts = anchor_material(anchors)
                for sequence, case in enumerate(gold["cases"], 1):
                    case_run_id = f"rwbase-{run_id[-8:]}-{sequence:03d}-{sha256(case['case_id'].encode()).hexdigest()[:10]}"
                    diag_offset = trace_offset(telemetry_path)
                    diagnostic_call = request(
                        client,
                        "POST",
                        "/materials/search",
                        json={"query": case["question"], "top_k": 18},
                    )
                    diagnostic = require(diagnostic_call, 200, f"diagnostic {case['case_id']}")
                    diagnostic_events = trace_since(telemetry_path, diag_offset)
                    candidates = [
                        annotate_source(item, filename_map, anchors, anchor_texts)
                        for item in diagnostic["results"]
                    ]
                    reconstructed = reconstruct_selection(candidates, config)

                    conversation_call = request(
                        client,
                        "POST",
                        "/rag/conversations",
                        json={"title": f"baseline:{case['case_id']}", "default_top_k": 6},
                    )
                    conversation = require(conversation_call, 201, f"conversation {case['case_id']}")
                    ask_offset = trace_offset(telemetry_path)
                    ask_call = request(
                        client,
                        "POST",
                        f"/rag/conversations/{conversation['id']}/ask",
                        json={"question": case["question"], "request_id": case_run_id, "top_k": 6},
                    )
                    response = require(ask_call, 200, f"ask {case['case_id']}")
                    ask_events = trace_since(telemetry_path, ask_offset)
                    retrieval_events = [item for item in ask_events if item["event"] == "rag.retrieval.completed"]
                    if len(retrieval_events) != 1:
                        raise RuntimeError(f"missing/duplicate retrieval telemetry for {case['case_id']}: {len(retrieval_events)}")
                    retrieval = retrieval_events[0]
                    selected = [
                        annotate_source(item, filename_map, anchors, anchor_texts)
                        for item in retrieval["selected_sources"]
                    ]
                    telemetry_chunk_ids = [item["chunk_id"] for item in selected]
                    reconstruction_match = telemetry_chunk_ids == reconstructed["selected_after_context_budget_chunk_ids"]
                    if not reconstruction_match:
                        raise RuntimeError(
                            f"selection reconstruction mismatch {case['case_id']}: {telemetry_chunk_ids} != "
                            f"{reconstructed['selected_after_context_budget_chunk_ids']}"
                        )
                    rewrite_events = [item for item in ask_events if item["event"] == "rag.rewrite.completed"]
                    if len(rewrite_events) != 1 or rewrite_events[0]["retrieval_query"] != case["question"]:
                        raise RuntimeError(f"fresh-conversation rewrite binding mismatch: {case['case_id']}")
                    selected_by_label = {item["source_label"]: item for item in selected}
                    citations = []
                    for citation in response["assistant_message"].get("citations", []):
                        source = selected_by_label.get(citation["source_label"], {})
                        citations.append(
                            {
                                **citation,
                                "document_id": filename_map.get(citation["original_filename"]),
                                "evidence_ids": source.get("evidence_ids", []),
                            }
                        )
                    completed_llm = [item for item in ask_events if item["event"] == "llm.structured.completed"]
                    raw_drafts = [item for item in ask_events if item["event"] == "llm.raw_draft.received"]
                    transport = [item for item in ask_events if item["event"].startswith("llm.transport.")]
                    transport_completed = [
                        item for item in transport if item["event"] == "llm.transport.completed"
                    ]
                    usage = {
                        "input_tokens": sum((item.get("usage", {}).get("input_tokens") or 0) for item in transport_completed),
                        "output_tokens": sum((item.get("usage", {}).get("output_tokens") or 0) for item in transport_completed),
                        "total_tokens": sum((item.get("usage", {}).get("total_tokens") or 0) for item in transport_completed),
                    }
                    embedding_events = [
                        item for item in ask_events if item["event"] == "embedding.query.completed"
                    ]
                    generation_events = [
                        item
                        for item in ask_events
                        if item["event"] in {"llm.structured.completed", "llm.structured.error"}
                    ]
                    started_calls = sum(item["event"] == "llm.structured.started" for item in ask_events)
                    record = {
                        "sequence": sequence,
                        "case_run_id": case_run_id,
                        "case_id": case["case_id"],
                        "execution_status": "COMPLETED",
                        "executed_at": utc_now(),
                        "gold_case": case,
                        "diagnostic": {
                            "query": diagnostic["query"],
                            "candidate_limit": 18,
                            "index_version": diagnostic["index_version"],
                            "retrieved_count": diagnostic["retrieved_count"],
                            "filtered_count": diagnostic["filtered_count"],
                            "duration_ms": diagnostic["duration_ms"],
                            "candidates": candidates,
                            "events": diagnostic_events,
                        },
                        "selection_stage_trace": reconstructed,
                        "retrieval": {
                            **{key: value for key, value in retrieval.items() if key not in {"event", "at", "selected_sources"}},
                            "selected_sources": selected,
                            "reconstruction_matches_production_telemetry": reconstruction_match,
                        },
                        "generation": {
                            "events": [item for item in ask_events if item["event"].startswith("llm.")],
                            "raw_model_drafts": raw_drafts,
                            "parsed_model_drafts": completed_llm,
                            "structured_call_count": started_calls,
                            "repair_attempted": started_calls > 1,
                            "transport_attempt_count": len(transport),
                            "provider_retry_count": max(0, len(transport) - started_calls),
                            "errors": [item for item in ask_events if item["event"].endswith(".error")],
                            "aggregate_usage": usage,
                        },
                        "response": response,
                        "normalized_answer": response["assistant_message"]["content"],
                        "citations": citations,
                        "latency": {
                            "diagnostic_http_ms": diagnostic_call["elapsed_ms"],
                            "conversation_http_ms": conversation_call["elapsed_ms"],
                            "ask_http_ms": ask_call["elapsed_ms"],
                            "rewrite_ms": rewrite_events[0]["elapsed_ms"],
                            "embedding_query_ms": sum(item["elapsed_ms"] for item in embedding_events),
                            "retrieval_production_ms": retrieval["duration_ms"],
                            "retrieval_observed_ms": retrieval["observed_latency_ms"],
                            "selection_observed_ms": round(
                                max(0, retrieval["observed_latency_ms"] - retrieval["duration_ms"]), 2
                            ),
                            "generation_observed_ms": round(
                                sum(
                                    item.get("observed_latency_ms", item.get("elapsed_ms", 0))
                                    for item in generation_events
                                ),
                                2,
                            ),
                        },
                        "retry_and_error_summary": {
                            "provider_retries": max(0, len(transport) - started_calls),
                            "repair_attempted": started_calls > 1,
                            "error_count": sum(item["event"].endswith(".error") for item in ask_events),
                        },
                    }
                    case_records.append(record)
                    append_jsonl(checkpoint_path, record)
                    print(
                        f"CASE {sequence:02d}/72 {case['case_id']} answerable={response['assistant_message']['answerable']} "
                        f"sources={len(selected)} citations={len(citations)} ms={ask_call['elapsed_ms']}",
                        flush=True,
                    )

                persistence = sqlite_audit(runtime_dir / "evaluation.sqlite3", filename_map)
                write_json(run_dir / "persistence_audit.json", persistence)

        completed_at = utc_now()
        raw = {
            "schema_version": "1.0.0",
            "run_id": run_id,
            "baseline_id": "learnpilot-rag-real-world-dense-only-baseline-v1",
            "started_at": started_at,
            "completed_at": completed_at,
            "frozen_bindings": pre_identities,
            "effective_configuration": config,
            "index_binding": {
                "type": "IndexFlatIP",
                "chunk_count": 442,
                "index_version": index_status.get("index_version"),
                "embedding_dimension": index_status.get("embedding_dimension"),
            },
            "production_code_sha256": {relative(path): file_hash(path) for path in PRODUCTION_CODE},
            "instrumentation_sha256": file_hash(HERE / "instrumented_app.py"),
            "metrics_code_sha256": file_hash(HERE / "dense_baseline_metrics.py"),
            "runner_code_sha256": file_hash(Path(__file__)),
            "runtime": {"python": platform.python_version(), "platform": platform.platform(), "packages": package_versions()},
            "execution_contract": {
                "case_count": 72,
                "case_execution_semantics": "exactly_once",
                "fresh_conversation_per_case": True,
                "diagnostic_candidate_limit": 18,
                "production_ask_top_k": 6,
                "semantic_machine_judging": False,
            },
            "imports": imports,
            "cases": case_records,
        }
        raw_path = run_dir / "raw_results.json"
        write_json(raw_path, raw)
        raw_sha = file_hash(raw_path)
        (run_dir / "raw_results.sha256").write_text(f"{raw_sha}  raw_results.json\n", encoding="utf-8")

        metrics = build_artifacts(raw_path, run_dir)
        post_identities = identities()
        production_after = snapshot(list(PRODUCTION_STATE))
        protected_after = snapshot([CORPUS_MANIFEST, V1 / "corpus", GOLD_DIR])
        code_after = snapshot(list(PRODUCTION_CODE))
        validation = {
            "run_id": run_id,
            "case_count": len(case_records),
            "unique_case_run_ids": len({item["case_run_id"] for item in case_records}),
            "unique_case_ids": len({item["case_id"] for item in case_records}),
            "all_completed": all(item["execution_status"] == "COMPLETED" for item in case_records),
            "raw_results_sha256": raw_sha,
            "raw_hash_reverified_after_metrics": file_hash(raw_path) == raw_sha,
            "pre_post_frozen_identity_match": pre_identities == post_identities and post_identities["all_match"],
            "protected_corpus_gold_freeze_unchanged": protected_before == protected_after,
            "production_code_unchanged": code_before == code_after,
            "production_runtime_state_unchanged": production_before == production_after,
            "selection_reconstruction_all_match": all(
                item["retrieval"]["reconstruction_matches_production_telemetry"] for item in case_records
            ),
            "external_answer_model_call_scope": "frozen questions and selected frozen-corpus context only",
            "semantic_review_not_machine_approximated": metrics["claim_metrics"]["semantic_machine_pass_rate"] is None,
        }
        validation["terminal_status"] = "COMPLETE" if all(
            [
                validation["case_count"] == 72,
                validation["unique_case_run_ids"] == 72,
                validation["unique_case_ids"] == 72,
                validation["all_completed"],
                validation["raw_hash_reverified_after_metrics"],
                validation["pre_post_frozen_identity_match"],
                validation["protected_corpus_gold_freeze_unchanged"],
                validation["production_code_unchanged"],
                validation["production_runtime_state_unchanged"],
                validation["selection_reconstruction_all_match"],
                validation["semantic_review_not_machine_approximated"],
            ]
        ) else "BLOCKED"
        write_json(run_dir / "validation.json", validation)

        artifact_hashes = {
            path.name: file_hash(path)
            for path in sorted(run_dir.iterdir())
            if path.is_file() and path.name not in {"run_manifest.json"}
        }
        run_manifest = {
            "schema_version": "1.0.0",
            "run_id": run_id,
            "status": validation["terminal_status"],
            "created_at": completed_at,
            "frozen_bindings": post_identities,
            "effective_configuration": config,
            "raw_results": {"path": relative(raw_path), "sha256": raw_sha, "frozen_before_metrics": True},
            "artifact_sha256": artifact_hashes,
            "isolation": {
                "sqlite": "run-local temporary, removed after audit",
                "uploads": "run-local temporary, removed after audit",
                "faiss": "run-local temporary, removed after audit",
                "checkpoint": "run-local temporary, removed after audit",
                "production_state_unchanged": validation["production_runtime_state_unchanged"],
            },
            "secret_handling": "allow-listed configuration only; no headers, keys, secrets, or environment dump recorded",
        }
        write_json(run_dir / "run_manifest.json", run_manifest)
        ROOT_REPORT.write_text(render_root_report(run_dir, raw, metrics, validation), encoding="utf-8")
        write_json(RESULTS_ROOT / "latest_run.json", {"run_id": run_id, "run_dir": relative(run_dir), "status": validation["terminal_status"]})
        print(json.dumps({"run_id": run_id, "run_dir": str(run_dir), "validation": validation}, ensure_ascii=False, indent=2), flush=True)
        return 0 if validation["terminal_status"] == "COMPLETE" else 2
    finally:
        shutil.rmtree(runtime_parent, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
