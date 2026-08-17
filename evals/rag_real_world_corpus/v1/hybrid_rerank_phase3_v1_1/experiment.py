from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import perf_counter
from typing import Any, Callable, Protocol, Sequence
from urllib.parse import urlparse

import httpx
from pydantic import ValidationError


HERE = Path(__file__).resolve().parent
V1 = HERE.parent
ROOT = V1.parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.llm.openai_compatible import (  # noqa: E402
    _decode_json_content,
    _schema_messages,
)
from app.services.llm.schemas import RagGroundedAnswerDraft  # noqa: E402
from app.services.rag.prompts import (  # noqa: E402
    ANSWER_SYSTEM_PROMPT,
    REPAIR_SYSTEM_PROMPT,
    answer_messages,
    build_context,
    repair_messages,
)
from app.services.rag.types import RagSource  # noqa: E402
from app.services.rag.validation import (  # noqa: E402
    render_grounded_answer,
    validate_grounded_draft,
)


DESIGN_VERSION = "V1.1"
ABLATION_DESIGN_SHA256 = (
    "442bedce1c43b27b3557b0055708342edd278e98bcac0c12a68c1390fe88f655"
)
PHASE2_RUN_ID = "20260814T095542Z-1317c6a7"
PROVIDER = "openai_compatible"
PROVIDER_HOST = "api.deepseek.com"
ENDPOINT_PATH = "chat/completions"
MODEL_NAME = "deepseek-v4-flash"
PROMPT_VERSION = "rag-answer-v2-evidence-binding"
TEMPERATURE = 0.1
REASONING_ENABLED = False
MAX_OUTPUT_TOKENS = 2400
TIMEOUT_SECONDS = 60
MAX_RETRIES = 2
GROUNDING_REPAIR_LIMIT = 1
MAX_NORMAL_GENERATION_REQUESTS = 216
ARMS = ("B", "C", "D")


class ContractViolation(RuntimeError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def json_sha256(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def text_sha256(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class GenerationContract:
    provider: str
    provider_host: str
    endpoint_path: str
    model: str
    prompt_version: str
    temperature: float
    reasoning_enabled: bool
    max_output_tokens: int
    timeout_seconds: int
    max_retries: int
    grounding_repair_limit: int
    answer_system_prompt_sha256: str
    repair_system_prompt_sha256: str
    structured_schema_sha256: str
    production_prompt_file_sha256: str
    production_schema_file_sha256: str
    production_provider_file_sha256: str
    identity: str

    @classmethod
    def from_settings(cls, settings: Any) -> "GenerationContract":
        host = urlparse(settings.llm_base_url or "").hostname
        observed = {
            "provider": settings.llm_provider,
            "provider_host": host,
            "endpoint_path": ENDPOINT_PATH,
            "model": settings.llm_structured_model_name,
            "prompt_version": settings.rag_prompt_version,
            "temperature": settings.llm_temperature,
            "reasoning_enabled": settings.llm_structured_reasoning_enabled,
            "max_output_tokens": settings.llm_structured_max_output_tokens,
            "timeout_seconds": settings.llm_timeout_seconds,
            "max_retries": settings.llm_max_retries,
            "grounding_repair_limit": GROUNDING_REPAIR_LIMIT,
            "answer_system_prompt_sha256": text_sha256(ANSWER_SYSTEM_PROMPT),
            "repair_system_prompt_sha256": text_sha256(REPAIR_SYSTEM_PROMPT),
            "structured_schema_sha256": json_sha256(
                RagGroundedAnswerDraft.model_json_schema()
            ),
            "production_prompt_file_sha256": file_sha256(
                BACKEND / "app/services/rag/prompts.py"
            ),
            "production_schema_file_sha256": file_sha256(
                BACKEND / "app/services/llm/schemas.py"
            ),
            "production_provider_file_sha256": file_sha256(
                BACKEND / "app/services/llm/openai_compatible.py"
            ),
        }
        expected = {
            "provider": PROVIDER,
            "provider_host": PROVIDER_HOST,
            "endpoint_path": ENDPOINT_PATH,
            "model": MODEL_NAME,
            "prompt_version": PROMPT_VERSION,
            "temperature": TEMPERATURE,
            "reasoning_enabled": REASONING_ENABLED,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "timeout_seconds": TIMEOUT_SECONDS,
            "max_retries": MAX_RETRIES,
            "grounding_repair_limit": GROUNDING_REPAIR_LIMIT,
            "production_prompt_file_sha256": (
                "fbd463bb3789f21885f832a47f1f1a67a7d4a31bd76de1ad38744f690e31c49c"
            ),
            "production_provider_file_sha256": (
                "129bdd27d85296d960eb12bebc3dfe06ca85f2ad3a043eb4e8673adedaf20e68"
            ),
        }
        mismatches = {
            key: {"expected": value, "observed": observed.get(key)}
            for key, value in expected.items()
            if observed.get(key) != value
        }
        if not settings.llm_configured:
            mismatches["llm_configured"] = {"expected": True, "observed": False}
        if not settings.llm_api_key or not settings.llm_api_key.get_secret_value().strip():
            mismatches["api_key_present"] = {"expected": True, "observed": False}
        if mismatches:
            raise ContractViolation(f"generation contract drift: {mismatches}")
        identity = json_sha256(observed)
        return cls(**observed, identity=identity)

    def as_public_dict(self) -> dict[str, Any]:
        return asdict(self)


def _source_score(arm: str, candidate: dict[str, Any]) -> tuple[float, str]:
    if arm == "B":
        value = candidate.get("fusion_score")
        kind = "fusion_score"
    else:
        value = candidate.get("reranker_score")
        kind = "reranker_raw_logit"
    if not isinstance(value, (int, float)):
        raise ContractViolation(
            f"selected {arm} candidate {candidate.get('identity')} has no {kind}"
        )
    return float(value), kind


def _candidate_identity(candidate: dict[str, Any]) -> str:
    return (
        f"{candidate['document_id']}:{candidate['chunk_index']}:"
        f"{candidate['content_hash']}"
    )


def freeze_phase2_contexts(
    *,
    phase2_run_dir: Path,
    gold_cases: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    gold_by_id = {row["case_id"]: row for row in gold_cases}
    if len(gold_by_id) != 72:
        raise ContractViolation(f"expected 72 unique Gold cases, got {len(gold_by_id)}")
    records: list[dict[str, Any]] = []
    for arm in ARMS:
        trace_path = phase2_run_dir / f"arm_{arm}/candidate_traces.jsonl"
        rows = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
        if len(rows) != 72 or len({row["case_id"] for row in rows}) != 72:
            raise ContractViolation(f"Phase 2 arm {arm} does not contain 72 unique cases")
        by_id = {row["case_id"]: row for row in rows}
        for sequence, gold in enumerate(gold_cases, start=1):
            case_id = gold["case_id"]
            row = by_id.get(case_id)
            if row is None:
                raise ContractViolation(f"Phase 2 arm {arm} is missing {case_id}")
            if (
                row.get("design_version") != DESIGN_VERSION
                or row.get("ablation_design_sha256") != ABLATION_DESIGN_SHA256
                or row.get("run_id") != PHASE2_RUN_ID
                or row.get("arm") != arm
            ):
                raise ContractViolation(f"Phase 2 trace metadata drift for {arm}/{case_id}")
            question = gold["question"]
            if row.get("effective_query") != question:
                raise ContractViolation(
                    f"fresh-case query drift for {arm}/{case_id}: "
                    f"{row.get('effective_query')!r} != {question!r}"
                )
            selected_order = list(row.get("selected") or [])
            if len(selected_order) > 6 or len(selected_order) != len(set(selected_order)):
                raise ContractViolation(f"invalid selected order for {arm}/{case_id}")
            candidate_by_id = {item["identity"]: item for item in row["candidates"]}
            selected_rows: list[dict[str, Any]] = []
            sources: list[RagSource] = []
            for order, identity in enumerate(selected_order, start=1):
                candidate = candidate_by_id.get(identity)
                if candidate is None or not candidate.get("selected"):
                    raise ContractViolation(
                        f"selected identity missing from candidate trace: {arm}/{case_id}/{identity}"
                    )
                if _candidate_identity(candidate) != identity:
                    raise ContractViolation(f"stable identity mismatch: {arm}/{case_id}/{identity}")
                raw_text = candidate["raw_text"]
                if text_sha256(raw_text) != candidate["content_hash"]:
                    raise ContractViolation(f"content hash mismatch: {arm}/{case_id}/{identity}")
                if candidate.get("selected_text_chars") != len(raw_text):
                    raise ContractViolation(f"selected text length mismatch: {arm}/{case_id}/{identity}")
                score, score_kind = _source_score(arm, candidate)
                source_label = f"S{order}"
                source = RagSource(
                    source_label=source_label,
                    rank=order,
                    score=score,
                    chunk_id=candidate["chunk_id"],
                    material_id=candidate["material_id"],
                    original_filename=candidate["filename"],
                    chunk_index=candidate["chunk_index"],
                    content=raw_text,
                    page_number=candidate["page_number"],
                    section_title=candidate["section_title"],
                )
                sources.append(source)
                selected_rows.append(
                    {
                        "context_order": order,
                        "source_label": source_label,
                        "identity": identity,
                        "document_id": candidate["document_id"],
                        "chunk_index": candidate["chunk_index"],
                        "content_hash": candidate["content_hash"],
                        "filename": candidate["filename"],
                        "page_number": candidate["page_number"],
                        "section_title": candidate["section_title"],
                        "raw_text": raw_text,
                        "material_id": candidate["material_id"],
                        "chunk_id": candidate["chunk_id"],
                        "evidence_ids": candidate["evidence_ids"],
                        "score": score,
                        "score_kind": score_kind,
                    }
                )
            context_text = build_context(sources)
            messages = answer_messages(question, sources)
            records.append(
                {
                    "design_version": DESIGN_VERSION,
                    "ablation_design_sha256": ABLATION_DESIGN_SHA256,
                    "phase2_run_id": PHASE2_RUN_ID,
                    "arm": arm,
                    "case_id": case_id,
                    "sequence": sequence,
                    "question": question,
                    "query_digest": text_sha256(question),
                    "selected_candidate_identities": selected_order,
                    "selected_sources": selected_rows,
                    "context_text": context_text,
                    "context_digest": text_sha256(context_text),
                    "context_user_message": messages[1]["content"],
                    "generation_messages": messages,
                    "generation_messages_sha256": json_sha256(messages),
                    "source_count": len(sources),
                    "context_raw_text_chars": sum(len(item.content) for item in sources),
                }
            )
    if len(records) != MAX_NORMAL_GENERATION_REQUESTS:
        raise ContractViolation(f"expected 216 frozen contexts, got {len(records)}")
    return records


def sources_from_frozen_context(record: dict[str, Any]) -> list[RagSource]:
    sources = [
        RagSource(
            source_label=item["source_label"],
            rank=item["context_order"],
            score=item["score"],
            chunk_id=item["chunk_id"],
            material_id=item["material_id"],
            original_filename=item["filename"],
            chunk_index=item["chunk_index"],
            content=item["raw_text"],
            page_number=item["page_number"],
            section_title=item["section_title"],
        )
        for item in record["selected_sources"]
    ]
    context_text = build_context(sources)
    messages = answer_messages(record["question"], sources)
    checks = {
        "context_digest": text_sha256(context_text),
        "query_digest": text_sha256(record["question"]),
        "generation_messages_sha256": json_sha256(messages),
    }
    for key, observed in checks.items():
        if record.get(key) != observed:
            raise ContractViolation(
                f"CONTEXT_FREEZE_MISMATCH {record['arm']}/{record['case_id']}/{key}"
            )
    if record.get("context_text") != context_text or record.get("generation_messages") != messages:
        raise ContractViolation(
            f"CONTEXT_FREEZE_MISMATCH {record['arm']}/{record['case_id']}/text"
        )
    return sources


@dataclass(frozen=True, slots=True)
class TransportResponse:
    status_code: int
    body_text: str
    elapsed_ms: float
    response_headers: dict[str, str]


class GenerationTransport(Protocol):
    def post(
        self,
        *,
        base_url: str,
        endpoint_path: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout_seconds: int,
    ) -> TransportResponse: ...


class HttpxGenerationTransport:
    _SAFE_RESPONSE_HEADERS = (
        "x-request-id",
        "x-ds-trace-id",
        "request-id",
        "cf-ray",
    )

    def post(
        self,
        *,
        base_url: str,
        endpoint_path: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout_seconds: int,
    ) -> TransportResponse:
        started = perf_counter()
        with httpx.Client(
            base_url=base_url.rstrip("/") + "/",
            timeout=timeout_seconds,
            follow_redirects=False,
        ) as client:
            response = client.post(endpoint_path, headers=headers, json=payload)
        return TransportResponse(
            status_code=response.status_code,
            body_text=response.text,
            elapsed_ms=round((perf_counter() - started) * 1000, 3),
            response_headers={
                key: response.headers[key]
                for key in self._SAFE_RESPONSE_HEADERS
                if key in response.headers
            },
        )


@dataclass(slots=True)
class StructuredCall:
    call_kind: str
    parsed: RagGroundedAnswerDraft | None
    parse_status: str
    validation_reason: str | None
    attempts: list[dict[str, Any]]
    model: str | None
    response_id: str | None
    finish_reason: str | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    provider_failure: bool
    timeout_failure: bool


LedgerSink = Callable[[dict[str, Any]], None]


class DeepSeekGenerationAdapter:
    """Exact frozen generation contract behind one context-in/result-out interface."""

    def __init__(
        self,
        *,
        settings: Any,
        contract: GenerationContract,
        transport: GenerationTransport,
        ledger_sink: LedgerSink,
    ):
        self.settings = settings
        self.contract = contract
        self.transport = transport
        self.ledger_sink = ledger_sink
        self.normal_generation_calls = 0
        self.total_http_requests = 0

    def _payload(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.contract.model,
            "messages": _schema_messages(messages, RagGroundedAnswerDraft),
            "max_tokens": self.contract.max_output_tokens,
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
            "temperature": self.contract.temperature,
        }
        return payload

    def _structured_call(
        self,
        *,
        messages: list[dict[str, str]],
        call_kind: str,
        request_prefix: str,
    ) -> StructuredCall:
        payload = self._payload(messages)
        payload_digest = json_sha256(payload)
        attempts: list[dict[str, Any]] = []
        last_timeout = False
        for index in range(self.contract.max_retries + 1):
            attempt_number = index + 1
            local_request_id = f"{request_prefix}-{call_kind}-{attempt_number}"
            started_event = {
                "event": "http_request_started",
                "local_request_id": local_request_id,
                "call_kind": call_kind,
                "attempt": attempt_number,
                "provider_host": self.contract.provider_host,
                "endpoint_path": self.contract.endpoint_path,
                "model": self.contract.model,
                "payload_sha256": payload_digest,
            }
            self.ledger_sink(started_event)
            self.total_http_requests += 1
            attempt: dict[str, Any] = {
                **started_event,
                "request_payload": payload if attempt_number == 1 else None,
                "same_payload_as_first_attempt": attempt_number > 1,
            }
            try:
                response = self.transport.post(
                    base_url=self.settings.llm_base_url or "",
                    endpoint_path=self.contract.endpoint_path,
                    headers={
                        "Authorization": (
                            "Bearer "
                            + self.settings.llm_api_key.get_secret_value()
                        ),
                        "Content-Type": "application/json",
                    },
                    payload=payload,
                    timeout_seconds=self.contract.timeout_seconds,
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_timeout = isinstance(exc, httpx.TimeoutException)
                attempt.update(
                    {
                        "status": "transport_error",
                        "error_type": type(exc).__name__,
                        "timeout": last_timeout,
                    }
                )
                attempts.append(attempt)
                self.ledger_sink(
                    {
                        "event": "http_request_completed",
                        "local_request_id": local_request_id,
                        "status": "transport_error",
                        "error_type": type(exc).__name__,
                    }
                )
                if index < self.contract.max_retries:
                    continue
                return StructuredCall(
                    call_kind, None, "provider_failure", "transport_error", attempts,
                    None, None, None, None, None, None, True, last_timeout
                )

            attempt.update(
                {
                    "status_code": response.status_code,
                    "http_elapsed_ms": response.elapsed_ms,
                    "response_headers": response.response_headers,
                    "raw_provider_response": response.body_text,
                    "raw_provider_response_sha256": text_sha256(response.body_text),
                }
            )
            self.ledger_sink(
                {
                    "event": "http_request_completed",
                    "local_request_id": local_request_id,
                    "status": "http_response",
                    "status_code": response.status_code,
                    "raw_provider_response_sha256": text_sha256(response.body_text),
                }
            )
            retryable = response.status_code in {408, 409, 429} or response.status_code >= 500
            if retryable:
                attempt["status"] = "retryable_http_error"
                attempts.append(attempt)
                if index < self.contract.max_retries:
                    continue
                return StructuredCall(
                    call_kind, None, "provider_failure", f"http_{response.status_code}",
                    attempts, None, None, None, None, None, None, True,
                    response.status_code == 408
                )
            if response.status_code >= 400:
                attempt["status"] = "nonretryable_http_error"
                attempts.append(attempt)
                return StructuredCall(
                    call_kind, None, "provider_failure", f"http_{response.status_code}",
                    attempts, None, None, None, None, None, None, True, False
                )
            try:
                body = json.loads(response.body_text)
                choice = body["choices"][0]
                message = choice["message"]
                finish_reason = choice.get("finish_reason")
                raw = message.get("content")
                if isinstance(raw, list):
                    raw = "".join(
                        item.get("text", "") for item in raw if isinstance(item, dict)
                    )
                usage = body.get("usage") or {}
                attempt.update(
                    {
                        "status": "provider_response",
                        "response_id": body.get("id"),
                        "provider_model": body.get("model"),
                        "finish_reason": finish_reason,
                        "raw_content": raw,
                        "raw_content_sha256": (
                            text_sha256(raw) if isinstance(raw, str) else None
                        ),
                        "usage": {
                            "input_tokens": usage.get("prompt_tokens"),
                            "output_tokens": usage.get("completion_tokens"),
                            "total_tokens": usage.get("total_tokens"),
                        },
                    }
                )
                attempts.append(attempt)
                if (body.get("model") or self.contract.model) != self.contract.model:
                    return StructuredCall(
                        call_kind, None, "model_mismatch", "provider_model_mismatch",
                        attempts, body.get("model"), body.get("id"), finish_reason,
                        usage.get("prompt_tokens"), usage.get("completion_tokens"),
                        usage.get("total_tokens"), True, False
                    )
                if finish_reason == "length":
                    return StructuredCall(
                        call_kind, None, "parse_failure", "finish_reason_length",
                        attempts, body.get("model") or self.contract.model, body.get("id"),
                        finish_reason, usage.get("prompt_tokens"),
                        usage.get("completion_tokens"), usage.get("total_tokens"), False, False
                    )
                if not isinstance(raw, str) or not raw.strip():
                    return StructuredCall(
                        call_kind, None, "parse_failure", "empty_content", attempts,
                        body.get("model") or self.contract.model, body.get("id"), finish_reason,
                        usage.get("prompt_tokens"), usage.get("completion_tokens"),
                        usage.get("total_tokens"), False, False
                    )
                decoded = _decode_json_content(raw)
                parsed = RagGroundedAnswerDraft.model_validate(decoded)
                return StructuredCall(
                    call_kind, parsed, "parsed", None, attempts,
                    body.get("model") or self.contract.model, body.get("id"), finish_reason,
                    usage.get("prompt_tokens"), usage.get("completion_tokens"),
                    usage.get("total_tokens"), False, False
                )
            except (json.JSONDecodeError, ValidationError, KeyError, TypeError, IndexError) as exc:
                if not attempts or attempts[-1] is not attempt:
                    attempts.append(attempt)
                reason = "invalid_json" if isinstance(exc, json.JSONDecodeError) else "schema_or_provider_response_invalid"
                attempt["parse_error_type"] = type(exc).__name__
                return StructuredCall(
                    call_kind, None, "parse_failure", reason, attempts,
                    attempt.get("provider_model"), attempt.get("response_id"),
                    attempt.get("finish_reason"),
                    (attempt.get("usage") or {}).get("input_tokens"),
                    (attempt.get("usage") or {}).get("output_tokens"),
                    (attempt.get("usage") or {}).get("total_tokens"), False, False
                )
        raise AssertionError("unreachable retry loop")

    def generate(self, context: dict[str, Any], *, phase3_run_id: str) -> dict[str, Any]:
        if self.normal_generation_calls >= MAX_NORMAL_GENERATION_REQUESTS:
            raise ContractViolation("normal generation request cap would be exceeded")
        sources = sources_from_frozen_context(context)
        prefix = (
            f"{phase3_run_id}-{context['arm']}-{context['sequence']:03d}-"
            f"{text_sha256(context['case_id'])[:8]}"
        )
        self.normal_generation_calls += 1
        started = perf_counter()
        initial = self._structured_call(
            messages=context["generation_messages"],
            call_kind="initial",
            request_prefix=prefix,
        )
        calls = [initial]
        parsed = initial.parsed
        validation_reason = initial.validation_reason
        invalid_draft: dict[str, Any] | None = None
        repair_attempted = False
        if initial.provider_failure:
            final_status = "FAILED"
            final_reason = validation_reason or "provider_failure"
        else:
            if parsed is not None:
                valid, validation_reason = validate_grounded_draft(parsed, sources)
                if valid:
                    final_status = "COMPLETED"
                    final_reason = None
                else:
                    invalid_draft = parsed.model_dump(mode="json")
                    final_status = "NEEDS_REPAIR"
                    final_reason = validation_reason
            else:
                final_status = "NEEDS_REPAIR"
                final_reason = validation_reason or "parse_failure"

        if final_status == "NEEDS_REPAIR":
            repair_attempted = True
            repair = self._structured_call(
                messages=repair_messages(
                    question=context["question"],
                    sources=sources,
                    invalid_draft=invalid_draft,
                    validation_reason=final_reason or "grounding_validation_failed",
                ),
                call_kind="repair",
                request_prefix=prefix,
            )
            calls.append(repair)
            parsed = repair.parsed
            if repair.provider_failure or parsed is None:
                final_status = "FAILED"
                final_reason = repair.validation_reason or "repair_parse_failure"
            else:
                valid, repaired_reason = validate_grounded_draft(parsed, sources)
                if not valid:
                    final_status = "FAILED"
                    final_reason = repaired_reason or "repair_grounding_validation_failed"
                else:
                    final_status = "COMPLETED"
                    final_reason = None

        rendered = render_grounded_answer(parsed, sources) if final_status == "COMPLETED" and parsed is not None else None
        attempts = [attempt for call in calls for attempt in call.attempts]
        input_tokens = sum(call.input_tokens or 0 for call in calls)
        output_tokens = sum(call.output_tokens or 0 for call in calls)
        total_tokens_values = [call.total_tokens for call in calls]
        total_tokens = (
            sum(value or 0 for value in total_tokens_values)
            if any(value is not None for value in total_tokens_values)
            else (input_tokens + output_tokens if input_tokens or output_tokens else None)
        )
        result: dict[str, Any] = {
            "design_version": DESIGN_VERSION,
            "ablation_design_sha256": ABLATION_DESIGN_SHA256,
            "phase2_run_id": PHASE2_RUN_ID,
            "phase3_run_id": phase3_run_id,
            "arm": context["arm"],
            "case_id": context["case_id"],
            "sequence": context["sequence"],
            "query_digest": context["query_digest"],
            "context_digest": context["context_digest"],
            "generation_contract_identity": self.contract.identity,
            "provider": self.contract.provider,
            "provider_host": self.contract.provider_host,
            "endpoint_class": "OpenAI-compatible chat/completions structured JSON",
            "model": self.contract.model,
            "local_request_id": prefix,
            "response_ids": [call.response_id for call in calls if call.response_id],
            "status": final_status,
            "failure_reason": final_reason,
            "parse_status": calls[-1].parse_status,
            "validation_status": "PASS" if final_status == "COMPLETED" else "FAIL",
            "repair_attempted": repair_attempted,
            "initial_validation_reason": (
                calls[0].validation_reason
                if calls[0].parsed is None
                else validate_grounded_draft(calls[0].parsed, sources)[1]
            ),
            "attempt_count": len(attempts),
            "structured_call_count": len(calls),
            "retry_count": sum(max(0, len(call.attempts) - 1) for call in calls),
            "timeout_count": sum(bool(call.timeout_failure) for call in calls),
            "provider_failure": any(call.provider_failure for call in calls),
            "attempts": attempts,
            "raw_provider_responses": [
                {
                    "local_request_id": attempt["local_request_id"],
                    "raw_provider_response": attempt.get("raw_provider_response"),
                    "raw_provider_response_sha256": attempt.get("raw_provider_response_sha256"),
                    "raw_content": attempt.get("raw_content"),
                    "raw_content_sha256": attempt.get("raw_content_sha256"),
                }
                for attempt in attempts
                if attempt.get("raw_provider_response") is not None
            ],
            "parsed_structured_result": (
                parsed.model_dump(mode="json") if parsed is not None else None
            ),
            "answerable": rendered.answerable if rendered is not None else None,
            "answer_markdown": rendered.answer_markdown if rendered is not None else None,
            "citation_ids": rendered.cited_source_ids if rendered is not None else [],
            "refusal_reason": rendered.refusal_reason if rendered is not None else None,
            "usage": {
                "input_tokens": input_tokens or None,
                "output_tokens": output_tokens or None,
                "total_tokens": total_tokens,
            },
            "latency_ms": round((perf_counter() - started) * 1000, 3),
            "fallback_used": False,
            "semantic_review_performed": False,
        }
        result["result_identity_sha256"] = json_sha256(result)
        return result


def validate_generation_result(
    result: dict[str, Any],
    context: dict[str, Any],
    *,
    contract_identity: str,
) -> list[str]:
    errors: list[str] = []
    expected_metadata = {
        "design_version": DESIGN_VERSION,
        "ablation_design_sha256": ABLATION_DESIGN_SHA256,
        "phase2_run_id": PHASE2_RUN_ID,
        "arm": context["arm"],
        "case_id": context["case_id"],
        "query_digest": context["query_digest"],
        "context_digest": context["context_digest"],
        "generation_contract_identity": contract_identity,
        "provider_host": PROVIDER_HOST,
        "model": MODEL_NAME,
    }
    for key, expected in expected_metadata.items():
        if result.get(key) != expected:
            errors.append(f"{key}_mismatch")
    payload = dict(result)
    identity = payload.pop("result_identity_sha256", None)
    if identity != json_sha256(payload):
        errors.append("result_identity_mismatch")
    if result.get("fallback_used") is not False:
        errors.append("fallback_used")
    if result.get("semantic_review_performed") is not False:
        errors.append("semantic_review_performed")
    if result.get("status") == "COMPLETED":
        try:
            draft = RagGroundedAnswerDraft.model_validate(
                result.get("parsed_structured_result")
            )
            sources = sources_from_frozen_context(context)
            valid, reason = validate_grounded_draft(draft, sources)
            if not valid:
                errors.append(f"grounding_invalid:{reason}")
            rendered = render_grounded_answer(draft, sources)
            if result.get("answer_markdown") != rendered.answer_markdown:
                errors.append("rendered_answer_mismatch")
            if result.get("citation_ids") != rendered.cited_source_ids:
                errors.append("citation_ids_mismatch")
            if result.get("answerable") != rendered.answerable:
                errors.append("answerability_mismatch")
        except (ValidationError, ValueError, ContractViolation) as exc:
            errors.append(f"parsed_result_invalid:{type(exc).__name__}")
    return errors
