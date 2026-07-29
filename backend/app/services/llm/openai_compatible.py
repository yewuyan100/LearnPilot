import json
from time import perf_counter
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.services.llm.base import LLMUsage, StructuredLLMResult
from app.services.llm.errors import (
    LLMNotConfiguredError,
    LLMOutputInvalidError,
    LLMUnavailableError,
)

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


class OpenAICompatibleProvider:
    def __init__(self, settings: Settings):
        if not settings.llm_configured:
            raise LLMNotConfiguredError("LLM 尚未配置")
        self.settings = settings
        self.model_name = settings.llm_model or ""

    def generate_structured(
        self,
        *,
        messages: list[dict[str, str]],
        schema: type[StructuredModel],
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> StructuredLLMResult:
        started = perf_counter()
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": (
                self.settings.llm_temperature if temperature is None else temperature
            ),
            "max_tokens": (
                self.settings.llm_max_output_tokens
                if max_output_tokens is None
                else max_output_tokens
            ),
            "response_format": {"type": "json_object"},
        }
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
                if response.status_code in {408, 409, 429} or response.status_code >= 500:
                    raise LLMUnavailableError(f"LLM 服务暂时不可用（HTTP {response.status_code}）")
                response.raise_for_status()
                body = response.json()
                raw = body["choices"][0]["message"]["content"]
                if isinstance(raw, list):
                    raw = "".join(item.get("text", "") for item in raw if isinstance(item, dict))
                parsed = schema.model_validate(_decode_json_content(raw))
                usage = body.get("usage") or {}
                return StructuredLLMResult(
                    value=parsed,
                    usage=LLMUsage(
                        input_tokens=usage.get("prompt_tokens"),
                        output_tokens=usage.get("completion_tokens"),
                    ),
                    model=body.get("model") or self.model_name,
                    latency_ms=round((perf_counter() - started) * 1000),
                )
            except json.JSONDecodeError as exc:
                raise LLMOutputInvalidError(
                    "模型未返回有效的结构化结果",
                    reason="invalid_json",
                ) from exc
            except ValidationError as exc:
                raise LLMOutputInvalidError(
                    "模型输出未通过结构校验",
                    reason=_validation_reason(exc),
                ) from exc
            except (KeyError, TypeError) as exc:
                raise LLMOutputInvalidError(
                    "模型服务响应结构不完整",
                    reason="malformed_provider_response",
                ) from exc
            except (
                httpx.TimeoutException,
                httpx.NetworkError,
                httpx.HTTPStatusError,
                LLMUnavailableError,
            ) as exc:
                last_error = exc
                if attempt >= self.settings.llm_max_retries:
                    break
        raise LLMUnavailableError("LLM 调用失败，请稍后重试") from last_error
