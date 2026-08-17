"""Run the frozen LearnPilot RAG baseline through isolated public HTTP interfaces."""

from __future__ import annotations

from argparse import ArgumentParser
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from typing import Any, Iterator
from uuid import uuid4

import httpx

from baseline_metrics import compute_run, recompute


ROOT = Path(__file__).resolve().parents[3]
BASE = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
ALEMBIC = ROOT / ".venv" / "Scripts" / "alembic.exe"


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, value: Any) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False) + "\n")


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def wait_ready(base_url: str, process: subprocess.Popen[str], log_path: Path) -> None:
    deadline = time.monotonic() + 120
    last_error = ""
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        try:
            response = httpx.get(f"{base_url}/health", timeout=2)
            if response.status_code == 200:
                return
            last_error = response.text
        except httpx.HTTPError as exc:
            last_error = str(exc)
        time.sleep(0.25)
    tail = ""
    if log_path.is_file():
        tail = "\n".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-40:])
    raise RuntimeError(f"isolated backend failed to start: {last_error}\n{tail}")


@contextmanager
def live_backend(port: int, environment: dict[str, str], log_path: Path) -> Iterator[str]:
    with log_path.open("a", encoding="utf-8") as log_handle:
        process = subprocess.Popen(
            [str(PYTHON), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
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


def timed_request(client: httpx.Client, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = client.request(method, url, **kwargs)
        elapsed = round((time.perf_counter() - started) * 1000, 2)
        result: dict[str, Any] = {"status_code": response.status_code, "elapsed_ms": elapsed}
        try:
            result["response_json"] = response.json()
        except ValueError:
            result["response_text"] = response.text
        return result
    except Exception as exc:
        return {
            "status_code": 0,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            "response_text": f"{type(exc).__name__}: {exc}",
        }


def require(result: dict[str, Any], expected: int, label: str) -> dict[str, Any]:
    if result["status_code"] != expected:
        raise RuntimeError(f"{label} returned {result['status_code']}: {result.get('response_json') or result.get('response_text')}")
    return result["response_json"]


def package_versions() -> dict[str, str]:
    script = (
        "import fastapi,pydantic,sqlalchemy,numpy,faiss,sentence_transformers,httpx;"
        "import json;print(json.dumps({'fastapi':fastapi.__version__,'pydantic':pydantic.__version__,"
        "'sqlalchemy':sqlalchemy.__version__,'numpy':numpy.__version__,'faiss':faiss.__version__,"
        "'sentence_transformers':sentence_transformers.__version__,'httpx':httpx.__version__}))"
    )
    output = subprocess.run([str(PYTHON), "-c", script], check=True, capture_output=True, text=True).stdout
    return json.loads(output)


def snapshot_file_set(paths: list[Path]) -> dict[str, Any]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(item for item in path.rglob("*") if item.is_file())
        else:
            files.append(path)
    return {
        str(path): {
            "exists": path.is_file(),
            "size": path.stat().st_size if path.is_file() else None,
            "mtime_ns": path.stat().st_mtime_ns if path.is_file() else None,
            "sha256": sha256(path.read_bytes()).hexdigest() if path.is_file() else None,
        }
        for path in sorted(set(files))
    }


def environment_for(runtime_dir: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "DATABASE_URL": f"sqlite:///{(runtime_dir / 'evaluation.sqlite3').as_posix()}",
            "UPLOAD_DIR": str(runtime_dir / "uploads"),
            "FAISS_INDEX_PATH": str(runtime_dir / "materials.faiss"),
            "FAISS_MANIFEST_PATH": str(runtime_dir / "materials.faiss.manifest.json"),
            "AGENT_CHECKPOINT_DB_PATH": str(runtime_dir / "agent_checkpoints.sqlite"),
            "DEMO_DATA_ENABLED": "false",
        }
    )
    return environment


def sqlite_persistence_audit(database: Path, filename_map: dict[str, str]) -> dict[str, Any]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    counts = {
        table: connection.execute(f"select count(*) from {table}").fetchone()[0]
        for table in ("materials", "material_chunks", "rag_conversations", "rag_messages", "rag_citations")
    }
    messages = [
        dict(row)
        for row in connection.execute(
            "select request_id,input_tokens,output_tokens,answerable,refusal_reason,status from rag_messages where role='assistant' order by id"
        )
    ]
    citations = [
        dict(row)
        for row in connection.execute(
            "select assistant_message_id,source_label,chunk_id,material_id,rank,score,original_filename,chunk_index,page_number,section_title from rag_citations order by assistant_message_id,rank"
        )
    ]
    chunks = [
        dict(row)
        for row in connection.execute(
            "select m.original_filename,c.id as chunk_id,c.chunk_index,c.content_hash,c.page_number,c.section_title from material_chunks c join materials m on m.id=c.material_id order by m.id,c.chunk_index"
        )
    ]
    connection.close()
    return {
        "counts": counts,
        "token_usage": {
            "available": any(item["input_tokens"] is not None or item["output_tokens"] is not None for item in messages),
            "input_tokens_total": sum(item["input_tokens"] or 0 for item in messages),
            "output_tokens_total": sum(item["output_tokens"] or 0 for item in messages),
            "messages_with_usage": sum(item["input_tokens"] is not None or item["output_tokens"] is not None for item in messages),
        },
        "assistant_messages": messages,
        "persisted_citations": [
            {**item, "document_id": filename_map.get(item["original_filename"])} for item in citations
        ],
        "run_local_chunks": [
            {**item, "document_id": filename_map.get(item["original_filename"])} for item in chunks
        ],
    }


def render_report(metadata: dict[str, Any], imports: list[dict[str, Any]], result: dict[str, Any], persistence: dict[str, Any], files: list[str]) -> str:
    aggregate = result["aggregate"]
    cases = result["cases"]
    passes = [item for item in cases if item["passed"]][:3]
    failures = [item for item in cases if not item["passed"]][:5]
    pct = lambda value: f"{value * 100:.2f}%"
    table_types = "\n".join(
        f"| {name} | {metrics['case_count']} | {pct(metrics['pass_rate'])} | {pct(metrics['retrieval_hit_at_k'])} | {pct(metrics['citation_expected_coverage'])} | {pct(metrics['key_fact_coverage'])} |"
        for name, metrics in aggregate["by_type"].items()
    )
    table_topics = "\n".join(
        f"| {name} | {metrics['case_count']} | {pct(metrics['pass_rate'])} | {pct(metrics['retrieval_hit_at_k'])} | {pct(metrics['citation_expected_coverage'])} |"
        for name, metrics in aggregate["by_topic"].items()
    )
    pass_lines = "\n".join(f"- `{item['case_id']}`：answerability、key facts 与 citation contract 均通过。" for item in passes) or "- 无。"
    fail_lines = "\n".join(f"- `{item['case_id']}` → `{item['failure_stage']}`；context={item.get('selected_context_document_ids')}；cited={item.get('cited_document_ids')}。" for item in failures) or "- 无失败 case。"
    failure_rows = "\n".join(f"| {name} | {count} |" for name, count in aggregate["failure_taxonomy"].items())
    created = "\n".join(f"- `{item}`" for item in files)
    terminal_status = (
        "RAG_BASELINE_EVAL_V1 = BLOCKED"
        if aggregate["reliability"]["infrastructure_failure_rate"] == 1.0
        else "RAG_BASELINE_EVAL_V1 = COMPLETE"
    )
    return f"""# LearnPilot RAG Baseline Eval V1

## 1. Eval environment

- Run ID：`{metadata['run_id']}`；isolated SQLite / uploads / FAISS / checkpoint 均位于 run-local 临时目录。
- Git HEAD：`{metadata['git']['head']}`；工作树 dirty：`{metadata['git']['working_tree']['dirty']}`；仅记录条目数：{metadata['git']['working_tree']['porcelain_entry_count']}，未记录无关文件名。
- Python：`{metadata['runtime']['python']}`；平台：`{metadata['runtime']['platform']}`。
- 主评分仅调用 `POST /api/rag/conversations/{{id}}/ask`；导入仅调用公开 materials APIs。
- 外发范围严格限定为 48 个评测问题及每题检索到的 project-owned controlled corpus 片段；未发送个人知识库、生产数据库、密钥、环境变量或无关仓库内容。

## 2. Frozen RAG configuration

`{json.dumps(metadata['rag_configuration'], ensure_ascii=False)}`

Embedding：`{metadata['embedding']['model']}` / `{metadata['embedding']['revision']}` / dimension `{metadata['embedding']['dimension']}` / normalized `{metadata['embedding']['normalized']}`。  
LLM：provider `{metadata['answer_model']['provider']}` / host `{metadata['answer_model'].get('host', 'not recorded')}` / model `{metadata['answer_model']['model']}` / prompt `{metadata['answer_model']['prompt_version']}`。  
FAISS index version：`{metadata['faiss']['index_version']}`。

## 3. Corpus import result

13/13 文档按 manifest 顺序通过 upload → process 成功；总 chunks：{sum(item['chunk_count'] for item in imports)}。`document_id → material_id` 已保存，未把运行时 ID 写入 gold truth。

## 4. Gold dataset composition

共 {aggregate['case_count']} cases；`single_doc_fact`、`semantic_paraphrase`、`multi_doc`、`rerank_disambiguation`、`citation_sensitive`、`unanswerable` 各 8。Gold 已通过独立 evidence verification。

## 5. Aggregate metrics

- Overall pass rate：{pct(aggregate['pass_rate'])} ({aggregate['pass_count']}/{aggregate['case_count']})
- Expected document Hit@K：{pct(aggregate['retrieval']['expected_document_hit_at_k'])}
- Expected document Recall@K：{pct(aggregate['retrieval']['expected_document_recall_at_k'])}
- Selected-context expected-document recall：{pct(aggregate['retrieval']['selected_context_expected_document_recall'])}
- Source precision@K：{pct(aggregate['retrieval']['source_precision_at_k'])}
- Wrong-source rate@K：{pct(aggregate['retrieval']['wrong_source_rate_at_k'])}
- Multi-document coverage：{pct(aggregate['retrieval']['multi_document_coverage'])}

## 6. Metrics by question type

| Type | Cases | Pass | Hit@K | Citation coverage | Key-fact coverage |
| --- | ---: | ---: | ---: | ---: | ---: |
{table_types}

## 7. Metrics by topic cluster

| Topic | Cases | Pass | Hit@K | Citation coverage |
| --- | ---: | ---: | ---: | ---: |
{table_topics}

## 8. Citation metrics

- Citation validity：{pct(aggregate['citation']['citation_validity_rate'])}
- Expected-document citation coverage：{pct(aggregate['citation']['expected_document_citation_coverage'])}
- Wrong-document citation rate：{pct(aggregate['citation']['wrong_document_citation_rate'])}
- Missing-citation case rate：{pct(aggregate['citation']['missing_citation_case_rate'])}
- Unanswerable citation case rate：{pct(aggregate['citation']['unanswerable_citation_case_rate'])}

## 9. Answerability metrics

- Answerable success：{pct(aggregate['answer']['answerable_success_rate'])}
- Key-fact coverage：{pct(aggregate['answer']['key_fact_coverage'])}
- Unanswerable/refusal accuracy：{pct(aggregate['answer']['unanswerable_refusal_accuracy'])}
- Unsupported-answer proxy rate：{pct(aggregate['answer']['unsupported_answer_proxy_rate'])}

## 10. Latency / reliability

- Infrastructure failure rate：{pct(aggregate['reliability']['infrastructure_failure_rate'])}
- Generation/repair failure rate：{pct(aggregate['reliability']['generation_repair_failure_rate'])}
- Fallback rate：{pct(aggregate['reliability']['fallback_rate'])}
- Latency average / p50 / p95：{aggregate['reliability']['latency_ms']['average']} / {aggregate['reliability']['latency_ms']['p50']} / {aggregate['reliability']['latency_ms']['p95']} ms
- Token usage：{json.dumps(aggregate['reliability']['token_usage'], ensure_ascii=False)}
- Cost：runtime 不提供 provider price，未估算不受支持的成本。

## 11. Failure taxonomy

| Stage | Count |
| --- | ---: |
{failure_rows}

## 12. Representative PASS cases

{pass_lines}

## 13. Representative FAIL cases

{fail_lines}

## 14. Root-cause observations

- 诊断严格区分 expected document 未过 threshold、被 selection 淘汰、被 context budget 截断、进入上下文后生成失败以及 citation failure。
- `rerank_disambiguation` 只是 eval category；当前架构没有 cross-encoder/LLM reranker。
- Key-fact coverage 是冻结 key facts 与 final answer 的 deterministic lexical proxy，原始回答保留供人工审计。

## 15. Recommended next optimization candidates

仅根据本 baseline 的失败明细考虑后续独立任务；优先查看失败最多的 taxonomy stage。本轮未改变 Top K、threshold、chunking、Embedding、prompt、citation 或 selection logic。

## 16. Explicit limitations

- 13 篇均为 project-owned system corpus，不代表开放域或真实教育分布。
- 候选/selected context 是用公开 `/materials/search` 原始结果和冻结 production rules 重构，用 response `source_count` 校验；当前 ask response 不直接暴露全部 context rows。
- Unsupported-answer 使用 citation/evidence proxy，不是外部 LLM judge。
- Provider 成本不可观测；只记录实际 token usage（若 provider 返回）。

## 17. Exact files created/modified

{created}

## 18. Production RAG behavior confirmation

未修改 `backend/app/services/rag/*`、Embedding、chunking、FAISS、prompt、schema、citation 或 UI。个人 SQLite/FAISS/upload 文件在运行前后按 hash/mtime 复核；eval service 已停止，临时 runtime 已清理，仅保留版本化结果 artifacts。artifacts/logs 未记录 API Key 或环境变量。

{terminal_status}
"""


def finalize_existing_run(run_dir: Path) -> int:
    """Rebuild deterministic reports from a completed run without any API calls."""
    run_dir = run_dir.resolve()
    metadata = json.loads((run_dir / "run_metadata.json").read_text(encoding="utf-8"))
    mapping = json.loads((run_dir / "document_material_map.json").read_text(encoding="utf-8"))
    imports = mapping["imports"]
    persistence = json.loads((run_dir / "persistence_audit.json").read_text(encoding="utf-8"))
    validation = json.loads((run_dir / "validation.json").read_text(encoding="utf-8"))
    result = recompute(run_dir)
    if not (
        validation["documents_imported"] == 13
        and validation["cases_executed"] == 48
        and validation["unique_case_ids"] == 48
        and validation["production_paths_unchanged"]
        and validation["metrics_recomputed_from_raw"]
    ):
        raise RuntimeError(f"cannot finalize invalid run: {validation}")
    result_artifacts = [
        str(path.relative_to(ROOT)).replace("\\", "/")
        for sibling in sorted(run_dir.parent.iterdir())
        if sibling.is_dir()
        for path in sorted(sibling.iterdir())
        if path.is_file()
    ]
    files = sorted(set([
        "evals/rag_demo_corpus/v1/gold_cases.json",
        "evals/rag_demo_corpus/v1/gold_cases.schema.json",
        "evals/rag_demo_corpus/v1/validate_foundation.py",
        "evals/rag_demo_corpus/v1/verify_gold_cases.py",
        "evals/rag_demo_corpus/v1/baseline_metrics.py",
        "evals/rag_demo_corpus/v1/run_baseline_eval.py",
        "evals/rag_demo_corpus/v1/app_config_probe.py",
        "backend/tests/test_rag_baseline_eval_tooling.py",
        *result_artifacts,
        str((run_dir / "report.md").relative_to(ROOT)).replace("\\", "/"),
        str((run_dir / "result.json").relative_to(ROOT)).replace("\\", "/"),
    ]))
    write_json(run_dir / "metrics.json", result["aggregate"])
    write_json(run_dir / "case_analysis.json", result["cases"])
    write_json(run_dir / "failure_taxonomy.json", {
        "counts": result["aggregate"]["failure_taxonomy"],
        "failures": [item for item in result["cases"] if not item["passed"]],
    })
    (run_dir / "report.md").write_text(
        render_report(metadata, imports, result, persistence, files), encoding="utf-8"
    )
    run_status = (
        "blocked"
        if result["aggregate"]["reliability"]["infrastructure_failure_rate"] == 1.0
        else "complete"
    )
    write_json(run_dir / "result.json", {
        "status": run_status,
        "metadata": metadata,
        "imports": imports,
        "metrics": result["aggregate"],
        "validation": validation,
    })
    print(json.dumps({"status": run_status, "run_dir": str(run_dir)}, ensure_ascii=False, indent=2))
    return 2 if run_status == "blocked" else 0


def main() -> int:
    parser = ArgumentParser()
    parser.add_argument("--port", type=int, default=8021)
    parser.add_argument(
        "--finalize-run",
        type=Path,
        help="Rebuild report/result from an existing completed run without external calls.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=BASE / "results" / "baseline_v1",
    )
    args = parser.parse_args()
    if args.finalize_run:
        return finalize_existing_run(args.finalize_run)
    manifest = json.loads((BASE / "corpus_manifest.json").read_text(encoding="utf-8"))
    gold = json.loads((BASE / "gold_cases.json").read_text(encoding="utf-8"))
    if len(manifest["documents"]) != 13 or len(gold["cases"]) != 48:
        raise RuntimeError("frozen foundation counts are not 13 documents / 48 cases")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    run_dir = args.output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    raw_path = run_dir / "raw_cases.jsonl"
    runtime_parent = Path(tempfile.mkdtemp(prefix="learnpilot-rag-baseline-v1-"))
    runtime_dir = runtime_parent / "runtime"
    runtime_dir.mkdir()
    environment = environment_for(runtime_dir)
    production_paths = [
        BACKEND / "data" / "personal_learning.sqlite3",
        BACKEND / "data" / "materials.faiss",
        BACKEND / "data" / "materials.faiss.manifest.json",
        BACKEND / "data" / "agent_checkpoints.sqlite",
        ROOT / "data" / "agent_checkpoints.sqlite",
        BACKEND / "uploads",
    ]
    production_before = snapshot_file_set(production_paths)
    imports: list[dict[str, Any]] = []
    raw_cases: list[dict[str, Any]] = []
    try:
        foundation = subprocess.run(
            [str(PYTHON), str(BASE / "validate_foundation.py")],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )
        verification = subprocess.run(
            [str(PYTHON), str(BASE / "verify_gold_cases.py")],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )
        preflight = {
            "foundation": json.loads(foundation.stdout),
            "gold_verification": json.loads(verification.stdout),
            "canonical_api_path": [
                "POST /api/materials/upload",
                "POST /api/materials/{material_id}/process",
                "POST /api/rag/conversations",
                "POST /api/rag/conversations/{conversation_id}/ask",
            ],
            "canonical_source_hashes": {
                str(path.relative_to(ROOT)).replace("\\", "/"): sha256(path.read_bytes()).hexdigest()
                for path in (
                    BACKEND / "app/api/routes/materials.py",
                    BACKEND / "app/api/routes/rag.py",
                    BACKEND / "app/services/material_processing/pipeline.py",
                    BACKEND / "app/services/vector_store/service.py",
                    BACKEND / "app/services/rag/retrieval.py",
                    BACKEND / "app/services/rag/service.py",
                    BACKEND / "app/services/rag/grounding.py",
                    BACKEND / "app/services/rag/validation.py",
                )
            },
        }
        write_json(run_dir / "preflight.json", preflight)
        migration = subprocess.run([str(ALEMBIC), "upgrade", "head"], cwd=BACKEND, env=environment, capture_output=True, text=True)
        if migration.returncode != 0:
            raise RuntimeError(f"isolated migration failed: {migration.stderr}")
        with live_backend(args.port, environment, run_dir / "backend.log") as base_url:
            with httpx.Client(base_url=base_url, timeout=180) as client:
                rag_status = require(timed_request(client, "GET", "/rag/status"), 200, "rag status")
                if not rag_status["llm_configured"]:
                    raise RuntimeError("real answer provider is not configured")
                filename_map: dict[str, str] = {}
                id_map: dict[str, int] = {}
                for document in manifest["documents"]:
                    path = ROOT / document["repository_path"]
                    actual_hash = sha256(path.read_bytes()).hexdigest()
                    if actual_hash != document["sha256"]:
                        raise RuntimeError(f"corpus hash mismatch before import: {document['document_id']}")
                    upload = timed_request(client, "POST", "/materials/upload", files={"file": (path.name, path.read_bytes(), "text/markdown")})
                    uploaded = require(upload, 201, f"upload {document['document_id']}")
                    process = timed_request(client, "POST", f"/materials/{uploaded['id']}/process")
                    processed = require(process, 200, f"process {document['document_id']}")
                    filename_map[path.name] = document["document_id"]
                    id_map[document["document_id"]] = uploaded["id"]
                    imports.append({
                        "document_id": document["document_id"], "material_id": uploaded["id"],
                        "original_filename": path.name, "sha256": actual_hash,
                        "upload_status": upload["status_code"], "upload_elapsed_ms": upload["elapsed_ms"],
                        "processing_status": processed["ingestion_status"], "chunk_count": processed["chunk_count"],
                        "indexing_status": processed["indexing_status"], "process_elapsed_ms": process["elapsed_ms"],
                    })
                    write_json(run_dir / "document_material_map.json", {"corpus_version": "v1", "mapping": id_map, "imports": imports})
                index_status = require(timed_request(client, "GET", "/materials/index/status"), 200, "index status")
                runtime_manifest = json.loads((runtime_dir / "materials.faiss.manifest.json").read_text(encoding="utf-8"))
                from app_config_probe import probe_config  # type: ignore
                config = probe_config(environment)
                metadata = {
                    "run_id": run_id, "started_at": datetime.now(timezone.utc).isoformat(),
                    "corpus_id": manifest["corpus_id"], "corpus_version": manifest["corpus_version"],
                    "corpus_hashes": {item["document_id"]: item["sha256"] for item in manifest["documents"]},
                    "git": {
                        "head": git("rev-parse", "HEAD"),
                        "working_tree": {
                            "dirty": bool(git("status", "--porcelain=v1")),
                            "porcelain_entry_count": len(git("status", "--porcelain=v1").splitlines()),
                        },
                    },
                    "embedding": {"model": runtime_manifest["model_name"], "revision": runtime_manifest["model_revision"], "dimension": runtime_manifest["embedding_dimension"], "normalized": runtime_manifest["normalized"]},
                    "rag_configuration": config["rag_configuration"],
                    "answer_model": {"provider": config["llm_provider"], "host": config["llm_host"], "model": rag_status["model"], "prompt_version": rag_status["rag_prompt_version"], "rewrite_prompt_version": rag_status["rewrite_prompt_version"], "answer_schema": "RagGroundedAnswerDraft"},
                    "faiss": {"index_version": index_status["index_version"], "chunk_count": index_status["chunk_count"], "built_at": index_status["built_at"], "distance_metric": runtime_manifest["distance_metric"]},
                    "runtime": {"python": platform.python_version(), "platform": platform.platform(), "packages": package_versions()},
                    "filename_to_document_id": filename_map,
                    "document_topics": {item["document_id"]: item["topic"] for item in manifest["documents"]},
                    "isolation": {"database": str(runtime_dir / "evaluation.sqlite3"), "upload_dir": str(runtime_dir / "uploads"), "faiss_index": str(runtime_dir / "materials.faiss"), "faiss_manifest": str(runtime_dir / "materials.faiss.manifest.json"), "checkpoint": str(runtime_dir / "agent_checkpoints.sqlite")},
                }
                write_json(run_dir / "run_metadata.json", metadata)
                for index, case in enumerate(gold["cases"], start=1):
                    search = timed_request(client, "POST", "/materials/search", json={"query": case["question"], "top_k": config["search_top_k_max"], "min_score": None})
                    conversation = timed_request(client, "POST", "/rag/conversations", json={"title": f"baseline:{case['case_id']}"})
                    conversation_body = require(conversation, 201, f"conversation {case['case_id']}")
                    ask = timed_request(client, "POST", f"/rag/conversations/{conversation_body['id']}/ask", json={"question": case["question"], "request_id": f"bev1-{index:03d}-{uuid4().hex[:8]}", "top_k": config["rag_configuration"]["top_k"]})
                    raw = {"sequence": index, "case": case, "diagnostic_search": search, "conversation": conversation, "ask": ask}
                    raw_cases.append(raw)
                    append_jsonl(raw_path, raw)
        persistence = sqlite_persistence_audit(runtime_dir / "evaluation.sqlite3", metadata["filename_to_document_id"])
        write_json(run_dir / "persistence_audit.json", persistence)
        result = compute_run(raw_cases, metadata, persistence)
        write_json(run_dir / "metrics.json", result["aggregate"])
        write_json(run_dir / "case_analysis.json", result["cases"])
        write_json(run_dir / "failure_taxonomy.json", {"counts": result["aggregate"]["failure_taxonomy"], "failures": [item for item in result["cases"] if not item["passed"]]})
        recomputed = recompute(run_dir)
        production_after = snapshot_file_set(production_paths)
        validation = {
            "documents_imported": len(imports), "documents_expected": 13,
            "cases_executed": len(raw_cases), "cases_expected": 48,
            "unique_case_ids": len({item['case']['case_id'] for item in raw_cases}),
            "assistant_messages": persistence["counts"]["rag_messages"] // 2,
            "metrics_recomputed_from_raw": recomputed == result,
            "production_paths_unchanged": production_before == production_after,
            "production_before": production_before, "production_after": production_after,
            "temporary_service_stopped": True, "runtime_cleanup_policy": "deleted after artifact extraction",
        }
        write_json(run_dir / "validation.json", validation)
        if not (validation["documents_imported"] == 13 and validation["cases_executed"] == 48 and validation["unique_case_ids"] == 48 and validation["production_paths_unchanged"] and validation["metrics_recomputed_from_raw"]):
            raise RuntimeError(f"post-run validation failed: {validation}")
        files = sorted(set([
            "evals/rag_demo_corpus/v1/gold_cases.json", "evals/rag_demo_corpus/v1/gold_cases.schema.json",
            "evals/rag_demo_corpus/v1/validate_foundation.py",
            "evals/rag_demo_corpus/v1/verify_gold_cases.py", "evals/rag_demo_corpus/v1/baseline_metrics.py",
            "evals/rag_demo_corpus/v1/run_baseline_eval.py", "evals/rag_demo_corpus/v1/app_config_probe.py",
            "backend/tests/test_rag_baseline_eval_tooling.py",
            *[str(path.relative_to(ROOT)).replace('\\', '/') for path in sorted(run_dir.iterdir())],
            str((run_dir / "report.md").relative_to(ROOT)).replace('\\', '/'),
            str((run_dir / "result.json").relative_to(ROOT)).replace('\\', '/'),
        ]))
        report = render_report(metadata, imports, result, persistence, files)
        (run_dir / "report.md").write_text(report, encoding="utf-8")
        run_status = (
            "blocked"
            if result["aggregate"]["reliability"]["infrastructure_failure_rate"] == 1.0
            else "complete"
        )
        write_json(run_dir / "result.json", {"status": run_status, "metadata": metadata, "imports": imports, "metrics": result["aggregate"], "validation": validation})
        print(json.dumps({"status": run_status, "run_dir": str(run_dir), "metrics": result["aggregate"]}, ensure_ascii=False, indent=2))
        return 2 if run_status == "blocked" else 0
    finally:
        shutil.rmtree(runtime_parent, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
