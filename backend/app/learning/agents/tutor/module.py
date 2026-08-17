import re

from fastapi import status

from app.core.errors import AppError
from app.learning.agents.tutor.prompts import tutor_messages
from app.learning.agents.tutor.schemas import (
    TutorAnswer,
    TutorCitation,
    TutorContextReference,
    TutorModelAnswer,
    TutorRequest,
)
from app.learning.agents.tutor.retrieval import TutorRetrievalInterface
from app.services.llm.errors import LLMError
from app.services.rag.types import RagSource
from app.services.rag.validation import CITATION_PATTERN, is_prompt_injection_request


class TutorAgent:
    """Context-aware Tutor Module with one deep ``answer`` Interface.

    It can retrieve and explain, but it owns no domain writes and produces no
    assessment or Mastery evidence.
    """

    def __init__(self, retrieval: TutorRetrievalInterface, provider):
        self.retrieval = retrieval
        self.provider = provider

    @staticmethod
    def _location(request: TutorRequest) -> str:
        course = request.learner_context.course
        lesson = request.learner_context.lesson
        point = request.learner_context.knowledge_point
        labels = [item.title for item in (course, lesson, point) if item is not None]
        return " / ".join(labels) if labels else "当前学习位置"

    @staticmethod
    def _context_references(request: TutorRequest) -> list[TutorContextReference]:
        context = request.learner_context
        items: list[TutorContextReference] = []
        for kind, value in (
            ("learning_goal", context.goal),
            ("course", context.course),
            ("knowledge_point", context.knowledge_point),
            ("lesson", context.lesson),
            ("learning_session", context.learning_session),
            ("daily_task", context.current_task),
        ):
            if value is None:
                continue
            title = getattr(value, "title", None) or f"学习会话 {value.id}"
            items.append(TutorContextReference(kind=kind, id=value.id, title=title))
        if context.lesson_version is not None:
            lesson_title = context.lesson.title if context.lesson else "课节"
            items.append(
                TutorContextReference(
                    kind="lesson_version",
                    id=context.lesson_version.id,
                    title=f"{lesson_title} · v{context.lesson_version.version_number}",
                )
            )
        items.extend(
            TutorContextReference(kind="material", id=item.material_id, title=item.title)
            for item in request.material_scope.materials
        )
        return items

    @staticmethod
    def _citations(sources: list[RagSource], source_ids: list[str]) -> list[TutorCitation]:
        by_label = {item.source_label: item for item in sources}
        return [
            TutorCitation(
                source_label=source.source_label,
                material_id=source.material_id,
                chunk_id=source.chunk_id,
                original_filename=source.original_filename,
                page_number=source.page_number,
                section_title=source.section_title,
                content_excerpt=re.sub(r"\s+", " ", source.content).strip()[:360],
                score=source.score,
            )
            for source_id in source_ids
            if (source := by_label.get(source_id)) is not None
        ]

    def _limited_answer(self, request: TutorRequest, reason: str) -> TutorAnswer:
        limitation = {
            "unscoped_learning_context": "当前学习位置尚未形成可检索的资料范围。",
            "empty_material_scope": "当前课程或知识点尚无可用的已索引资料。",
            "no_retrieval_results": "当前资料范围内没有检索到相关片段。",
            "below_score_threshold": "检索结果与问题的相关度不足，无法可靠讲解。",
            "empty_context": "检索结果没有形成可用的讲解上下文。",
            "index_unavailable": "当前资料索引暂时不可用。",
            "index_stale": "当前资料索引已过期，需要重新构建。",
            "search_unavailable": "当前资料检索暂时不可用。",
            "prompt_injection_request": "无法处理要求披露或绕过内部提示的请求。",
        }.get(reason, "当前有效资料不足，无法形成可靠教学回答。")
        follow_up = (
            "请改为询问当前课程或知识点本身。"
            if reason == "prompt_injection_request"
            else "你可以先为当前课程关联并完成索引的资料，再重新提问。"
        )
        return TutorAnswer(
            answer_markdown=(
                f"**当前学习位置：{self._location(request)}**\n\n"
                "当前有效资料范围内没有足够内容支持可靠讲解。我不会跨课程补取资料或猜测答案。"
            ),
            teaching_mode="scope_limited",
            citations=[],
            context_references=self._context_references(request),
            follow_up_check=follow_up,
            limitations=[limitation],
        )

    @staticmethod
    def _validate_model_answer(answer: TutorModelAnswer, sources: list[RagSource]) -> None:
        allowed = {item.source_label for item in sources}
        inline = set(CITATION_PATTERN.findall(answer.answer_markdown))
        declared = set(answer.cited_source_ids)
        if not inline or inline != declared or not inline.issubset(allowed):
            raise AppError(
                "tutor_output_invalid",
                "The Tutor answer failed citation validation.",
                status.HTTP_502_BAD_GATEWAY,
            )

    def answer(self, request: TutorRequest) -> TutorAnswer:
        if is_prompt_injection_request(request.question):
            return self._limited_answer(request, "prompt_injection_request")

        retrieval = self.retrieval.retrieve(
            question=request.question,
            material_scope=request.material_scope,
        )
        if not retrieval.sources:
            return self._limited_answer(
                request,
                retrieval.unavailable_reason or "insufficient_sources",
            )
        if self.provider is None:
            raise AppError(
                "llm_not_configured",
                "已找到当前范围内的资料，但模型尚未配置，无法生成教学回答。",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        try:
            result = self.provider.generate_structured(
                messages=tutor_messages(request, retrieval.sources),
                schema=TutorModelAnswer,
                temperature=0.2,
            )
        except LLMError as exc:
            raise AppError(
                exc.code,
                "教学模型暂时不可用，请稍后重试。",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from exc

        model_answer = result.value
        if not isinstance(model_answer, TutorModelAnswer):
            raise AppError(
                "tutor_output_invalid",
                "The Tutor returned an unexpected response shape.",
                status.HTTP_502_BAD_GATEWAY,
            )
        self._validate_model_answer(model_answer, retrieval.sources)
        source_ids = list(dict.fromkeys(model_answer.cited_source_ids))
        return TutorAnswer(
            answer_markdown=(
                f"**当前学习位置：{self._location(request)}**\n\n"
                f"{model_answer.answer_markdown.strip()}"
            ),
            teaching_mode=model_answer.teaching_mode,
            citations=self._citations(retrieval.sources, source_ids),
            context_references=self._context_references(request),
            follow_up_check=model_answer.follow_up_check,
            limitations=model_answer.limitations,
        )
