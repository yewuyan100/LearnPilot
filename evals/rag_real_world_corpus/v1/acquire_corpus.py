"""Acquire pinned, licensed upstream documents into Real-world Corpus V1."""

from __future__ import annotations

from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
CORPUS = HERE / "corpus"
UPSTREAM_DEFAULT = ROOT / ".tmp" / "rag-real-world-upstreams-20260813"
ACQUIRED_AT = "2026-08-13T12:33:34.949269+00:00"

SOURCES: list[dict[str, Any]] = [
    {"id":"rw-rag-bge-m3","title":"BGE-M3: Multi-Functionality Retrieval","cluster":"rag_retrieval","format":"md","project":"FlagEmbedding","repo":"https://github.com/FlagOpen/FlagEmbedding","commit":"7ed43d67ec03fbe5c31c0992dbfa941fb1860549","path":"research/BGE_M3/README.md","license":"MIT","license_path":"LICENSE"},
    {"id":"rw-rag-faiss-overview","title":"FAISS Overview and Index Trade-offs","cluster":"rag_retrieval","format":"md","project":"FAISS","repo":"https://github.com/facebookresearch/faiss","commit":"80a16564f86530dbf0bfaf96c2b71feffeb5093f","path":"README.md","license":"MIT","license_path":"LICENSE"},
    {"id":"rw-agent-langgraph-overview","title":"LangGraph Repository Overview","cluster":"agent_engineering","format":"md","project":"LangGraph","repo":"https://github.com/langchain-ai/langgraph","commit":"644815f9e5bc52ad8f7a5227a456227e9c3e639b","path":"README.md","license":"MIT","license_path":"LICENSE"},
    {"id":"rw-agent-persistence","title":"LangGraph Persistence and Checkpointing","cluster":"agent_engineering","format":"txt","project":"LangChain Documentation","repo":"https://github.com/langchain-ai/docs","commit":"47062bb8dc8eb56fb7cdd99201028e1d0177b19b","path":"src/oss/langgraph/persistence.mdx","license":"MIT","license_path":"LICENSE"},
    {"id":"rw-agent-interrupts","title":"LangGraph Interrupts and Human-in-the-loop","cluster":"agent_engineering","format":"pdf","project":"LangChain Documentation","repo":"https://github.com/langchain-ai/docs","commit":"47062bb8dc8eb56fb7cdd99201028e1d0177b19b","path":"src/oss/langgraph/interrupts.mdx","license":"MIT","license_path":"LICENSE"},
    {"id":"rw-backend-fastapi-async","title":"FastAPI Concurrency and async await","cluster":"ai_app_backend","format":"md","project":"FastAPI","repo":"https://github.com/fastapi/fastapi","commit":"f336ff831c4af3d4f625c2593a27b1e0cae93eb7","path":"docs/en/docs/async.md","license":"MIT","license_path":"LICENSE"},
    {"id":"rw-backend-fastapi-dependencies","title":"FastAPI Dependency Injection","cluster":"ai_app_backend","format":"md","project":"FastAPI","repo":"https://github.com/fastapi/fastapi","commit":"f336ff831c4af3d4f625c2593a27b1e0cae93eb7","path":"docs/en/docs/tutorial/dependencies/index.md","license":"MIT","license_path":"LICENSE"},
    {"id":"rw-backend-fastapi-errors","title":"FastAPI Error Handling","cluster":"ai_app_backend","format":"md","project":"FastAPI","repo":"https://github.com/fastapi/fastapi","commit":"f336ff831c4af3d4f625c2593a27b1e0cae93eb7","path":"docs/en/docs/tutorial/handling-errors.md","license":"MIT","license_path":"LICENSE"},
    {"id":"rw-eval-ragas-workflow","title":"Ragas RAG Evaluation Workflow","cluster":"evaluation_reliability","format":"md","project":"Ragas","repo":"https://github.com/vibrantlabsai/ragas","commit":"298b68274234c060deacab3cf5fb52aa3a20e885","path":"docs/getstarted/rag_eval.md","license":"Apache-2.0","license_path":"LICENSE"},
    {"id":"rw-eval-context-precision","title":"Ragas Context Precision","cluster":"evaluation_reliability","format":"md","project":"Ragas","repo":"https://github.com/vibrantlabsai/ragas","commit":"298b68274234c060deacab3cf5fb52aa3a20e885","path":"docs/concepts/metrics/available_metrics/context_precision.md","license":"Apache-2.0","license_path":"LICENSE"},
    {"id":"rw-eval-otel-traces","title":"OpenTelemetry Traces and Spans","cluster":"evaluation_reliability","format":"pdf","project":"OpenTelemetry Website","repo":"https://github.com/open-telemetry/opentelemetry.io","commit":"0480294d04e49023b559d33d4546a34ce738fcab","path":"content/en/docs/concepts/signals/traces.md","license":"CC-BY-4.0","license_path":"LICENSE"},
]

REPO_DIR = {"FlagEmbedding":"FlagEmbedding","Sentence Transformers":"sentence-transformers","FAISS":"faiss","LangGraph":"langgraph","LangChain Documentation":"langchain-docs","FastAPI":"fastapi","Pydantic":"pydantic","Ragas":"ragas","OpenTelemetry Website":"opentelemetry.io"}
NOTICE_PATHS = {"Sentence Transformers": "NOTICE.txt"}


def hash_bytes(data: bytes) -> str:
    return sha256(data).hexdigest()


def wrap_line(line: str, width: int = 92) -> list[str]:
    if not line:
        return [""]
    return [line[index:index + width] for index in range(0, len(line), width)]


def render_verbatim_pdf(text: str, output: Path) -> dict[str, Any]:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen.canvas import Canvas

    font_name = "Consolas"
    font_path = Path("C:/Windows/Fonts/consola.ttf")
    pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
    canvas = Canvas(str(output), pagesize=A4, pageCompression=1, invariant=1)
    canvas.setTitle(output.stem)
    canvas.setAuthor("Official upstream source; deterministic corpus representation")
    page_width, page_height = A4
    margin, font_size, leading = 42, 7.5, 10
    page = 1
    y = page_height - margin
    canvas.setFont(font_name, font_size)
    for original in text.splitlines():
        for line in wrap_line(original):
            if y < margin:
                canvas.drawRightString(page_width - margin, 22, str(page))
                canvas.showPage(); page += 1; y = page_height - margin
                canvas.setFont(font_name, font_size)
            canvas.drawString(margin, y, line)
            y -= leading
    canvas.drawRightString(page_width - margin, 22, str(page))
    canvas.save()
    return {"method":"verbatim Markdown/MDX source rendered as line-wrapped monospaced PDF","content_rewritten":False,"renderer":"reportlab","renderer_version":__import__("reportlab").Version,"font":"Consolas (embedded TrueType)","line_wrap_columns":92,"page_size":"A4","page_count":page}


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ensure_upstreams(upstream_root: Path) -> None:
    upstream_root.mkdir(parents=True, exist_ok=True)
    projects = {
        item["project"]:{"repository":item["repo"], "commit":item["commit"]}
        for item in SOURCES
    }
    for project, record in projects.items():
        repo_dir = upstream_root / REPO_DIR[project]
        if not (repo_dir / ".git").exists():
            subprocess.run(["git", "init", str(repo_dir)], check=True)
            subprocess.run(
                ["git", "-C", str(repo_dir), "remote", "add", "origin", record["repository"]],
                check=True,
            )
        actual = subprocess.run(
            ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
        )
        if actual.returncode == 0 and actual.stdout.strip() == record["commit"]:
            continue
        subprocess.run(
            ["git", "-C", str(repo_dir), "fetch", "--depth=1", "origin", record["commit"]],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(repo_dir), "checkout", "--detach", "FETCH_HEAD"],
            check=True,
        )


def main(upstream_root: Path = UPSTREAM_DEFAULT) -> None:
    CORPUS.mkdir(parents=True, exist_ok=True)
    license_dir = HERE / "provenance" / "licenses"
    license_dir.mkdir(parents=True, exist_ok=True)
    documents = []
    licenses: dict[str, dict[str, Any]] = {}
    repositories: dict[str, dict[str, str]] = {}
    for source in SOURCES:
        repo_dir = upstream_root / REPO_DIR[source["project"]]
        original = repo_dir / source["path"]
        license_file = repo_dir / source["license_path"]
        if not original.is_file() or not license_file.is_file():
            raise RuntimeError(f"missing pinned source or license: {source['id']}")
        actual_commit = subprocess.run(
            ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if actual_commit != source["commit"]:
            raise RuntimeError(
                f"upstream commit mismatch for {source['project']}: "
                f"expected {source['commit']}, got {actual_commit}"
            )
        repositories[source["project"]] = {
            "repository": source["repo"],
            "commit_sha": source["commit"],
        }
        license_name = REPO_DIR[source["project"]] + "-" + source["license"] + ".txt"
        license_output = license_dir / license_name
        shutil.copyfile(license_file, license_output)
        license_record: dict[str, Any] = {
            "project": source["project"],
            "spdx_identifier": source["license"],
            "repository_path": str(license_output.relative_to(ROOT)).replace("\\", "/"),
            "source": f"{source['repo']}/blob/{source['commit']}/{source['license_path']}",
            "sha256": hash_bytes(license_output.read_bytes()),
        }
        notice_path = NOTICE_PATHS.get(source["project"])
        if notice_path:
            notice_source = repo_dir / notice_path
            if not notice_source.is_file():
                raise RuntimeError(f"missing NOTICE for {source['project']}")
            notice_output = license_dir / (REPO_DIR[source["project"]] + "-NOTICE.txt")
            shutil.copyfile(notice_source, notice_output)
            license_record["notice"] = {
                "repository_path": str(notice_output.relative_to(ROOT)).replace("\\", "/"),
                "source": f"{source['repo']}/blob/{source['commit']}/{notice_path}",
                "sha256": hash_bytes(notice_output.read_bytes()),
            }
        licenses[source["project"]] = license_record
        data = original.read_bytes()
        extension = source["format"]
        output = CORPUS / f"{source['id']}.{extension}"
        if extension == "pdf":
            transformation = render_verbatim_pdf(data.decode("utf-8"), output)
        else:
            shutil.copyfile(original, output)
            transformation = {"method":"verbatim byte copy" if extension == original.suffix.lstrip(".") else "verbatim byte copy with container extension changed to UTF-8 TXT","content_rewritten":False}
        corpus_data = output.read_bytes()
        documents.append({
            "document_id": source["id"], "title": source["title"], "topic_cluster": source["cluster"],
            "source_format": extension, "repository_path": str(output.relative_to(ROOT)).replace("\\","/"),
            "upstream_project": source["project"], "upstream_repository": source["repo"],
            "upstream_commit_sha": source["commit"], "upstream_path_or_source": source["path"],
            "retrieved_at": ACQUIRED_AT, "license": source["license"],
            "license_source": f"{source['repo']}/blob/{source['commit']}/{source['license_path']}",
            "license_repository_path": license_record["repository_path"],
            "license_sha256": license_record["sha256"],
            "attribution": f"{source['project']} contributors; source retained under {source['license']}",
            "source_sha256": hash_bytes(data), "corpus_sha256": hash_bytes(corpus_data),
            "transformation": transformation, "language":"en", "notes":"Official pinned upstream documentation; no semantic rewriting."
        })
    manifest = {
        "schema_version":"1.0.0",
        "corpus_id":"learnpilot-rag-real-world-corpus",
        "corpus_version":"v1",
        "acquired_at":ACQUIRED_AT,
        "document_count":len(documents),
        "format_plan":{
            name: sum(item["source_format"] == name for item in documents)
            for name in ("md", "txt", "pdf")
        },
        "topic_plan":{
            name: sum(item["topic_cluster"] == name for item in documents)
            for name in ("rag_retrieval", "agent_engineering", "ai_app_backend", "evaluation_reliability")
        },
        "licenses":sorted(licenses.values(), key=lambda item: item["project"]),
        "documents":documents,
    }
    write_json(HERE / "corpus_manifest.json", manifest)
    write_json(HERE / "acquisition_lock.json", {
        "schema_version":"1.0.0",
        "acquired_at":ACQUIRED_AT,
        "repositories":sorted(
            ({"project": project, **record} for project, record in repositories.items()),
            key=lambda item: item["project"],
        ),
    })
    write_json(HERE / "source_decisions.json", {
        "schema_version":"1.0.0",
        "accepted":[
            {"document_id": item["id"], "project": item["project"], "path": item["path"], "reason":"official, pinned, licensed, substantial, and useful for an overlapping topic family"}
            for item in SOURCES
        ],
        "rejected":[
            {"candidate":"BAAI/bge-m3 Hugging Face model card", "reason":"rejected as a second copy of the selected official FlagEmbedding BGE-M3 material; avoids semantic duplication"},
            {"candidate":"FAISS GitHub wiki pages", "reason":"rejected because the main-repository README provides a cleaner commit-pinned provenance chain"},
            {"candidate":"Sentence Transformers semantic-search README", "reason":"license-eligible but rejected after canonical chunk projection produced 170 chunks and made retrieval 53.46% of the corpus while evaluation was only 6.07%"},
            {"candidate":"Sentence Transformers retrieve-and-rerank README", "reason":"license-eligible but rejected because its projected fragmentation still left retrieval significantly dominant; the persistence material already satisfies the TXT format slot"},
            {"candidate":"LangGraph orchestration overview MDX", "reason":"license-eligible but rejected after canonical chunk projection to keep the agent cluster balanced with the larger interrupts PDF"},
            {"candidate":"Pydantic models documentation", "reason":"license-eligible but rejected after canonical chunk projection produced 187 chunks and caused backend-cluster dominance"},
            {"candidate":"OpenTelemetry observability primer", "reason":"rejected as broader and more overlapping than the selected traces/spans material"},
        ],
    })
    print(json.dumps({"status":"acquired","document_count":len(documents)}, ensure_ascii=False))


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--upstream-root", type=Path, default=UPSTREAM_DEFAULT)
    parser.add_argument(
        "--fetch-missing",
        action="store_true",
        help="Create/fetch exact upstream commits before acquisition (network required).",
    )
    arguments = parser.parse_args()
    if arguments.fetch_missing:
        ensure_upstreams(arguments.upstream_root)
    main(arguments.upstream_root)
