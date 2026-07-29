"""Evaluate a running V3 API without reading SQLite or FAISS directly."""

from argparse import ArgumentParser
import json
import os
from pathlib import Path
import subprocess
from statistics import mean, median
from tempfile import TemporaryDirectory
from time import perf_counter

import httpx

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "evals" / "rag_eval_dataset.json"


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = min(len(ordered) - 1, round((len(ordered) - 1) * quantile))
    return ordered[position]


def inline_labels(text: str) -> set[str]:
    import re

    return set(re.findall(r"\[(S\d+)\]", text))


def evaluate(base_url: str, dataset_path: Path) -> dict:
    cases = json.loads(dataset_path.read_text(encoding="utf-8"))
    results = []
    with httpx.Client(base_url=base_url.rstrip("/"), timeout=90) as client:
        status_response = client.get("/rag/status")
        status_response.raise_for_status()
        status_data = status_response.json()
        if not status_data["llm_configured"]:
            raise RuntimeError("LLM 尚未配置，不能执行真实 RAG 评测")
        for case in cases:
            conversation_response = client.post(
                "/rag/conversations",
                json={"title": f"评测：{case['id']}"},
            )
            conversation_response.raise_for_status()
            conversation_id = conversation_response.json()["id"]
            started = perf_counter()
            response = client.post(
                f"/rag/conversations/{conversation_id}/ask",
                json={
                    "question": case["question"],
                    "request_id": f"eval-{case['id']}",
                    "top_k": 6,
                },
            )
            total_ms = round((perf_counter() - started) * 1000, 2)
            if response.status_code != 200:
                results.append(
                    {
                        "id": case["id"],
                        "valid_output": False,
                        "http_status": response.status_code,
                        "total_ms": total_ms,
                    }
                )
                continue
            body = response.json()
            message = body["assistant_message"]
            citations = message["citations"]
            cited_files = {item["original_filename"] for item in citations}
            expected = set(case["expected_sources"])
            declared = {item["source_label"] for item in citations}
            inline = inline_labels(message["content"])
            results.append(
                {
                    "id": case["id"],
                    "valid_output": True,
                    "expected_answerable": case["answerable"],
                    "actual_answerable": message["answerable"],
                    "retrieval_hit": bool(expected & cited_files) if expected else True,
                    "source_precision": (
                        len(expected & cited_files) / len(cited_files)
                        if cited_files
                        else (1.0 if not expected else 0.0)
                    ),
                    "citation_valid": inline == declared and inline == {
                        item["source_label"] for item in citations
                    },
                    "citation_coverage": (
                        1.0 if (not message["answerable"] or bool(inline)) else 0.0
                    ),
                    "retrieval_ms": body["retrieval"]["duration_ms"],
                    "llm_ms": message["latency_ms"] or 0,
                    "total_ms": total_ms,
                }
            )
    valid = [item for item in results if item.get("valid_output")]
    answerable = [item for item in valid if item["expected_answerable"]]
    refusal = [item for item in valid if not item["expected_answerable"]]
    totals = [item["total_ms"] for item in valid]
    metrics = {
        "case_count": len(cases),
        "retrieval_hit_at_k": mean(
            [float(item["retrieval_hit"]) for item in answerable]
        )
        if answerable
        else 0.0,
        "source_precision": mean([item["source_precision"] for item in answerable])
        if answerable
        else 0.0,
        "citation_validity_rate": mean(
            [float(item["citation_valid"]) for item in valid]
        )
        if valid
        else 0.0,
        "citation_coverage_rate": mean(
            [item["citation_coverage"] for item in valid]
        )
        if valid
        else 0.0,
        "refusal_accuracy": mean(
            [float(item["actual_answerable"] is False) for item in refusal]
        )
        if refusal
        else 0.0,
        "answerable_accuracy": mean(
            [float(item["actual_answerable"] is True) for item in answerable]
        )
        if answerable
        else 0.0,
        "invalid_output_rate": 1 - (len(valid) / len(cases)),
        "latency_ms": {
            "retrieval_average": mean([item["retrieval_ms"] for item in valid])
            if valid
            else 0.0,
            "llm_average": mean([item["llm_ms"] for item in valid]) if valid else 0.0,
            "total_average": mean(totals) if totals else 0.0,
            "total_p50": median(totals) if totals else 0.0,
            "total_p95": percentile(totals, 0.95),
        },
    }
    return {"status": "completed", "metrics": metrics, "cases": results}


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--isolated",
        action="store_true",
        help="在临时数据库、上传目录和索引中启动本地 API 并导入评测夹具",
    )
    parser.add_argument("--port", type=int, default=8013)
    args = parser.parse_args()
    if args.isolated:
        from acceptance_v3 import (
            ALEMBIC,
            BACKEND,
            live_backend,
            upload_fixtures,
        )

        with TemporaryDirectory(
            prefix="personal-learning-v3-evaluation-",
            ignore_cleanup_errors=True,
        ) as temp:
            temp_dir = Path(temp)
            environment = os.environ.copy()
            environment.update(
                {
                    "DATABASE_URL": (
                        f"sqlite:///{(temp_dir / 'evaluation.sqlite3').as_posix()}"
                    ),
                    "UPLOAD_DIR": str(temp_dir / "uploads"),
                    "FAISS_INDEX_PATH": str(temp_dir / "materials.faiss"),
                    "FAISS_MANIFEST_PATH": str(
                        temp_dir / "materials.faiss.manifest.json"
                    ),
                    "EMBEDDING_MODEL_NAME": "BAAI/bge-m3",
                    "EMBEDDING_MODEL_REVISION": "local-cache",
                    "EMBEDDING_LOCAL_FILES_ONLY": "true",
                    "EMBEDDING_DEVICE": "cpu",
                    "EMBEDDING_NORMALIZE": "true",
                    "APP_VERSION": "3.0.0",
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
            with live_backend(
                port=args.port,
                environment=environment,
                log_path=temp_dir / "backend.log",
            ) as base_url:
                with httpx.Client(base_url=base_url, timeout=180) as client:
                    upload_fixtures(client)
                report = evaluate(base_url, args.dataset)
    else:
        report = evaluate(args.base_url, args.dataset)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
