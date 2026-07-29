from dataclasses import dataclass
from typing import Protocol, TypeVar

from pydantic import BaseModel

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


@dataclass(frozen=True)
class LLMUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class StructuredLLMResult:
    value: BaseModel
    usage: LLMUsage
    model: str
    latency_ms: int


class LLMProvider(Protocol):
    model_name: str

    def generate_structured(
        self,
        *,
        messages: list[dict[str, str]],
        schema: type[StructuredModel],
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> StructuredLLMResult: ...
