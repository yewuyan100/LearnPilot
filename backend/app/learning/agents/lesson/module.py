from fastapi import status

from app.core.errors import AppError
from app.learning.agents.lesson.prompts import LESSON_PROMPT_VERSION, lesson_messages
from app.learning.agents.lesson.schemas import (
    GeneratedLessonDraft,
    LessonAgentResult,
    LessonGenerationRequest,
)
from app.learning.agents.tutor.retrieval import TutorRetrievalInterface
from app.services.llm.errors import LLMError


class LessonAgent:
    """Lesson generation Module; it returns an unpublished draft and real sources."""

    prompt_version = LESSON_PROMPT_VERSION

    def __init__(self, retrieval: TutorRetrievalInterface, provider):
        self.retrieval = retrieval
        self.provider = provider

    def generate(self, request: LessonGenerationRequest) -> LessonAgentResult:
        query = " ".join(
            [request.lesson_title, request.course_title]
            + [point.title for point in request.knowledge_points]
            + [item.title for item in request.prerequisites]
        )
        retrieval = self.retrieval.retrieve(
            question=query,
            material_scope=request.material_scope,
        )
        if not retrieval.sources:
            raise AppError(
                "lesson_sources_insufficient",
                "当前有效资料范围内没有足够片段生成课节。",
                status.HTTP_409_CONFLICT,
                {"reason": retrieval.unavailable_reason or "insufficient_sources"},
            )
        if self.provider is None:
            raise AppError(
                "llm_not_configured",
                "已找到课节资料，但模型尚未配置。",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        try:
            result = self.provider.generate_structured(
                messages=lesson_messages(request, retrieval.sources),
                schema=GeneratedLessonDraft,
                temperature=0.2,
            )
        except LLMError as exc:
            raise AppError(
                exc.code,
                "课节生成模型暂时不可用，请稍后重试。",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from exc
        if not isinstance(result.value, GeneratedLessonDraft):
            raise AppError(
                "lesson_generation_output_invalid",
                "课节生成结果结构无效。",
                status.HTTP_502_BAD_GATEWAY,
            )
        return LessonAgentResult(
            draft=result.value,
            sources=retrieval.sources,
            model_name=result.model,
        )
