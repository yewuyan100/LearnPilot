"""Evaluation-only observers around the unmodified production RAG application.

Every wrapper delegates to the production implementation without changing inputs or
outputs.  The JSONL trace deliberately excludes credentials, headers, environment
variables, database rows, and files outside the frozen evaluation corpus.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import Lock
from time import perf_counter
from typing import Any
from urllib.parse import urlparse

import httpx

from app.api.deps import get_embedder, get_llm_provider
from app.core.config import get_settings
from app.main import app
from app.services.embedding.service import build_embedder
from app.services.llm.openai_compatible import OpenAICompatibleProvider
import app.services.llm.openai_compatible as provider_module
import app.services.rag.service as rag_service_module


TRACE_PATH = Path(os.environ["RAG_BASELINE_TELEMETRY_PATH"])
_TRACE_LOCK = Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError(type(value).__name__)


def _record(event: str, **payload: Any) -> None:
    row = {"at": _utc_now(), "event": event, **payload}
    encoded = json.dumps(row, ensure_ascii=False, default=_jsonable, separators=(",", ":"))
    with _TRACE_LOCK:
        TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with TRACE_PATH.open("a", encoding="utf-8") as handle:
            handle.write(encoded + "\n")


class RecordingEmbedder:
    def __init__(self, delegate):
        self.delegate = delegate
        self.model_name = delegate.model_name
        self.model_revision = delegate.model_revision
        self.normalized = delegate.normalized

    @property
    def dimension(self) -> int:
        return self.delegate.dimension

    def embed_documents(self, texts: list[str]):
        started = perf_counter()
        try:
            result = self.delegate.embed_documents(texts)
        except Exception as exc:
            _record(
                "embedding.documents.error",
                text_count=len(texts),
                error_type=type(exc).__name__,
                elapsed_ms=round((perf_counter() - started) * 1000, 2),
            )
            raise
        _record(
            "embedding.documents.completed",
            text_count=len(texts),
            character_count=sum(len(item) for item in texts),
            dimension=int(result.shape[-1]) if result.ndim else None,
            elapsed_ms=round((perf_counter() - started) * 1000, 2),
        )
        return result

    def embed_query(self, query: str):
        started = perf_counter()
        try:
            result = self.delegate.embed_query(query)
        except Exception as exc:
            _record(
                "embedding.query.error",
                query_sha256=sha256(query.encode("utf-8")).hexdigest(),
                query_chars=len(query),
                error_type=type(exc).__name__,
                elapsed_ms=round((perf_counter() - started) * 1000, 2),
            )
            raise
        _record(
            "embedding.query.completed",
            query=query,
            query_sha256=sha256(query.encode("utf-8")).hexdigest(),
            query_chars=len(query),
            dimension=int(result.shape[-1]) if result.ndim else None,
            elapsed_ms=round((perf_counter() - started) * 1000, 2),
        )
        return result


class RecordingProvider:
    def __init__(self, delegate):
        self.delegate = delegate
        self.model_name = delegate.model_name

    def generate_structured(self, *, messages, schema, temperature=None, max_output_tokens=None):
        started = perf_counter()
        _record(
            "llm.structured.started",
            schema=schema.__name__,
            messages=messages,
            messages_sha256=sha256(
                json.dumps(messages, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
            requested_temperature=temperature,
            requested_max_output_tokens=max_output_tokens,
        )
        try:
            result = self.delegate.generate_structured(
                messages=messages,
                schema=schema,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            )
        except Exception as exc:
            _record(
                "llm.structured.error",
                schema=schema.__name__,
                error_type=type(exc).__name__,
                error_code=getattr(exc, "code", None),
                error_reason=getattr(exc, "reason", None),
                elapsed_ms=round((perf_counter() - started) * 1000, 2),
            )
            raise
        _record(
            "llm.structured.completed",
            schema=schema.__name__,
            parsed_draft=result.value.model_dump(mode="json"),
            model=result.model,
            usage=asdict(result.usage),
            provider_latency_ms=result.latency_ms,
            observed_latency_ms=round((perf_counter() - started) * 1000, 2),
            finish_reason=result.finish_reason,
        )
        return result


_real_decode = provider_module._decode_json_content


def _recording_decode(raw: str):
    _record(
        "llm.raw_draft.received",
        raw_draft=raw,
        raw_draft_sha256=sha256(raw.encode("utf-8")).hexdigest(),
        raw_draft_chars=len(raw),
    )
    return _real_decode(raw)


provider_module._decode_json_content = _recording_decode


_real_http_post = httpx.Client.post


def _recording_http_post(self, url, *args, **kwargs):
    started = perf_counter()
    try:
        response = _real_http_post(self, url, *args, **kwargs)
    except Exception as exc:
        _record(
            "llm.transport.error",
            endpoint_path=str(url),
            error_type=type(exc).__name__,
            elapsed_ms=round((perf_counter() - started) * 1000, 2),
        )
        raise
    safe_provider_metadata: dict[str, Any] = {}
    try:
        body = response.json()
        choice = (body.get("choices") or [{}])[0]
        safe_provider_metadata = {
            "model": body.get("model"),
            "usage": {
                "input_tokens": (body.get("usage") or {}).get("prompt_tokens"),
                "output_tokens": (body.get("usage") or {}).get("completion_tokens"),
                "total_tokens": (body.get("usage") or {}).get("total_tokens"),
            },
            "finish_reason": choice.get("finish_reason"),
        }
    except (ValueError, TypeError, AttributeError, IndexError):
        safe_provider_metadata = {}
    _record(
        "llm.transport.completed",
        endpoint_path=str(url),
        status_code=response.status_code,
        elapsed_ms=round((perf_counter() - started) * 1000, 2),
        **safe_provider_metadata,
    )
    return response


httpx.Client.post = _recording_http_post


_real_rewrite = rag_service_module.rewrite_query


def _recording_rewrite(**kwargs):
    started = perf_counter()
    result = _real_rewrite(**kwargs)
    _record(
        "rag.rewrite.completed",
        original_question=kwargs["question"],
        retrieval_query=result.query,
        used_history_messages=result.used_history_messages,
        rewritten=result.rewritten,
        elapsed_ms=round((perf_counter() - started) * 1000, 2),
    )
    return result


rag_service_module.rewrite_query = _recording_rewrite


_real_retrieve = rag_service_module.retrieve_sources


def _recording_retrieve(**kwargs):
    started = perf_counter()
    result = _real_retrieve(**kwargs)
    _record(
        "rag.retrieval.completed",
        query=result.query,
        top_k=kwargs["top_k"],
        material_ids=kwargs["material_ids"],
        candidate_count=result.candidate_count,
        retrieved_count=result.retrieved_count,
        filtered_count=result.filtered_count,
        final_count=result.final_count,
        index_version=result.index_version,
        duration_ms=result.duration_ms,
        observed_latency_ms=round((perf_counter() - started) * 1000, 2),
        unavailable_reason=result.unavailable_reason,
        selected_sources=[asdict(source) for source in result.sources],
    )
    return result


rag_service_module.retrieve_sources = _recording_retrieve


def _recording_embedder_dependency():
    return RecordingEmbedder(build_embedder(get_settings()))


def _recording_provider_dependency():
    settings = get_settings()
    if not settings.llm_configured:
        return None
    return RecordingProvider(OpenAICompatibleProvider(settings))


app.dependency_overrides[get_embedder] = _recording_embedder_dependency
app.dependency_overrides[get_llm_provider] = _recording_provider_dependency


@app.get("/api/eval/dense-baseline-config")
def dense_baseline_config() -> dict[str, Any]:
    """Return an allow-listed effective configuration; never return a secret."""
    settings = get_settings()
    return {
        "llm_configured": settings.llm_configured,
        "provider": settings.llm_provider,
        "host": urlparse(settings.llm_base_url or "").hostname,
        "model": settings.llm_model,
        "structured_model": settings.llm_structured_model_name,
        "temperature": settings.llm_temperature,
        "structured_reasoning_enabled": settings.llm_structured_reasoning_enabled,
        "structured_max_output_tokens": settings.llm_structured_max_output_tokens,
        "timeout_seconds": settings.llm_timeout_seconds,
        "max_retries": settings.llm_max_retries,
        "embedding_model": settings.embedding_model_name,
        "embedding_revision": settings.embedding_model_revision,
        "embedding_local_files_only": settings.embedding_local_files_only,
        "embedding_device": settings.embedding_device,
        "embedding_normalize": settings.embedding_normalize,
        "search_top_k_max": settings.search_top_k_max,
        "rag_top_k_default": settings.rag_top_k_default,
        "rag_min_score": settings.rag_min_score,
        "rag_max_sources": settings.rag_max_sources,
        "rag_max_context_chars": settings.rag_max_context_chars,
        "rag_max_chunk_chars": settings.rag_max_chunk_chars,
        "rag_prompt_version": settings.rag_prompt_version,
        "rag_rewrite_prompt_version": settings.rag_rewrite_prompt_version,
        "rag_query_rewrite_enabled": settings.rag_query_rewrite_enabled,
    }

_record("instrumentation.ready", contract="observe-only-v1")
