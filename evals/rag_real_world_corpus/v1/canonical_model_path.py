from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path


RERANKER_MODEL_PATH_ENV = "RAG_RERANKER_MODEL_PATH"
EXPECTED_MODEL_REVISION = "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
EXPECTED_MODEL_FILES = (
    ".gitattributes",
    "config.json",
    "model.safetensors",
    "README.md",
    "sentencepiece.bpe.model",
    "special_tokens_map.json",
    "tokenizer_config.json",
    "tokenizer.json",
)
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _dotenv_value(path: Path, key: str) -> str | None:
    if not path.is_file():
        return None
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() != key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        return value or None
    return None


def resolve_canonical_reranker_model_path(
    explicit_path: str | Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    repository_root: Path = REPOSITORY_ROOT,
    require_complete_snapshot: bool = True,
) -> Path:
    """Resolve the frozen reranker snapshot without a machine path in source."""
    environment = os.environ if environ is None else environ
    configured = (
        str(explicit_path)
        if explicit_path is not None
        else environment.get(RERANKER_MODEL_PATH_ENV)
        or _dotenv_value(repository_root / ".env", RERANKER_MODEL_PATH_ENV)
    )
    if not configured:
        raise RuntimeError(
            f"Set {RERANKER_MODEL_PATH_ENV} to the absolute frozen reranker snapshot path"
        )

    model_path = Path(configured).expanduser()
    if not model_path.is_absolute():
        model_path = repository_root / model_path
    model_path = model_path.resolve()

    if model_path.name != EXPECTED_MODEL_REVISION:
        raise RuntimeError(
            f"{RERANKER_MODEL_PATH_ENV} must select revision {EXPECTED_MODEL_REVISION}; "
            f"got {model_path}"
        )
    if require_complete_snapshot:
        missing = [name for name in EXPECTED_MODEL_FILES if not (model_path / name).is_file()]
        if missing:
            raise FileNotFoundError(
                f"Incomplete reranker snapshot at {model_path}; missing: {', '.join(missing)}"
            )
    return model_path

