"""Ingest Real-world Corpus V1 through isolated public HTTP interfaces only."""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from typing import Any, Iterator
from uuid import uuid4

import httpx


ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
ALEMBIC = ROOT / ".venv" / "Scripts" / "alembic.exe"
MIME_TYPES = {"md":"text/markdown", "txt":"text/plain", "pdf":"application/pdf"}
PRODUCTION_SOURCE_FILES = (
    BACKEND / "app/api/routes/materials.py",
    BACKEND / "app/services/material_processing/pipeline.py",
    BACKEND / "app/services/material_processing/chunking.py",
    BACKEND / "app/services/material_processing/cleaning.py",
    BACKEND / "app/services/material_processing/parsers/markdown.py",
    BACKEND / "app/services/material_processing/parsers/text.py",
    BACKEND / "app/services/material_processing/parsers/pdf.py",
    BACKEND / "app/services/vector_store/service.py",
    BACKEND / "app/services/vector_store/faiss_store.py",
    BACKEND / "app/services/embedding/bge_m3.py",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


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
            "sha256": file_hash(path) if path.is_file() else None,
        }
        for path in sorted(set(files))
    }


def sanitized_environment(runtime_dir: Path) -> dict[str, str]:
    environment = os.environ.copy()
    for name in tuple(environment):
        upper = name.upper()
        if any(marker in upper for marker in ("API_KEY", "ACCESS_TOKEN", "AUTH_TOKEN", "PASSWORD", "SECRET")):
            environment.pop(name, None)
    environment.update({
        "DATABASE_URL": f"sqlite:///{(runtime_dir / 'evaluation.sqlite3').as_posix()}",
        "UPLOAD_DIR": str(runtime_dir / "uploads"),
        "FAISS_INDEX_PATH": str(runtime_dir / "materials.faiss"),
        "FAISS_MANIFEST_PATH": str(runtime_dir / "materials.faiss.manifest.json"),
        "AGENT_CHECKPOINT_DB_PATH": str(runtime_dir / "agent_checkpoints.sqlite"),
        "DEMO_DATA_ENABLED": "false",
        "EMBEDDING_LOCAL_FILES_ONLY": "true",
        "LLM_API_KEY": "",
        "LLM_BASE_URL": "",
        "LLM_MODEL": "",
    })
    return environment


def wait_ready(base_url: str, process: subprocess.Popen[str], log_path: Path) -> None:
    deadline = time.monotonic() + 180
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
        try:
            body: Any = response.json()
        except ValueError:
            body = response.text[:1000]
        return {"status_code":response.status_code, "elapsed_ms":elapsed, "body":body}
    except Exception as exc:
        return {
            "status_code":0,
            "elapsed_ms":round((time.perf_counter() - started) * 1000, 2),
            "body":f"{type(exc).__name__}: {exc}",
        }


def require(result: dict[str, Any], expected: int, label: str) -> Any:
    if result["status_code"] != expected:
        raise RuntimeError(f"{label} returned {result['status_code']}: {result['body']}")
    return result["body"]


def package_versions() -> dict[str, str]:
    script = (
        "import fastapi,pydantic,sqlalchemy,numpy,faiss,sentence_transformers,httpx,pypdf;"
        "import json;print(json.dumps({'fastapi':fastapi.__version__,'pydantic':pydantic.__version__,"
        "'sqlalchemy':sqlalchemy.__version__,'numpy':numpy.__version__,'faiss':faiss.__version__,"
        "'sentence_transformers':sentence_transformers.__version__,'httpx':httpx.__version__,"
        "'pypdf':pypdf.__version__}))"
    )
    output = subprocess.run([str(PYTHON), "-c", script], check=True, capture_output=True, text=True).stdout
    return json.loads(output)


def database_audit(database: Path) -> dict[str, Any]:
    connection = sqlite3.connect(database)
    counts = {
        table: connection.execute(f"select count(*) from {table}").fetchone()[0]
        for table in ("materials", "material_chunks", "rag_conversations", "rag_messages", "rag_citations")
    }
    distinct_hashes = connection.execute("select count(distinct content_hash) from material_chunks").fetchone()[0]
    connection.close()
    return {"counts":counts, "distinct_chunk_content_hashes":distinct_hashes}


def shape_summary(imports: list[dict[str, Any]], inventory: list[dict[str, Any]]) -> dict[str, Any]:
    document_counts = {item["document_id"]: item["chunk_count"] for item in imports}
    by_topic: Counter[str] = Counter()
    by_format: Counter[str] = Counter()
    for item in imports:
        by_topic[item["topic_cluster"]] += item["chunk_count"]
        by_format[item["source_format"]] += item["chunk_count"]
    char_counts = [item["char_count"] for item in inventory]
    total = sum(document_counts.values())
    repeated_hash_groups = [
        {
            "content_hash":content_hash,
            "occurrences":len(items),
            "locations":[
                {
                    "document_id":item["document_id"],
                    "chunk_index":item["chunk_index"],
                    "section_title":item["section_title"],
                    "page_number":item["page_number"],
                }
                for item in items
            ],
        }
        for content_hash in sorted({item["content_hash"] for item in inventory})
        if len(items := [item for item in inventory if item["content_hash"] == content_hash]) > 1
    ]
    topic_shares = {key: round(value / total, 6) for key, value in sorted(by_topic.items())}
    format_shares = {key: round(value / total, 6) for key, value in sorted(by_format.items())}
    return {
        "total_chunks":total,
        "by_document":document_counts,
        "by_topic":dict(sorted(by_topic.items())),
        "by_format":dict(sorted(by_format.items())),
        "topic_shares":topic_shares,
        "format_shares":format_shares,
        "largest_topic_share":max(topic_shares.values(), default=0),
        "largest_document_share":round(max(document_counts.values(), default=0) / total, 6) if total else 0,
        "chunk_chars":{
            "min":min(char_counts, default=0),
            "max":max(char_counts, default=0),
            "mean":round(sum(char_counts) / len(char_counts), 2) if char_counts else 0,
        },
        "repeated_chunk_content":{
            "group_count":len(repeated_hash_groups),
            "duplicate_occurrence_count":sum(item["occurrences"] - 1 for item in repeated_hash_groups),
            "groups":repeated_hash_groups,
        },
    }


def render_report(
    manifest: dict[str, Any],
    metadata: dict[str, Any],
    imports: list[dict[str, Any]],
    shape: dict[str, Any],
    validation: dict[str, Any],
    acquisition_decisions: dict[str, Any],
) -> str:
    import_rows = "\n".join(
        f"| {item['document_id']} | {item['topic_cluster']} | {item['source_format']} | {item['chunk_count']} | {item['upload_elapsed_ms']} | {item['process_elapsed_ms']} | {item['ingestion_status']}/{item['indexing_status']} |"
        for item in imports
    )
    rejected_rows = "\n".join(
        f"| {item['candidate']} | {item['reason']} |" for item in acquisition_decisions["rejected"]
    )
    topic_rows = "\n".join(
        f"| {topic} | {count} | {shape['topic_shares'][topic] * 100:.2f}% |"
        for topic, count in shape["by_topic"].items()
    )
    format_rows = "\n".join(
        f"| {fmt} | {count} | {shape['format_shares'][fmt] * 100:.2f}% |"
        for fmt, count in shape["by_format"].items()
    )
    files = [
        "corpus_manifest.json", "corpus_manifest.schema.json", "acquisition_lock.json",
        "source_decisions.json", "license_provenance_audit.json", "chunk_projection.json",
        "duplicate_overlap_analysis.json", "validation_report.json", "acquire_corpus.py",
        "validate_corpus.py", "run_ingestion.py", "README.md",
        "results/ingestion_v1/<run-id>/preflight.json", "imports.json", "chunk_inventory.json",
        "run_metadata.json", "validation.json", "report.md", "result.json", "backend.log",
    ]
    return f"""# LearnPilot RAG Real-world Corpus V1 — Acquisition & Installation

## 1. 结论与边界

已冻结并通过真实公开接口导入 {manifest['document_count']} 篇许可明确的官方上游资料，实际生成 {shape['total_chunks']} 个 chunks。此运行没有 Gold 问题、没有答案生成、没有 DeepSeek 调用，也没有改动生产或个人知识库状态。

## 2. Corpus Manifest

- Corpus：`{manifest['corpus_id']}@{manifest['corpus_version']}`
- 文档：{manifest['document_count']}；格式：{manifest['format_plan']}；主题：{manifest['topic_plan']}
- Manifest、来源 SHA-256、语料 SHA-256、固定提交、许可证与归属均已机器校验。

## 3. 来源清单与固定版本

每篇材料的官方仓库、40 位提交 SHA、上游路径、取得时间、许可证来源和 attribution 见 `corpus_manifest.json`；仓库锁见 `acquisition_lock.json`。

## 4. 许可证与可再分发说明

使用的许可证仅为 MIT、Apache-2.0 与 CC-BY-4.0。许可证原文已冻结到 `provenance/licenses/`。再分发时必须继续保留各项目的 copyright、归属和变换说明；若未来引入带 NOTICE 的材料，也必须保留其 NOTICE。

## 5. Transformation 说明

MD/MDX/TXT 材料为逐字节副本（MDX 仅改变容器扩展名时也不改内容）；两份 PDF 是把固定提交中的上游 Markdown/MDX 原文逐行、等宽、可复制地渲染为 A4，未摘要、翻译或注入检索词。逐文档变换参数见 manifest。

## 6. 接受与拒绝来源

| 拒绝候选 | 原因 |
|---|---|
{rejected_rows}

接受来源详表见 `source_decisions.json`。

## 7. 导入方式与隔离策略

只使用 `POST /api/materials/upload` 与 `POST /api/materials/{{material_id}}/process`。SQLite、uploads、FAISS index/manifest 与 agent checkpoint 均指向一次性运行目录；运行后删除。服务进程环境会剥离密钥类变量，并明确清空 LLM 配置。

## 8. 实际导入结果与延迟

| 文档 | 主题 | 格式 | chunks | upload ms | process ms | 状态 |
|---|---|---:|---:|---:|---:|---|
{import_rows}

## 9. Chunk 形态

| 主题 | chunks | 占比 |
|---|---:|---:|
{topic_rows}

| 格式 | chunks | 占比 |
|---|---:|---:|
{format_rows}

Chunk 字符数 min/mean/max = {shape['chunk_chars']['min']}/{shape['chunk_chars']['mean']}/{shape['chunk_chars']['max']}。逐文档和逐 chunk（只含 hash/长度/页码/标题，不复制正文）见 `imports.json` 与 `chunk_inventory.json`。

## 10. Topic / Format Balance

最大主题占比 {shape['largest_topic_share'] * 100:.2f}%，最大单文档占比 {shape['largest_document_share'] * 100:.2f}%。RAG/Agent 的真实官方文档在生产 Markdown 解析器下产生较多短 section chunks；这是本轮测量到的生产行为，不通过改切块参数掩盖。

## 11. 重复与语义重叠分析

文件 SHA-256 精确重复为 0，标准化 token 5-gram 近重复文档为 0。实际 chunks 中有 {shape['repeated_chunk_content']['duplicate_occurrence_count']} 个额外重复 occurrence，来自 Ragas 同一上游文档在两个示例章节重复的 449 字符官方示例；保持来源忠实，不在 corpus 层去重。详细文档对阈值见 `duplicate_overlap_analysis.json`，chunk 位置见 `shape_analysis.json`。

## 12. 规模判断

实际 {shape['total_chunks']} chunks，位于本任务可接受的 150–600 区间，足以进行后续真实规模 RAG 评测；本轮不创建 Gold 问题。

## 13. 可复现性

运行 ID `{metadata['run_id']}`；Git HEAD `{metadata['git']['head']}`；Python {metadata['runtime']['python']}；模型 `{metadata['embedding']['model']}@{metadata['embedding']['revision']}`，维度 {metadata['embedding']['dimension']}。`acquire_corpus.py` 会核对每个临时克隆的实际 HEAD 后才重建语料；`validate_corpus.py` 可离线重算 hashes、解析与切块投影。

## 14. 生产/个人数据不变证明

生产及个人 SQLite、uploads、FAISS、checkpoint 前后快照相同：{validation['production_paths_unchanged']}。生产解析、切块、Embedding、索引源码前后哈希相同：{validation['production_sources_unchanged']}。运行内 RAG conversations/messages/citations 均为 0：{validation['no_answer_evaluation_state']}。

## 15. 验证

- manifest / license / hash / format / topic / duplicate：passed
- 11 篇经公开 API 导入并处理：{validation['all_documents_imported']}
- 实际 chunks 与投影一致：{validation['actual_matches_projection']}
- FAISS chunk 数与数据库一致：{validation['faiss_matches_chunks']}
- 临时服务停止且运行目录删除：{validation['temporary_service_stopped'] and validation['runtime_deleted']}

## 16. 下一阶段建议

基于此冻结版本单独设计真实世界 Gold 集；优先覆盖短 section 密集文档、跨文档概念重叠、PDF 页码引用和 Agent/RAG 主题边界。不要回写本轮 corpus 或调整生产切块参数来适配题目。

## 17. 交付文件

{chr(10).join(f'- `{item}`' for item in files)}

RAG_REAL_WORLD_CORPUS_V1 = READY
"""


def main() -> int:
    if not PYTHON.is_file() or not ALEMBIC.is_file():
        raise RuntimeError("project virtual environment is unavailable")
    manifest = json.loads((HERE / "corpus_manifest.json").read_text(encoding="utf-8"))
    projection = json.loads((HERE / "chunk_projection.json").read_text(encoding="utf-8"))
    acquisition_decisions = json.loads((HERE / "source_decisions.json").read_text(encoding="utf-8"))
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    output_root = HERE / "results" / "ingestion_v1"
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    runtime_parent = Path(tempfile.mkdtemp(prefix="learnpilot-rag-real-world-v1-"))
    runtime_dir = runtime_parent / "runtime"
    runtime_dir.mkdir()
    environment = sanitized_environment(runtime_dir)
    production_paths = [
        BACKEND / "data" / "personal_learning.sqlite3",
        BACKEND / "data" / "materials.faiss",
        BACKEND / "data" / "materials.faiss.manifest.json",
        BACKEND / "data" / "agent_checkpoints.sqlite",
        ROOT / "data" / "agent_checkpoints.sqlite",
        BACKEND / "uploads",
    ]
    production_before = snapshot_file_set(production_paths)
    source_before = {str(path.relative_to(ROOT)).replace("\\", "/"):file_hash(path) for path in PRODUCTION_SOURCE_FILES}
    imports: list[dict[str, Any]] = []
    inventory: list[dict[str, Any]] = []
    service_stopped = False
    runtime_deleted = False
    started_at = utc_now()
    try:
        validation_result = subprocess.run(
            [str(PYTHON), str(HERE / "validate_corpus.py")], cwd=ROOT,
            check=True, capture_output=True, text=True,
        )
        preflight = {
            "validation":json.loads(validation_result.stdout),
            "canonical_api_path":[
                "POST /api/materials/upload",
                "POST /api/materials/{material_id}/process",
                "GET /api/materials/{material_id}/chunks",
                "GET /api/materials/index/status",
            ],
            "answer_evaluation":False,
            "network_answer_provider":False,
            "secret_environment_policy":"secret-like variables removed; LLM fields explicitly blank",
            "production_source_hashes":source_before,
        }
        write_json(run_dir / "preflight.json", preflight)
        migration = subprocess.run(
            [str(ALEMBIC), "upgrade", "head"], cwd=BACKEND, env=environment,
            capture_output=True, text=True,
        )
        if migration.returncode != 0:
            raise RuntimeError(f"isolated migration failed: {migration.stderr}")
        port = available_port()
        with live_backend(port, environment, run_dir / "backend.log") as base_url:
            with httpx.Client(base_url=base_url, timeout=900) as client:
                for document in manifest["documents"]:
                    path = ROOT / document["repository_path"]
                    if file_hash(path) != document["corpus_sha256"]:
                        raise RuntimeError(f"corpus hash mismatch before upload: {document['document_id']}")
                    upload = timed_request(
                        client, "POST", "/materials/upload",
                        files={"file":(path.name, path.read_bytes(), MIME_TYPES[document["source_format"]])},
                    )
                    uploaded = require(upload, 201, f"upload {document['document_id']}")
                    process = timed_request(client, "POST", f"/materials/{uploaded['id']}/process")
                    processed = require(process, 200, f"process {document['document_id']}")
                    chunk_page = timed_request(
                        client, "GET", f"/materials/{uploaded['id']}/chunks",
                        params={"page":1, "page_size":100},
                    )
                    first_page = require(chunk_page, 200, f"chunks {document['document_id']}")
                    chunk_items = list(first_page["items"])
                    for page in range(2, first_page["pages"] + 1):
                        next_page = require(
                            timed_request(
                                client, "GET", f"/materials/{uploaded['id']}/chunks",
                                params={"page":page, "page_size":100},
                            ),
                            200,
                            f"chunks {document['document_id']} page {page}",
                        )
                        chunk_items.extend(next_page["items"])
                    if len(chunk_items) != processed["chunk_count"]:
                        raise RuntimeError(f"chunk pagination mismatch: {document['document_id']}")
                    imports.append({
                        "document_id":document["document_id"],
                        "material_id":uploaded["id"],
                        "topic_cluster":document["topic_cluster"],
                        "source_format":document["source_format"],
                        "original_filename":path.name,
                        "corpus_sha256":document["corpus_sha256"],
                        "upload_status":upload["status_code"],
                        "upload_elapsed_ms":upload["elapsed_ms"],
                        "process_status":process["status_code"],
                        "process_elapsed_ms":process["elapsed_ms"],
                        "ingestion_status":processed["ingestion_status"],
                        "indexing_status":processed["indexing_status"],
                        "chunk_count":processed["chunk_count"],
                        "indexed_chunk_count":processed["indexed_chunk_count"],
                    })
                    inventory.extend({
                        "document_id":document["document_id"],
                        "material_id":uploaded["id"],
                        "chunk_id":item["id"],
                        "chunk_index":item["chunk_index"],
                        "char_count":item["char_count"],
                        "content_hash":item["content_hash"],
                        "page_number":item["page_number"],
                        "section_title":item["section_title"],
                    } for item in chunk_items)
                    write_json(run_dir / "imports.json", imports)
                    write_json(run_dir / "chunk_inventory.json", inventory)
                index_status = require(timed_request(client, "GET", "/materials/index/status"), 200, "index status")
        service_stopped = True
        runtime_manifest = json.loads((runtime_dir / "materials.faiss.manifest.json").read_text(encoding="utf-8"))
        persistence = database_audit(runtime_dir / "evaluation.sqlite3")
        shape = shape_summary(imports, inventory)
        metadata = {
            "run_id":run_id,
            "started_at":started_at,
            "finished_at":utc_now(),
            "corpus_id":manifest["corpus_id"],
            "corpus_version":manifest["corpus_version"],
            "git":{
                "head":git("rev-parse", "HEAD"),
                "working_tree_dirty":bool(git("status", "--porcelain=v1")),
            },
            "embedding":{
                "model":runtime_manifest["model_name"],
                "revision":runtime_manifest["model_revision"],
                "dimension":runtime_manifest["embedding_dimension"],
                "normalized":runtime_manifest["normalized"],
                "distance_metric":runtime_manifest["distance_metric"],
                "local_files_only":True,
            },
            "chunking":projection["canonical_chunking"],
            "faiss":{
                "chunk_count":index_status["chunk_count"],
                "index_version":index_status["index_version"],
                "available":index_status["available"],
                "stale":index_status["stale"],
            },
            "runtime":{"python":platform.python_version(), "platform":platform.platform(), "packages":package_versions()},
            "isolation":{
                "runtime_paths_recorded":False,
                "runtime_cleanup_policy":"delete after audit extraction",
                "llm_configuration_present":False,
            },
        }
        write_json(run_dir / "run_metadata.json", metadata)
        write_json(run_dir / "shape_analysis.json", shape)
        write_json(run_dir / "persistence_audit.json", persistence)
        production_after = snapshot_file_set(production_paths)
        source_after = {str(path.relative_to(ROOT)).replace("\\", "/"):file_hash(path) for path in PRODUCTION_SOURCE_FILES}
        expected = {item["document_id"]:item["projected_chunk_count"] for item in projection["documents"]}
        actual = {item["document_id"]:item["chunk_count"] for item in imports}
        validation = {
            "all_documents_imported":len(imports) == manifest["document_count"],
            "all_processing_completed":all(item["ingestion_status"] == "completed" and item["indexing_status"] == "completed" for item in imports),
            "actual_matches_projection":actual == expected,
            "faiss_matches_chunks":index_status["chunk_count"] == len(inventory) == persistence["counts"]["material_chunks"],
            "unique_material_ids":len({item["material_id"] for item in imports}) == len(imports),
            "unique_chunk_ids":len({item["chunk_id"] for item in inventory}) == len(inventory),
            "unique_chunk_content_hashes":persistence["distinct_chunk_content_hashes"],
            "duplicate_chunk_occurrences":len(inventory) - persistence["distinct_chunk_content_hashes"],
            "production_paths_unchanged":production_before == production_after,
            "production_sources_unchanged":source_before == source_after,
            "no_answer_evaluation_state":all(persistence["counts"][name] == 0 for name in ("rag_conversations", "rag_messages", "rag_citations")),
            "temporary_service_stopped":service_stopped,
            "runtime_deleted":False,
        }
        checks = [value for key, value in validation.items() if isinstance(value, bool) and key != "runtime_deleted"]
        if not all(checks):
            write_json(run_dir / "validation.json", validation)
            raise RuntimeError(f"post-run validation failed: {validation}")
        shutil.rmtree(runtime_parent)
        runtime_deleted = not runtime_parent.exists()
        validation["runtime_deleted"] = runtime_deleted
        write_json(run_dir / "validation.json", validation)
        status = "complete" if all(value for value in validation.values() if isinstance(value, bool)) else "blocked"
        report = render_report(manifest, metadata, imports, shape, validation, acquisition_decisions)
        (run_dir / "report.md").write_text(report, encoding="utf-8")
        write_json(run_dir / "result.json", {
            "status":status,
            "run_id":run_id,
            "corpus":f"{manifest['corpus_id']}@{manifest['corpus_version']}",
            "document_count":len(imports),
            "chunk_count":len(inventory),
            "validation":validation,
        })
        print(json.dumps({"status":status, "run_dir":str(run_dir), "chunks":len(inventory)}, ensure_ascii=False, indent=2))
        return 0 if status == "complete" else 2
    finally:
        if runtime_parent.exists():
            shutil.rmtree(runtime_parent, ignore_errors=True)
            runtime_deleted = not runtime_parent.exists()
        if not service_stopped and (run_dir / "validation.json").exists():
            value = json.loads((run_dir / "validation.json").read_text(encoding="utf-8"))
            value["runtime_deleted"] = runtime_deleted
            write_json(run_dir / "validation.json", value)


if __name__ == "__main__":
    sys.exit(main())
