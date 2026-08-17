import argparse
import json
import sys
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.services.embedding.service import build_embedder
from app.services.rag.retrieval import retrieve_sources
from app.services.vector_store.faiss_store import FaissStore


QUESTION = "根据这份资料帮我梳理最重要的内容。"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--material-id", type=int, default=1)
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()

    database = args.database.resolve()
    output = args.output.resolve()
    settings = Settings(database_url=f"sqlite:///{database.as_posix()}")
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    embedder = build_embedder(settings)
    real_faiss_load = FaissStore.load
    faiss_load_calls = 0

    def capture_faiss_load(self, **kwargs):
        nonlocal faiss_load_calls
        faiss_load_calls += 1
        return real_faiss_load(self, **kwargs)

    FaissStore.load = capture_faiss_load
    results = []
    with session_factory() as db:
        for run_number in range(1, args.runs + 1):
            faiss_before = faiss_load_calls
            model_before = getattr(embedder, "_model", None)
            started = perf_counter()
            retrieval = retrieve_sources(
                db=db,
                settings=settings,
                embedder=embedder,
                query=QUESTION,
                top_k=settings.rag_top_k_default,
                material_ids=[args.material_id],
            )
            total_ms = round((perf_counter() - started) * 1000)
            results.append(
                {
                    "run": run_number,
                    "phase": "cold" if run_number == 1 else "warm",
                    "source_count": len(retrieval.sources),
                    "source_ids": [source.source_label for source in retrieval.sources],
                    "chunk_ids": [source.chunk_id for source in retrieval.sources],
                    "material_ids": [source.material_id for source in retrieval.sources],
                    "scores": [round(source.score, 6) for source in retrieval.sources],
                    "candidate_count": retrieval.candidate_count,
                    "retrieved_count": retrieval.retrieved_count,
                    "filtered_count": retrieval.filtered_count,
                    "retrieval_duration_ms": retrieval.duration_ms,
                    "wall_latency_ms": total_ms,
                    "embedding_loaded_before": model_before is not None,
                    "embedding_loaded_after": getattr(embedder, "_model", None) is not None,
                    "embedding_model_reused": (
                        model_before is not None and model_before is getattr(embedder, "_model", None)
                    ),
                    "faiss_load_calls": faiss_load_calls - faiss_before,
                }
            )

    engine.dispose()
    report = {
        "question": QUESTION,
        "database_copy": str(database),
        "material_id": args.material_id,
        "embedding_model": settings.embedding_model_name,
        "runs": results,
        "retrieval_passed": all(
            run["source_count"] >= 1
            and all(material_id == args.material_id for material_id in run["material_ids"])
            for run in results
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["retrieval_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
