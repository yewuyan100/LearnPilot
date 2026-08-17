import json
import logging
from time import perf_counter
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.services.llm.base import LLMUsage, StructuredLLMResult
from app.services.llm.errors import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMEmptyContentError,
    LLMNotConfiguredError,
    LLMOutputInvalidError,
    LLMOutputTruncatedError,
    LLMUnavailableError,
)

logger = logging.getLogger(__name__)
StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


def _decode_json_content(raw: str) -> object:
    content = raw.strip()
    if content.startswith("```") and content.endswith("```"):
        first_newline = content.find("\n")
        if first_newline >= 0:
            content = content[first_newline + 1 : -3].strip()
    return json.loads(content)


def _validation_reason(exc: ValidationError) -> str:
    items = []
    for error in exc.errors(include_input=False)[:8]:
        location = ".".join(str(item) for item in error["loc"])
        items.append(f"{location}:{error['type']}")
    return "schema_validation:" + ",".join(items)


def _schema_messages(
    messages: list[dict[str, str]], schema: type[StructuredModel]
) -> list[dict[str, str]]:
    contract = json.dumps(
        schema.model_json_schema(), ensure_ascii=False, separators=(",", ":")
    )
    instruction = (
        "Return JSON only. The complete JSON Schema contract is below. "
        "Do not omit required fields, add undeclared fields, or include markdown fences.\n"
        f"{contract}"
    )
    return [*messages, {"role": "system", "content": instruction}]


class OpenAICompatibleProvider:
    def __init__(self, settings: Settings):
        if not settings.llm_configured:
            raise LLMNotConfiguredError("LLM 尚未配置")
        self.settings = settings
        self.model_name = settings.llm_structured_model_name or ""

    def generate_structured(
        self,
        *,
        messages: list[dict[str, str]],
        schema: type[StructuredModel],
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> StructuredLLMResult:
        started = perf_counter()
        token_budget = (
            self.settings.llm_structured_max_output_tokens
            if max_output_tokens is None
            else max_output_tokens
        )
        payload = {
            "model": self.model_name,
            "messages": _schema_messages(messages, schema),
            "max_tokens": token_budget,
            "response_format": {"type": "json_object"},
            "thinking": {
                "type": (
                    "enabled"
                    if self.settings.llm_structured_reasoning_enabled
                    else "disabled"
                )
            },
        }
        if not self.settings.llm_structured_reasoning_enabled:
            payload["temperature"] = (
                self.settings.llm_temperature if temperature is None else temperature
            )
        headers = {
            "Authorization": f"Bearer {self.settings.llm_api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }
        last_error: Exception | None = None
        for attempt in range(self.settings.llm_max_retries + 1):
            try:
                with httpx.Client(
                    base_url=(self.settings.llm_base_url or "").rstrip("/") + "/",
                    timeout=self.settings.llm_timeout_seconds,
                ) as client:
                    response = client.post("chat/completions", headers=headers, json=payload)
                if response.status_code in {401, 403}:
                    raise LLMAuthenticationError("LLM authentication failed")
                if response.status_code in {408, 409, 429} or response.status_code >= 500:
                    raise LLMUnavailableError(
                        f"LLM service unavailable (HTTP {response.status_code})"
                    )
                if response.status_code >= 400:
                    raise LLMConfigurationError(
                        f"LLM request rejected (HTTP {response.status_code})"
                    )
                body = response.json()
                choice = body["choices"][0]
                message = choice["message"]
                finish_reason = choice.get("finish_reason")
                raw = message.get("content")
                if isinstance(raw, list):
                    raw = "".join(
                        item.get("text", "") for item in raw if isinstance(item, dict)
                    )

                logger.info(
                    "llm_structured_response | model=%s schema=%s attempt=%s "
                    "finish_reason=%s content_type=%s content_chars=%s "
                    "reasoning_chars=%s max_tokens=%s latency_ms=%s",
                    body.get("model") or self.model_name,
                    schema.__name__,
                    attempt + 1,
                    finish_reason,
                    type(raw).__name__,
                    len(raw) if isinstance(raw, str) else None,
                    len(message.get("reasoning_content") or ""),
                    token_budget,
                    round((perf_counter() - started) * 1000),
                )
                if finish_reason == "length":
                    raise LLMOutputTruncatedError(
                        "Structured output was truncated",
                        reason="finish_reason_length",
                    )
                if not isinstance(raw, str) or not raw.strip():
                    raise LLMEmptyContentError(
                        "Structured output content was empty",
                        reason="empty_content",
                    )
                try:
                    decoded = _decode_json_content(raw)
                except json.JSONDecodeError as exc:
                    raise LLMOutputInvalidError(
                        "Structured output was not valid JSON", reason="invalid_json"
                    ) from exc
                try:
                    parsed = schema.model_validate(decoded)
                except ValidationError as exc:
                    logger.info(
                        "llm_structured_validation_failed | model=%s schema=%s errors=%s",
                        self.model_name,
                        schema.__name__,
                        exc.errors(include_input=False),
                    )
                    raise LLMOutputInvalidError(
                        "Structured output failed schema validation",
                        reason=_validation_reason(exc),
                    ) from exc
                usage = body.get("usage") or {}
                return StructuredLLMResult(
                    value=parsed,
                    usage=LLMUsage(
                        input_tokens=usage.get("prompt_tokens"),
                        output_tokens=usage.get("completion_tokens"),
                    ),
                    model=body.get("model") or self.model_name,
                    latency_ms=round((perf_counter() - started) * 1000),
                    finish_reason=finish_reason,
                )
            except (
                LLMAuthenticationError,
                LLMConfigurationError,
                LLMOutputInvalidError,
                KeyError,
                TypeError,
                json.JSONDecodeError,
            ) as exc:
                if isinstance(exc, (KeyError, TypeError, json.JSONDecodeError)):
                    raise LLMOutputInvalidError(
                        "LLM provider response was malformed",
                        reason="malformed_provider_response",
                    ) from exc
                raise
            except (httpx.TimeoutException, httpx.NetworkError, LLMUnavailableError) as exc:
                last_error = exc
                if attempt >= self.settings.llm_max_retries:
                    break
        raise LLMUnavailableError("LLM 调用失败，请稍后重试") from last_error
