"""Capture hashes for task-external artifacts that this Gold task must not mutate."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from gold_common import CORPUS_ROOT, GOLD_ROOT, REPO_ROOT, write_json


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def relative_hashes(paths: list[Path]) -> dict[str, str]:
    return {
        path.relative_to(REPO_ROOT).as_posix(): digest(path)
        for path in sorted(set(paths)) if path.is_file()
    }


def main() -> None:
    frozen_corpus_paths = [
        path for path in CORPUS_ROOT.rglob("*")
        if path.is_file() and GOLD_ROOT not in path.parents
    ]
    controlled_v2_root = REPO_ROOT / "evals" / "rag_demo_corpus" / "v1" / "contracts" / "v2"
    controlled_v2_paths = [path for path in controlled_v2_root.rglob("*") if path.is_file()]
    production_paths = [
        REPO_ROOT / "backend" / "app" / "api" / "routes" / "materials.py",
        REPO_ROOT / "backend" / "app" / "api" / "routes" / "rag.py",
        REPO_ROOT / "backend" / "app" / "core" / "config.py",
        REPO_ROOT / "backend" / "app" / "services" / "material_processing" / "pipeline.py",
    ]
    for directory in ("rag", "embedding", "vector_store"):
        production_paths.extend((REPO_ROOT / "backend" / "app" / "services" / directory).glob("*.py"))
    write_json(GOLD_ROOT / "immutability_baseline.json", {
        "schema_version": "1.0.0",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "scope_note": "Captured after Gold-only draft work and before merge/review/finalization; all listed paths are outside the writable Gold seam.",
        "frozen_real_world_corpus": relative_hashes(frozen_corpus_paths),
        "controlled_corpus_v2": relative_hashes(controlled_v2_paths),
        "production_rag": relative_hashes(production_paths),
    })


if __name__ == "__main__":
    main()
