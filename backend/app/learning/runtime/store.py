from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.learning.runtime.schemas import LearningRequest, LearningResponse
from app.models.harness_run import HarnessRun


class HarnessRunStore:
    """Persistence boundary for Harness lifecycle records only."""

    def __init__(self, db):
        self.db = db

    def find_request(self, actor_key: str, request_id: str) -> HarnessRun | None:
        return self.db.scalar(
            select(HarnessRun).where(
                HarnessRun.actor_key == actor_key,
                HarnessRun.request_id == request_id,
            )
        )

    def get(self, public_id: str) -> HarnessRun | None:
        return self.db.scalar(select(HarnessRun).where(HarnessRun.public_id == public_id))

    def create(self, request: LearningRequest, input_hash: str, started_at) -> tuple[HarnessRun, bool]:
        row = HarnessRun(
            public_id=str(uuid4()),
            actor_key=request.actor_key,
            request_id=request.request_id,
            input_hash=input_hash,
            conversation_id=request.conversation_id,
            channel=request.channel,
            surface_context=request.surface_context.model_dump(mode="json"),
            status="accepted",
            result_summary={},
            citations=[],
            started_at=started_at,
        )
        self.db.add(row)
        try:
            self.db.commit()
            self.db.refresh(row)
            return row, True
        except IntegrityError:
            self.db.rollback()
            existing = self.find_request(request.actor_key, request.request_id)
            if existing is None:
                raise
            return existing, False

    @staticmethod
    def matches(row: HarnessRun, request: LearningRequest, input_hash: str) -> bool:
        return (
            row.input_hash == input_hash
            and row.conversation_id == request.conversation_id
            and row.channel == request.channel
            and (row.surface_context or {}) == request.surface_context.model_dump(mode="json")
        )

    def set_context_and_route(self, row: HarnessRun, context_version: str, selected_agent: str) -> None:
        row.context_version = context_version
        row.selected_agent = selected_agent
        row.status = "running"
        self.db.commit()

    def complete(
        self,
        row: HarnessRun,
        response: LearningResponse,
        execution_result: dict,
        completed_at,
        resume_requests: dict | None = None,
    ) -> None:
        summary = dict(row.result_summary or {})
        summary["execution_result"] = execution_result
        if execution_result.get("agent_run_id") is not None:
            summary["adapter_result"] = execution_result
        summary["response"] = response.model_dump(mode="json")
        if resume_requests is not None:
            summary["resume_requests"] = resume_requests
        row.result_summary = summary
        row.status = response.status
        row.citations = response.citations
        row.error_code = execution_result.get("error_code")
        row.completed_at = completed_at
        self.db.commit()

    def fail(self, row: HarnessRun, error_code: str, completed_at) -> None:
        row.status = "failed"
        row.error_code = error_code
        row.completed_at = completed_at
        self.db.commit()

    @staticmethod
    def response(row: HarnessRun) -> LearningResponse:
        saved = (row.result_summary or {}).get("response")
        if saved is not None:
            return LearningResponse.model_validate(saved)
        return LearningResponse(
            run_id=row.public_id,
            status=row.status,
            selected_agent=row.selected_agent,
            answer=None,
            proposal=None,
            confirmation=None,
            citations=row.citations or [],
            tutor_answer=None,
            context_version=row.context_version,
            warnings=[],
        )
