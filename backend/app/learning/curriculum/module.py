import json
from datetime import timedelta, timezone
from hashlib import sha256
from uuid import uuid4

from fastapi import status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.errors import AppError
from app.learning.agents.curriculum.schemas import (
    CurriculumAgentRequest,
    CurriculumDiagnosticBaseline,
    CurriculumExistingSkill,
    CurriculumMaterial,
    CurriculumMaterialChunk,
    CurriculumMaterialScope,
)
from app.learning.context.schemas import LearnerContext
from app.learning.curriculum.schemas import (
    CurriculumArchitectureRead,
    CurriculumDecisionRequest,
    CurriculumGenerateRequest,
    CurriculumGoalRead,
    CurriculumProposalRead,
    CurriculumPublishRequest,
    CurriculumPublishResult,
)
from app.learning.proposals.schemas import ProposalEnvelope
from app.models.course import Course
from app.models.diagnostic import DiagnosticKnowledgeResult, DiagnosticSession
from app.models.knowledge_mastery import KnowledgeMastery
from app.models.knowledge_point import KnowledgePoint
from app.models.learning_goal import LearningGoal
from app.models.learning_proposal import LearningProposal
from app.models.material import Material
from app.models.material_chunk import MaterialChunk
from app.schemas.course_architecture import (
    ArchitectureImportCourse,
    ArchitectureImportKnowledgePoint,
    ArchitectureImportPrerequisite,
    CourseArchitectureImport,
)
from app.services.course_architecture.drafts import CourseArchitectureDraftService
from app.services.course_architecture.publishing import CourseArchitecturePublishingService
from app.services.course_architecture.validation import CourseArchitectureValidationService


class CurriculumModule:
    """Deep Goal → Proposal → Architecture boundary.

    It owns proposal lifecycle and context composition. It never creates formal
    Course, KnowledgePoint, or Lesson rows; publication delegates to the existing
    Course Architecture publishing boundary.
    """

    proposal_type = "curriculum"

    def __init__(self, db, settings, agent, clock) -> None:
        self.db = db
        self.settings = settings
        self.agent = agent
        self.clock = clock
        self.drafts = CourseArchitectureDraftService(db, clock)

    @staticmethod
    def _hash(value: dict) -> str:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return sha256(encoded).hexdigest()

    @staticmethod
    def _utc(value):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    def _proposal(self, public_id: str) -> LearningProposal:
        proposal = self.db.scalar(
            select(LearningProposal).where(
                LearningProposal.public_id == public_id,
                LearningProposal.proposal_type == self.proposal_type,
            )
        )
        if proposal is None:
            raise AppError(
                "curriculum_proposal_not_found",
                "学习路径提案不存在。",
                status.HTTP_404_NOT_FOUND,
            )
        expires_at = self._utc(proposal.expires_at)
        if (
            proposal.status in {"pending", "review_required"}
            and expires_at is not None
            and expires_at <= self.clock.now()
        ):
            proposal.status = "expired"
            proposal.version += 1
            self.db.commit()
            self.db.refresh(proposal)
        return proposal

    def _diagnostic_baseline(self, goal_id: int) -> list[CurriculumDiagnosticBaseline]:
        rows = self.db.execute(
            select(DiagnosticKnowledgeResult, KnowledgePoint, DiagnosticSession)
            .join(KnowledgePoint, KnowledgePoint.id == DiagnosticKnowledgeResult.knowledge_point_id)
            .join(Course, Course.id == KnowledgePoint.course_id)
            .join(DiagnosticSession, DiagnosticSession.id == DiagnosticKnowledgeResult.diagnostic_session_id)
            .where(
                Course.learning_goal_id == goal_id,
                DiagnosticSession.status.in_(("submitted", "evidence_insufficient", "review_required")),
            )
            .order_by(DiagnosticSession.updated_at.desc(), DiagnosticKnowledgeResult.id.desc())
        ).all()
        seen: set[int] = set()
        result: list[CurriculumDiagnosticBaseline] = []
        for baseline, point, _session in rows:
            if point.id in seen:
                continue
            seen.add(point.id)
            result.append(
                CurriculumDiagnosticBaseline(
                    knowledge_point=point.title,
                    ability_level=baseline.ability_level,
                    score_percentage=(
                        float(baseline.score_percentage)
                        if baseline.score_percentage is not None
                        else None
                    ),
                    confidence=float(baseline.confidence),
                    is_skill_gap=baseline.is_skill_gap,
                )
            )
        return result[:50]

    def _existing_skills(self, goal_id: int) -> list[CurriculumExistingSkill]:
        rows = self.db.execute(
            select(KnowledgeMastery, KnowledgePoint)
            .join(KnowledgePoint, KnowledgePoint.id == KnowledgeMastery.knowledge_point_id)
            .join(Course, Course.id == KnowledgePoint.course_id)
            .where(
                Course.learning_goal_id == goal_id,
                KnowledgeMastery.mastery_level.in_(("proficient", "strong")),
            )
            .order_by(KnowledgePoint.id)
        ).all()
        return [
            CurriculumExistingSkill(
                knowledge_point=point.title,
                level=mastery.mastery_level,
                score=float(mastery.mastery_score) if mastery.mastery_score is not None else None,
                evidence_source="mastery",
            )
            for mastery, point in rows
        ][:50]

    def _material_scope(
        self,
        context: LearnerContext,
        requested_material_ids: list[int] | None,
    ) -> CurriculumMaterialScope:
        effective_ids = set(context.material_scope.material_ids)
        if requested_material_ids is None:
            material_ids = sorted(effective_ids)
        else:
            unavailable = sorted(set(requested_material_ids).difference(effective_ids))
            if unavailable:
                raise AppError(
                    "curriculum_material_scope_invalid",
                    "所选资料不属于该学习目标的有效资料范围。",
                    status.HTTP_409_CONFLICT,
                    {"material_ids": unavailable},
                )
            material_ids = requested_material_ids
        if not material_ids:
            return CurriculumMaterialScope(mode="goal_only")

        self.drafts.validate_materials(material_ids)
        materials = list(
            self.db.scalars(
                select(Material)
                .where(Material.id.in_(material_ids))
                .order_by(Material.id)
            )
        )
        chunks = list(
            self.db.scalars(
                select(MaterialChunk)
                .where(MaterialChunk.material_id.in_(material_ids))
                .order_by(MaterialChunk.material_id, MaterialChunk.chunk_index)
                .limit(self.settings.course_architecture_max_chunks_per_batch)
            )
        )
        remaining = self.settings.course_architecture_max_characters_per_batch
        projected_chunks: list[CurriculumMaterialChunk] = []
        for chunk in chunks:
            if remaining <= 0:
                break
            content = chunk.content[:remaining]
            remaining -= len(content)
            locator = f"chunk:{chunk.chunk_index}"
            if chunk.page_number is not None:
                locator += f";page:{chunk.page_number}"
            elif chunk.section_title:
                locator += f";section:{chunk.section_title}"
            projected_chunks.append(
                CurriculumMaterialChunk(
                    chunk_id=chunk.id,
                    material_id=chunk.material_id,
                    locator=locator,
                    content=content,
                )
            )
        if not projected_chunks:
            raise AppError(
                "curriculum_material_scope_empty",
                "所选资料没有可用于课程规划的片段。",
                status.HTTP_409_CONFLICT,
            )
        return CurriculumMaterialScope(
            mode="source_grounded",
            materials=[
                CurriculumMaterial(
                    material_id=item.id,
                    title=item.title,
                    original_filename=item.original_filename,
                )
                for item in materials
            ],
            chunks=projected_chunks,
        )

    def _agent_request(
        self,
        context: LearnerContext,
        payload: CurriculumGenerateRequest,
    ) -> CurriculumAgentRequest:
        if context.goal is None:
            raise AppError(
                "curriculum_goal_required",
                "生成学习路径需要明确的学习目标上下文。",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        goal = self.db.get(LearningGoal, context.goal.id)
        assert goal is not None
        if goal.status != "active":
            raise AppError(
                "curriculum_goal_inactive",
                "只能为有效学习目标生成学习路径。",
                status.HTTP_409_CONFLICT,
            )
        return CurriculumAgentRequest(
            user_request=payload.instruction,
            goal_id=goal.id,
            goal_title=goal.title,
            goal_description=goal.description,
            current_level=goal.current_level,
            target_date=goal.target_date,
            daily_minutes=goal.daily_minutes,
            diagnostic_baseline=self._diagnostic_baseline(goal.id),
            existing_skills=self._existing_skills(goal.id),
            material_scope=self._material_scope(context, payload.material_ids),
        )

    def generate(
        self,
        context: LearnerContext,
        payload: CurriculumGenerateRequest,
        *,
        source_harness_run_id: int | None = None,
    ) -> CurriculumProposalRead:
        generation_input = {
            "goal_id": context.goal.id if context.goal else None,
            "instruction": payload.instruction.strip(),
            "material_ids": payload.material_ids,
            "context_version": context.context_version,
        }
        input_hash = self._hash(generation_input)
        replay = self.db.scalar(
            select(LearningProposal).where(
                LearningProposal.generation_request_id == payload.request_id
            )
        )
        if replay is not None:
            if (replay.summary or {}).get("generation_input_hash") != input_hash:
                raise AppError(
                    "curriculum_generation_request_conflict",
                    "相同 request_id 已绑定到另一份生成输入。",
                    status.HTTP_409_CONFLICT,
                )
            return self.serialize(replay)

        request = self._agent_request(context, payload)
        result = self.agent.generate(request)
        grounding_mode = request.material_scope.mode
        material_ids = [item.material_id for item in request.material_scope.materials]
        proposal_dump = result.proposal.model_dump(mode="json")
        assumptions = list(proposal_dump["assumptions"])
        if not request.current_level.strip():
            assumptions.append("学习目标未填写当前水平，需在审查时确认难度。")
        if request.target_date is None:
            assumptions.append("学习目标未填写截止日期，时长仅按每日预算估算。")
        if grounding_mode == "goal_only":
            assumptions.append("当前没有有效资料，本提案尚未经过资料验证。")
        proposal_dump["assumptions"] = list(dict.fromkeys(assumptions))[:30]

        import_payload = CourseArchitectureImport(
            learning_goal_id=request.goal_id,
            title=f"{result.proposal.course_title} · Curriculum",
            description="由 Curriculum Proposal 生成，发布前必须人工审查。",
            material_ids=material_ids,
            generation_mode=(
                "curriculum_source_grounded"
                if grounding_mode == "source_grounded"
                else "curriculum_goal_only"
            ),
            generation_request_id=payload.request_id,
            model_name=result.model_name,
            prompt_version=result.prompt_version,
            courses=[
                ArchitectureImportCourse(
                    title=result.proposal.course_title,
                    description=result.proposal.course_description,
                    learning_outcomes=result.proposal.coverage_report.covered_topics,
                    knowledge_points=[
                        ArchitectureImportKnowledgePoint(
                            title=point.title,
                            description=point.description,
                            learning_objectives=point.learning_objectives,
                            key_terms=point.key_terms,
                            difficulty_label=point.difficulty_label,
                            source_chunk_ids=point.source_chunk_ids,
                        )
                        for point in result.proposal.knowledge_points
                    ],
                )
            ],
            prerequisites=[
                ArchitectureImportPrerequisite(**edge.model_dump())
                for edge in result.proposal.prerequisites
            ],
        )
        try:
            draft = self.drafts.import_structure(import_payload, commit=False)
            quality = CourseArchitectureValidationService(
                self.db, self.settings
            ).validate_draft(draft.id, version=draft.version, commit=False)
            draft = self.drafts.get_draft(draft.id)
            goal = self.db.get(LearningGoal, request.goal_id)
            assert goal is not None
            proposal = LearningProposal(
                public_id=str(uuid4()),
                proposal_type=self.proposal_type,
                status="review_required",
                version=1,
                generation_request_id=payload.request_id,
                source_harness_run_id=source_harness_run_id,
                target_type="learning_goal",
                target_id=str(goal.id),
                context_version=context.context_version,
                domain_draft_type="course_architecture_draft",
                domain_draft_id=str(draft.id),
                summary={
                    "generation_input_hash": input_hash,
                    "goal": {
                        "id": goal.id,
                        "title": goal.title,
                        "description": goal.description,
                        "current_level": goal.current_level,
                        "target_date": goal.target_date.isoformat() if goal.target_date else None,
                        "daily_minutes": goal.daily_minutes,
                    },
                    "grounding_mode": grounding_mode,
                    "material_ids": material_ids,
                    "curriculum": proposal_dump,
                    "architecture": {
                        "draft_id": draft.id,
                        "public_id": draft.public_id,
                        "version": draft.version,
                        "status": draft.status,
                        "quality_status": draft.quality_status,
                        "quality_report": quality.model_dump(mode="json"),
                    },
                },
                rationale="基于学习目标、时间预算、诊断基线、已有技能和可选资料形成。",
                expires_at=self.clock.now() + timedelta(days=7),
            )
            self.db.add(proposal)
            self.db.commit()
            self.db.refresh(proposal)
            return self.serialize(proposal)
        except AppError:
            self.db.rollback()
            raise
        except IntegrityError as exc:
            self.db.rollback()
            replay = self.db.scalar(
                select(LearningProposal).where(
                    LearningProposal.generation_request_id == payload.request_id
                )
            )
            if replay is not None:
                return self.serialize(replay)
            raise AppError(
                "curriculum_generation_conflict",
                "学习路径生成请求与现有提案冲突。",
                status.HTTP_409_CONFLICT,
            ) from exc

    def get(self, public_id: str) -> CurriculumProposalRead:
        return self.serialize(self._proposal(public_id))

    def decide(
        self,
        public_id: str,
        payload: CurriculumDecisionRequest,
    ) -> CurriculumProposalRead:
        proposal = self._proposal(public_id)
        if proposal.decision_request_id == payload.request_id:
            expected = "accepted" if payload.decision == "accept" else "rejected"
            if proposal.status != expected:
                raise AppError(
                    "curriculum_decision_request_conflict",
                    "相同 request_id 已用于另一项决策。",
                    status.HTTP_409_CONFLICT,
                )
            return self.serialize(proposal)
        used = self.db.scalar(
            select(LearningProposal).where(
                LearningProposal.decision_request_id == payload.request_id,
                LearningProposal.id != proposal.id,
            )
        )
        if used is not None:
            raise AppError(
                "curriculum_decision_request_conflict",
                "相同 request_id 已用于另一份提案。",
                status.HTTP_409_CONFLICT,
            )
        if not payload.confirmed:
            raise AppError(
                "curriculum_decision_confirmation_required",
                "接受或拒绝学习路径前需要明确确认。",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        if proposal.version != payload.expected_version:
            raise AppError(
                "curriculum_proposal_version_conflict",
                "学习路径提案已更新，请刷新后重试。",
                status.HTTP_409_CONFLICT,
                {"expected": proposal.version, "received": payload.expected_version},
            )
        if proposal.status not in {"pending", "review_required"}:
            raise AppError(
                "curriculum_proposal_not_decidable",
                "当前状态的学习路径提案不能再次决策。",
                status.HTTP_409_CONFLICT,
                {"status": proposal.status},
            )
        proposal.status = "accepted" if payload.decision == "accept" else "rejected"
        proposal.version += 1
        proposal.decision_request_id = payload.request_id
        proposal.decided_at = self.clock.now()
        self.db.commit()
        self.db.refresh(proposal)
        return self.serialize(proposal)

    def publish(
        self,
        public_id: str,
        payload: CurriculumPublishRequest,
    ) -> CurriculumPublishResult:
        proposal = self._proposal(public_id)
        if not payload.confirmed:
            raise AppError(
                "curriculum_publish_confirmation_required",
                "发布课程架构前需要明确确认。",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        if proposal.status != "accepted":
            raise AppError(
                "curriculum_proposal_not_accepted",
                "学习路径提案必须先接受，才能发布正式课程。",
                status.HTTP_409_CONFLICT,
                {"status": proposal.status},
            )
        if proposal.version != payload.expected_proposal_version:
            raise AppError(
                "curriculum_proposal_version_conflict",
                "学习路径提案已更新，请刷新后重试。",
                status.HTTP_409_CONFLICT,
            )
        draft_id = int(proposal.domain_draft_id or 0)
        publication = CourseArchitecturePublishingService(
            self.db, self.settings, self.clock
        ).publish(
            draft_id,
            version=payload.draft_version,
            publish_request_id=payload.publish_request_id,
            confirmed=True,
        )
        return CurriculumPublishResult(
            proposal=self.serialize(proposal),
            publication=publication,
        )

    def envelope(self, proposal: CurriculumProposalRead) -> ProposalEnvelope:
        return ProposalEnvelope(
            proposal_id=proposal.proposal_id,
            proposal_type=self.proposal_type,
            status=proposal.status,
            version=proposal.version,
            context_version=proposal.context_version,
            target_type="learning_goal",
            target_id=str(proposal.goal.id),
            summary={
                "course_title": proposal.curriculum.course_title,
                "knowledge_point_count": len(proposal.curriculum.knowledge_points),
                "estimated_duration": proposal.curriculum.estimated_duration,
                "grounding_mode": proposal.grounding_mode,
                "architecture_draft_id": proposal.architecture.draft_id,
            },
            expires_at=proposal.expires_at,
        )

    def serialize(self, proposal: LearningProposal) -> CurriculumProposalRead:
        summary = proposal.summary or {}
        architecture_summary = dict(summary.get("architecture") or {})
        draft_id = int(proposal.domain_draft_id or architecture_summary.get("draft_id") or 0)
        draft = self.drafts.get_draft(draft_id)
        architecture_summary.update(
            {
                "draft_id": draft.id,
                "public_id": draft.public_id,
                "version": draft.version,
                "status": draft.status,
                "quality_status": draft.quality_status,
                "quality_report": draft.quality_report,
            }
        )
        return CurriculumProposalRead(
            proposal_id=proposal.public_id,
            status=proposal.status,
            version=proposal.version,
            context_version=proposal.context_version,
            generation_request_id=proposal.generation_request_id,
            goal=CurriculumGoalRead.model_validate(summary["goal"]),
            grounding_mode=summary["grounding_mode"],
            material_ids=list(summary.get("material_ids") or []),
            curriculum=summary["curriculum"],
            architecture=CurriculumArchitectureRead.model_validate(architecture_summary),
            expires_at=self._utc(proposal.expires_at),
            decided_at=self._utc(proposal.decided_at),
            created_at=self._utc(proposal.created_at),
            updated_at=self._utc(proposal.updated_at),
        )
