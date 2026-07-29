from dataclasses import dataclass

from app.core.errors import AppError
from app.schemas.learning_activity import ActivityGenerateRequest, GeneratedActivity
from app.services.learning_activities.prompt_builder import generation_messages
from app.services.learning_activities.validator import ValidationReport, validate_generated_activity
from app.services.llm.base import LLMProvider
from app.services.llm.errors import LLMError, LLMOutputInvalidError
from app.services.rag.types import RagSource
from fastapi import status


@dataclass(frozen=True)
class GenerationResult:
    activity: GeneratedActivity
    report: ValidationReport
    model_name: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int
    repair_used: bool


def generate_activity(
    *,
    provider: LLMProvider,
    request: ActivityGenerateRequest,
    sources: list[RagSource],
    max_output_tokens: int,
) -> GenerationResult:
    allowed = {source.source_label for source in sources}
    repair_reason: str | None = None
    repair_used = False
    total_latency = 0
    last_result = None
    for attempt in range(2):
        try:
            result = provider.generate_structured(
                messages=generation_messages(
                    request, sources, repair_reason=repair_reason
                ),
                schema=GeneratedActivity,
                max_output_tokens=max_output_tokens,
            )
            total_latency += result.latency_ms
            activity = result.value
            assert isinstance(activity, GeneratedActivity)
            report = validate_generated_activity(activity, request, allowed)
            if report.valid:
                return GenerationResult(
                    activity=activity,
                    report=report,
                    model_name=result.model,
                    input_tokens=result.usage.input_tokens,
                    output_tokens=result.usage.output_tokens,
                    latency_ms=total_latency,
                    repair_used=repair_used,
                )
            repair_reason = "; ".join(report.errors)
            last_result = result
        except LLMOutputInvalidError as exc:
            repair_reason = exc.reason
        except LLMError as exc:
            raise AppError(
                exc.code,
                "题目生成模型暂时不可用，请稍后重试",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from exc
        repair_used = True
    details = {"reason": repair_reason or "unknown"}
    if last_result is not None:
        details["model"] = last_result.model
    raise AppError(
        "activity_generation_invalid",
        "模型未能生成通过校验的完整题目批次",
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        details,
    )
