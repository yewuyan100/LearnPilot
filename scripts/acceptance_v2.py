"""Run the complete V2 knowledge-base acceptance against an isolated live API.

The script starts a temporary backend twice, so it verifies persistence and
restart loading without touching the normal development database, uploads, or
FAISS files. It never accesses SQLite directly.
"""

from argparse import ArgumentParser
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from typing import Iterator

import httpx
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
ALEMBIC = ROOT / ".venv" / "Scripts" / "alembic.exe"


def require(response: httpx.Response, expected: int) -> dict:
    if response.status_code != expected:
        raise RuntimeError(
            f"{response.request.method} {response.request.url} returned "
            f"{response.status_code}: {response.text}"
        )
    return response.json() if response.content else {}


def text_pdf_bytes(path: Path) -> bytes:
    writer = PdfWriter()
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)
    pages = [
        "Transport connects MCP peers through stdio or Streamable HTTP.",
        "Resources expose contextual data identified by a URI.",
    ]
    for text in pages:
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {NameObject("/F1"): font_ref}
                )
            }
        )
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    with path.open("wb") as destination:
        writer.write(destination)
    return path.read_bytes()


def wait_until_ready(base_url: str, process: subprocess.Popen, log_path: Path) -> None:
    deadline = time.monotonic() + 90
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
        tail = "\n".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-30:])
    raise RuntimeError(f"临时后端未能启动：{last_error}\n{tail}")


@contextmanager
def live_backend(
    *,
    port: int,
    environment: dict[str, str],
    log_path: Path,
) -> Iterator[str]:
    log_handle = log_path.open("a", encoding="utf-8")
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    process = subprocess.Popen(
        [
            str(PYTHON),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=BACKEND,
        env=environment,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        creationflags=creation_flags,
    )
    base_url = f"http://127.0.0.1:{port}/api"
    try:
        wait_until_ready(base_url, process, log_path)
        yield base_url
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        log_handle.close()


def upload(
    client: httpx.Client,
    *,
    filename: str,
    content: bytes,
    mime_type: str,
) -> dict:
    material = require(
        client.post(
            "/materials/upload",
            files={"file": (filename, content, mime_type)},
        ),
        201,
    )
    assert material["processing_status"] == "ready"
    assert material["ingestion_status"] == "pending"
    assert material["indexing_status"] == "pending"
    return material


def prepare_and_validate(base_url: str, pdf_content: bytes) -> dict:
    with httpx.Client(base_url=base_url, timeout=600) as client:
        require(client.get("/health"), 200)
        materials = [
            upload(
                client,
                filename="mcp-overview.txt",
                mime_type="text/plain",
                content=(
                    "Model Context Protocol connects AI applications with external systems.\n\n"
                    "MCP Servers expose Tools as executable actions and Resources as contextual data."
                ).encode("utf-8"),
            ),
            upload(
                client,
                filename="mcp-architecture.md",
                mime_type="text/markdown",
                content=(
                    "# Client and Server\n\n"
                    "The MCP Client initiates requests. The MCP Server provides capabilities.\n\n"
                    "## Prompts\n\nPrompts are reusable interaction templates.\n"
                ).encode("utf-8"),
            ),
            upload(
                client,
                filename="mcp-transport.pdf",
                mime_type="application/pdf",
                content=pdf_content,
            ),
        ]

        processed = []
        for material in materials:
            current = require(
                client.post(f"/materials/{material['id']}/process"),
                200,
            )
            assert current["ingestion_status"] == "completed"
            assert current["indexing_status"] == "completed"
            assert current["chunk_count"] > 0
            assert current["indexed_chunk_count"] == current["chunk_count"]
            processed.append(current)

        txt, markdown, pdf = processed
        txt_chunks = require(
            client.get(f"/materials/{txt['id']}/chunks?page=1&page_size=10"),
            200,
        )
        markdown_chunks = require(
            client.get(f"/materials/{markdown['id']}/chunks?page=1&page_size=10"),
            200,
        )
        pdf_chunks = require(
            client.get(f"/materials/{pdf['id']}/chunks?page=1&page_size=10"),
            200,
        )
        assert "Model Context Protocol" in txt_chunks["items"][0]["content"]
        assert markdown_chunks["items"][0]["section_title"] == "Client and Server"
        assert any(item["page_number"] == 2 for item in pdf_chunks["items"])

        rebuilt = require(client.post("/materials/index/rebuild"), 200)
        dimension = rebuilt["embedding_dimension"]
        assert isinstance(dimension, int) and dimension > 0
        total_chunks = sum(item["chunk_count"] for item in processed)
        assert rebuilt["chunk_count"] == total_chunks

        index_status = require(client.get("/materials/index/status"), 200)
        assert index_status["available"] is True
        assert index_status["stale"] is False
        assert index_status["chunk_count"] == total_chunks
        assert index_status["embedding_dimension"] == dimension

        transport_search = require(
            client.post(
                "/materials/search",
                json={
                    "query": "How do MCP peers communicate over standard input output?",
                    "top_k": 5,
                    "material_ids": [pdf["id"]],
                },
            ),
            200,
        )
        assert transport_search["results"]
        assert all(
            result["original_filename"] == "mcp-transport.pdf"
            for result in transport_search["results"]
        )
        assert any(result["page_number"] == 1 for result in transport_search["results"])

        section_search = require(
            client.post(
                "/materials/search",
                json={
                    "query": "Which component initiates requests?",
                    "top_k": 3,
                    "material_ids": [markdown["id"]],
                },
            ),
            200,
        )
        assert section_search["results"][0]["section_title"] == "Client and Server"

        return {
            "materials": processed,
            "embedding_model": rebuilt["model_name"],
            "embedding_dimension": dimension,
            "index_chunk_count": total_chunks,
            "txt_chunk_count": txt["chunk_count"],
        }


def validate_after_restart(base_url: str, state: dict) -> dict:
    materials = state["materials"]
    txt, _, pdf = materials
    with httpx.Client(base_url=base_url, timeout=600) as client:
        restored = require(client.get("/materials/index/status"), 200)
        assert restored["available"] is True
        assert restored["embedding_dimension"] == state["embedding_dimension"]
        assert restored["chunk_count"] == state["index_chunk_count"]

        restored_search = require(
            client.post(
                "/materials/search",
                json={"query": "MCP executable actions", "top_k": 5},
            ),
            200,
        )
        assert restored_search["results"]

        reprocessed = require(
            client.post(f"/materials/{txt['id']}/process"),
            200,
        )
        assert reprocessed["chunk_count"] == state["txt_chunk_count"]
        assert reprocessed["indexed_chunk_count"] == reprocessed["chunk_count"]
        refreshed = require(client.get("/materials/index/status"), 200)
        assert refreshed["available"] is True
        assert refreshed["stale"] is False

        require(client.delete(f"/materials/{pdf['id']}"), 204)
        after_delete = require(
            client.post(
                "/materials/search",
                json={"query": "stdio Streamable HTTP transport", "top_k": 20},
            ),
            200,
        )
        assert all(
            result["material_id"] != pdf["id"]
            for result in after_delete["results"]
        )
        remaining_status = require(client.get("/materials/index/status"), 200)
        assert remaining_status["chunk_count"] == (
            state["index_chunk_count"] - pdf["chunk_count"]
        )

        for material in materials:
            response = client.delete(f"/materials/{material['id']}")
            if material["id"] == pdf["id"]:
                assert response.status_code == 404
            else:
                assert response.status_code == 204
        assert require(client.get("/materials"), 200) == []
        empty_status = require(client.get("/materials/index/status"), 200)
        assert empty_status["available"] is False
        assert empty_status["chunk_count"] == 0

        return {
            "status": "passed",
            "embedding_model": state["embedding_model"],
            "embedding_dimension": state["embedding_dimension"],
            "materials_processed": len(materials),
            "index_available": restored["available"],
            "search_verified": True,
            "restart_verified": True,
            "reprocessing_idempotent": True,
            "deletion_verified": True,
        }


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("--port", type=int, default=8011)
    args = parser.parse_args()
    if not PYTHON.is_file() or not ALEMBIC.is_file():
        raise RuntimeError("未找到项目虚拟环境，请先按 README 安装后端依赖。")
    hf_home = os.environ.get("HF_HOME")
    if not hf_home:
        raise RuntimeError("请先设置 HF_HOME，使其指向本地 BAAI/bge-m3 缓存根目录。")

    result: dict
    temporary_path: Path
    with TemporaryDirectory(
        prefix="personal-learning-v2-acceptance-",
        ignore_cleanup_errors=True,
    ) as temp:
        temp_dir = Path(temp)
        temporary_path = temp_dir
        environment = os.environ.copy()
        environment.update(
            {
                "DATABASE_URL": f"sqlite:///{(temp_dir / 'acceptance.sqlite3').as_posix()}",
                "UPLOAD_DIR": str(temp_dir / "uploads"),
                "FAISS_INDEX_PATH": str(temp_dir / "materials.faiss"),
                "FAISS_MANIFEST_PATH": str(temp_dir / "materials.faiss.manifest.json"),
                "EMBEDDING_MODEL_NAME": "BAAI/bge-m3",
                "EMBEDDING_MODEL_REVISION": "local-cache",
                "EMBEDDING_LOCAL_FILES_ONLY": "true",
                "EMBEDDING_DEVICE": "cpu",
                "EMBEDDING_NORMALIZE": "true",
                "HF_HOME": hf_home,
                "HF_HUB_OFFLINE": "1",
            }
        )
        subprocess.run(
            [str(ALEMBIC), "upgrade", "head"],
            cwd=BACKEND,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        pdf_content = text_pdf_bytes(temp_dir / "mcp-transport.pdf")
        log_path = temp_dir / "backend.log"

        with live_backend(port=args.port, environment=environment, log_path=log_path) as url:
            state = prepare_and_validate(url, pdf_content)
        with live_backend(port=args.port, environment=environment, log_path=log_path) as url:
            result = validate_after_restart(url, state)

    for _ in range(20):
        if not temporary_path.exists():
            break
        try:
            shutil.rmtree(temporary_path)
        except PermissionError:
            time.sleep(0.25)
    if temporary_path.exists():
        raise RuntimeError(f"验收通过，但临时目录未能清理：{temporary_path.name}")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(
            json.dumps(
                {"status": "failed", "error": str(exc)},
                ensure_ascii=False,
                indent=2,
            )
        )
        sys.exit(1)
