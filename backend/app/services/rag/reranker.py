from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from threading import RLock
from typing import Any, Protocol

from app.core.config import Settings

RERANKER_MODEL_ID = "BAAI/bge-reranker-v2-m3"
RERANKER_REVISION = "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
RERANKER_TOKEN_CAP = 1024
RERANKER_CANDIDATE_CAP = 18
REQUIRED_MODEL_FILES = (
    "config.json",
    "model.safetensors",
    "sentencepiece.bpe.model",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
)


class RerankerUnavailable(RuntimeError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class RerankCandidate:
    identity: str
    dense_rank: int
    text: str


@dataclass(frozen=True, slots=True)
class RerankScore:
    identity: str
    dense_rank: int
    rank: int
    raw_logit: float
    truncated: bool
    input_tokens: int


@dataclass(frozen=True, slots=True)
class RerankBatch:
    scores: tuple[RerankScore, ...]
    pair_count: int
    batch_count: int
    device: str
    dtype: str


@dataclass(frozen=True, slots=True)
class RerankerStatus:
    state: str
    load_count: int
    load_attempt_count: int
    inference_count: int
    device: str | None
    dtype: str | None
    failure_reason: str | None


class Reranker(Protocol):
    device: str
    dtype: str

    def rerank(
        self, query: str, candidates: Sequence[RerankCandidate]
    ) -> RerankBatch: ...


class RerankerGateway(Protocol):
    def rerank(
        self, query: str, candidates: Sequence[RerankCandidate]
    ) -> RerankBatch: ...

    def status(self) -> RerankerStatus: ...


@dataclass(frozen=True, slots=True)
class _PairTokens:
    query_token_ids: tuple[int, ...]
    chunk_token_ids: tuple[int, ...]
    truncated: bool
    total_tokens: int


def _enforce_pair_token_budget(
    query_token_ids: Sequence[int],
    chunk_token_ids: Sequence[int],
    *,
    special_token_count: int,
) -> _PairTokens:
    if len(query_token_ids) + special_token_count > RERANKER_TOKEN_CAP:
        raise RerankerUnavailable("query_exceeds_token_cap")
    allowed_chunk_tokens = (
        RERANKER_TOKEN_CAP - len(query_token_ids) - special_token_count
    )
    truncated_chunk = tuple(chunk_token_ids[:allowed_chunk_tokens])
    return _PairTokens(
        query_token_ids=tuple(query_token_ids),
        chunk_token_ids=truncated_chunk,
        truncated=len(chunk_token_ids) > allowed_chunk_tokens,
        total_tokens=len(query_token_ids) + len(truncated_chunk) + special_token_count,
    )


def _build_xlm_roberta_pair_feature(
    tokenizer: Any, pair: _PairTokens
) -> dict[str, list[int]]:
    if tokenizer.num_special_tokens_to_add(pair=True) != 4:
        raise RerankerUnavailable("unexpected_tokenizer_pair_template")
    if tokenizer.bos_token_id is None or tokenizer.eos_token_id is None:
        raise RerankerUnavailable("missing_tokenizer_boundary_ids")
    input_ids = [
        tokenizer.bos_token_id,
        *pair.query_token_ids,
        tokenizer.eos_token_id,
        tokenizer.eos_token_id,
        *pair.chunk_token_ids,
        tokenizer.eos_token_id,
    ]
    if len(input_ids) != pair.total_tokens or len(input_ids) > RERANKER_TOKEN_CAP:
        raise RerankerUnavailable("pair_token_contract_violation")
    return {"input_ids": input_ids, "attention_mask": [1] * len(input_ids)}


class CudaFp32Reranker:
    def __init__(self, snapshot_path: Path, *, device: str):
        snapshot_path = snapshot_path.resolve()
        if snapshot_path.name != RERANKER_REVISION:
            raise RerankerUnavailable("model_revision_mismatch")
        if not snapshot_path.is_dir():
            raise RerankerUnavailable("model_snapshot_missing")
        if any(not (snapshot_path / name).is_file() for name in REQUIRED_MODEL_FILES):
            raise RerankerUnavailable("model_snapshot_incomplete")

        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            if not device.startswith("cuda") or not torch.cuda.is_available():
                raise RerankerUnavailable("cuda_unavailable")
            torch.backends.cuda.matmul.allow_tf32 = False
            torch.backends.cudnn.allow_tf32 = False
            torch.set_float32_matmul_precision("highest")
            torch_device = torch.device(device)
            tokenizer = AutoTokenizer.from_pretrained(
                str(snapshot_path),
                local_files_only=True,
                trust_remote_code=False,
            )
            model = AutoModelForSequenceClassification.from_pretrained(
                str(snapshot_path),
                local_files_only=True,
                trust_remote_code=False,
            )
            model.to(device=torch_device, dtype=torch.float32)
            model.eval()
            parameter = next(model.parameters())
            if parameter.device.type != "cuda":
                raise RerankerUnavailable("unexpected_model_device")
            if parameter.dtype != torch.float32 or any(
                item.dtype != torch.float32 for item in model.parameters()
            ):
                raise RerankerUnavailable("unexpected_model_dtype")
            if model.training:
                raise RerankerUnavailable("model_not_in_eval_mode")
        except RerankerUnavailable:
            raise
        except Exception as exc:
            raise RerankerUnavailable("model_init_failed") from exc

        self.snapshot_path = snapshot_path
        self.tokenizer = tokenizer
        self.model = model
        self._torch = torch
        self.device = str(parameter.device)
        self.dtype = "float32"

    def rerank(
        self, query: str, candidates: Sequence[RerankCandidate]
    ) -> RerankBatch:
        if len(candidates) > RERANKER_CANDIDATE_CAP:
            raise RerankerUnavailable("candidate_cap_exceeded")
        if len({item.identity for item in candidates}) != len(candidates):
            raise RerankerUnavailable("duplicate_candidate_identity")
        if not candidates:
            return RerankBatch((), 0, 0, self.device, self.dtype)

        try:
            query_ids = self.tokenizer.encode(query, add_special_tokens=False)
            features: list[dict[str, list[int]]] = []
            pairs: list[_PairTokens] = []
            for candidate in candidates:
                chunk_ids = self.tokenizer.encode(
                    candidate.text, add_special_tokens=False
                )
                pair = _enforce_pair_token_budget(
                    query_ids,
                    chunk_ids,
                    special_token_count=self.tokenizer.num_special_tokens_to_add(
                        pair=True
                    ),
                )
                features.append(_build_xlm_roberta_pair_feature(self.tokenizer, pair))
                pairs.append(pair)
            batch = self.tokenizer.pad(
                features, padding=True, return_tensors="pt"
            )
            batch = {key: value.to(self.device) for key, value in batch.items()}
            with self._torch.inference_mode(), self._torch.autocast(
                device_type="cuda", enabled=False
            ):
                logits = self.model(**batch, return_dict=True).logits
            raw_logits = logits.reshape(-1).detach().to("cpu").tolist()
        except RerankerUnavailable:
            raise
        except Exception as exc:
            raise RerankerUnavailable("inference_failed") from exc
        if len(raw_logits) != len(candidates):
            raise RerankerUnavailable("logit_count_mismatch")

        ordered = sorted(
            zip(candidates, raw_logits, pairs, strict=True),
            key=lambda row: (-float(row[1]), row[0].dense_rank, row[0].identity),
        )
        scores = tuple(
            RerankScore(
                identity=candidate.identity,
                dense_rank=candidate.dense_rank,
                rank=rank,
                raw_logit=float(logit),
                truncated=pair.truncated,
                input_tokens=pair.total_tokens,
            )
            for rank, (candidate, logit, pair) in enumerate(ordered, start=1)
        )
        return RerankBatch(
            scores=scores,
            pair_count=len(candidates),
            batch_count=1,
            device=self.device,
            dtype=self.dtype,
        )


class RerankerProvider:
    def __init__(self, factory: Callable[[], Reranker]):
        self._factory = factory
        self._lock = RLock()
        self._instance: Reranker | None = None
        self._state = "unloaded"
        self._failure_reason: str | None = None
        self._load_count = 0
        self._load_attempt_count = 0
        self._inference_count = 0

    def rerank(
        self, query: str, candidates: Sequence[RerankCandidate]
    ) -> RerankBatch:
        with self._lock:
            if self._state == "degraded":
                raise RerankerUnavailable(self._failure_reason or "reranker_degraded")
            if self._instance is None:
                self._load_attempt_count += 1
                try:
                    self._instance = self._factory()
                except RerankerUnavailable as exc:
                    self._state = "degraded"
                    self._failure_reason = exc.reason
                    raise
                except Exception as exc:
                    self._state = "degraded"
                    self._failure_reason = "model_init_failed"
                    raise RerankerUnavailable("model_init_failed") from exc
                self._load_count += 1
                self._state = "active"
            try:
                result = self._instance.rerank(query, candidates)
            except RerankerUnavailable as exc:
                self._state = "degraded"
                self._failure_reason = exc.reason
                raise
            except Exception as exc:
                self._state = "degraded"
                self._failure_reason = "inference_failed"
                raise RerankerUnavailable("inference_failed") from exc
            self._inference_count += 1
            return result

    def status(self) -> RerankerStatus:
        with self._lock:
            return RerankerStatus(
                state=self._state,
                load_count=self._load_count,
                load_attempt_count=self._load_attempt_count,
                inference_count=self._inference_count,
                device=self._instance.device if self._instance else None,
                dtype=self._instance.dtype if self._instance else None,
                failure_reason=self._failure_reason,
            )


@lru_cache(maxsize=1)
def _cached_reranker_provider(model_path: str, device: str) -> RerankerProvider:
    snapshot_path = Path(model_path)
    return RerankerProvider(
        lambda: CudaFp32Reranker(snapshot_path, device=device)
    )


def build_reranker_provider(settings: Settings) -> RerankerProvider | None:
    if not settings.rag_reranker_enabled:
        return None
    if settings.rag_reranker_model_path is None:
        raise ValueError("RAG_RERANKER_MODEL_PATH is required when reranking is enabled")
    return _cached_reranker_provider(
        str(settings.rag_reranker_model_path.resolve()),
        settings.rag_reranker_device,
    )
