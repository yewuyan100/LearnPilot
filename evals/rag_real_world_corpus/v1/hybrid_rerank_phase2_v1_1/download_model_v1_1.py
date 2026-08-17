from __future__ import annotations

import argparse
import json
from pathlib import Path

from huggingface_hub import snapshot_download

from experiment import RERANKER_MODEL_ID, RERANKER_REVISION


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    args = parser.parse_args()
    snapshot = Path(
        snapshot_download(
            repo_id=RERANKER_MODEL_ID,
            revision=RERANKER_REVISION,
            cache_dir=str(args.cache.resolve()),
        )
    ).resolve()
    if snapshot.name != RERANKER_REVISION:
        raise RuntimeError(
            f"resolved revision mismatch: {snapshot.name} != {RERANKER_REVISION}"
        )
    print(
        json.dumps(
            {
                "model_id": RERANKER_MODEL_ID,
                "resolved_revision": snapshot.name,
                "snapshot": str(snapshot),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
