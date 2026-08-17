import logging

logger = logging.getLogger(__name__)
from fastapi import status

from app.core.errors import AppError
from app.learning.agents.curriculum.prompts import (
    CURRICULUM_PROMPT_VERSION,
    curriculum_messages,
)
from app.learning.agents.curriculum.schemas import (
    CurriculumAgentRequest,
    CurriculumAgentResult,
    CurriculumProposalDraft,
)
from app.services.course_architecture.graph import has_cycle, normalize_title
from app.services.llm.errors import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMNotConfiguredError,
    LLMOutputInvalidError,
    LLMUnavailableError,
)


class CurriculumAgent:
    """Goal-aware curriculum design Module with no formal-fact write authority."""

    prompt_version = CURRICULUM_PROMPT_VERSION

    def __init__(self, provider, settings=None) -> None:
        self.provider = provider
        self.settings = settings

    def generate(self, request: CurriculumAgentRequest) -> CurriculumAgentResult:
        if self.provider is None:
            raise AppError(
                "llm_not_configured",
                "学习路径生成需要先配置模型。",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        try:
            result = self.provider.generate_structured(
                messages=curriculum_messages(request),
                schema=CurriculumProposalDraft,
                temperature=0.1,
                max_output_tokens=(
                    self.settings.curriculum_generation_max_output_tokens
                    if self.settings is not None
                    else 8000
                ),
            )
        except LLMOutputInvalidError as exc:
            logger.exception(
                "curriculum_llm_failed | type=%s code=%s reason=%s message=%s",
                type(exc).__name__,
                getattr(exc, "code", None),
                getattr(exc, "reason", None),
                str(exc),
            )

            raise AppError(
                "curriculum_output_invalid",
                "学习路径生成结果不完整或格式无效，请重试。",
                status.HTTP_502_BAD_GATEWAY,
            ) from exc
        except (LLMAuthenticationError, LLMConfigurationError, LLMNotConfiguredError) as exc:
            logger.exception("curriculum_llm_configuration_failed | code=%s", exc.code)
            raise AppError(
                "curriculum_model_configuration_error",
                "学习路径生成服务尚未正确配置。",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from exc
        except LLMUnavailableError as exc:
            logger.exception("curriculum_llm_transport_failed | code=%s", exc.code)
            raise AppError(
                "curriculum_model_unavailable",
                "学习路径生成服务暂时不可用，请稍后重试。",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from exc
        if not isinstance(result.value, CurriculumProposalDraft):
            raise AppError(
                "curriculum_output_invalid",
                "学习路径生成结果结构无效。",
                status.HTTP_502_BAD_GATEWAY,
            )
        self._validate_output(request, result.value)
        return CurriculumAgentResult(
            proposal=result.value,
            model_name=result.model,
            prompt_version=self.prompt_version,
        )

    @staticmethod
    def _validate_output(
        request: CurriculumAgentRequest,
        proposal: CurriculumProposalDraft,
    ) -> None:
        title_to_index = {
            normalize_title(item.title): index
            for index, item in enumerate(proposal.knowledge_points)
        }
        edges: list[tuple[int, int]] = []
        for edge in proposal.prerequisites:
            source = title_to_index.get(normalize_title(edge.prerequisite_title))
            target = title_to_index.get(normalize_title(edge.dependent_title))
            if source is None or target is None:
                raise AppError(
                    "curriculum_prerequisite_invalid",
                    "前置关系引用了提案以外的知识点。",
                    status.HTTP_502_BAD_GATEWAY,
                )
            if source == target or (source, target) in edges:
                raise AppError(
                    "curriculum_prerequisite_invalid",
                    "前置关系包含自引用或重复关系。",
                    status.HTTP_502_BAD_GATEWAY,
                )
            edges.append((source, target))
        if has_cycle(edges):
            raise AppError(
                "curriculum_prerequisite_cycle",
                "学习路径中的前置关系存在循环。",
                status.HTTP_502_BAD_GATEWAY,
            )

        allowed_chunks = {item.chunk_id for item in request.material_scope.chunks}
        cited_chunks = {
            chunk_id
            for point in proposal.knowledge_points
            for chunk_id in point.source_chunk_ids
        }
        if not cited_chunks.issubset(allowed_chunks):
            raise AppError(
                "curriculum_source_invalid",
                "学习路径引用了资料范围外的片段。",
                status.HTTP_502_BAD_GATEWAY,
            )
        if request.material_scope.mode == "goal_only" and cited_chunks:
            raise AppError(
                "curriculum_source_fabricated",
                "无资料模式不能生成虚假来源。",
                status.HTTP_502_BAD_GATEWAY,
            )
        if request.material_scope.mode == "source_grounded" and any(
            not point.source_chunk_ids for point in proposal.knowledge_points
        ):
            raise AppError(
                "curriculum_source_coverage_incomplete",
                "资料驱动的学习路径必须为每个知识点保留真实来源。",
                status.HTTP_502_BAD_GATEWAY,
            )
        expected_grounding = (
            "source_grounded"
            if request.material_scope.mode == "source_grounded"
            else "goal_only_unverified"
        )
        if proposal.coverage_report.material_grounding != expected_grounding:
            raise AppError(
                "curriculum_grounding_report_invalid",
                "学习路径的资料验证声明与实际范围不一致。",
                status.HTTP_502_BAD_GATEWAY,
            )
