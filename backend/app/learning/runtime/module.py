from hashlib import sha256
from uuid import uuid4

from fastapi import status

from app.core.clock import Clock
from app.core.errors import AppError
from app.learning.adapters.schemas import (
    AgentExecutionResult,
    CurriculumAdapterInterface,
    CurriculumExecutionResult,
    OperationsAdapterInterface,
)
from app.learning.agents.tutor.schemas import TutorAnswer, TutorRequest
from app.learning.context.schemas import ContextQuery, LearnerContext, SurfaceContext
from app.learning.events.schemas import LearningEventEnvelope
from app.learning.policies.schemas import PolicyDecision, PolicyRequest
from app.learning.routing.schemas import RoutingRequest
from app.learning.runtime.schemas import LearningRequest, LearningResponse
from app.learning.runtime.store import HarnessRunStore


class LearningRuntime:
    """Top-level Harness Module with the small ``handle``/``resume`` Interface.

    It coordinates lifecycle Modules and capability Adapters. It intentionally
    owns no Course, Plan, Mastery, Quiz, Lesson, ORM, graph, prompt, or LLM logic.
    """

    def __init__(
        self,
        run_store: HarnessRunStore,
        context_module,
        policy_engine,
        router,
        operations_adapter: OperationsAdapterInterface,
        curriculum_adapter: CurriculumAdapterInterface,
        tutor_agent,
        event_recorder,
        clock: Clock,
    ):
        self.run_store = run_store
        self.context_module = context_module
        self.policy_engine = policy_engine
        self.router = router
        self.operations_adapter = operations_adapter
        self.curriculum_adapter = curriculum_adapter
        self.tutor_agent = tutor_agent
        self.event_recorder = event_recorder
        self.clock = clock

    @staticmethod
    def _input_hash(value: str) -> str:
        return sha256(value.strip().encode("utf-8")).hexdigest()

    @staticmethod
    def _require_allowed(decision: PolicyDecision) -> list[str]:
        if not decision.allowed:
            raise AppError(
                decision.code or "policy_denied",
                decision.reason or "The request was denied by policy.",
                status.HTTP_409_CONFLICT,
            )
        return decision.warnings

    def _context(self, actor_key: str, surface: SurfaceContext, expected: str | None = None):
        return self.context_module.load(
            ContextQuery(
                actor_key=actor_key,
                surface_context=surface,
                expected_context_version=expected,
            )
        )

    def _record_event(
        self,
        *,
        event_type: str,
        run,
        payload: dict,
        causation_id: str | None = None,
    ) -> None:
        self.event_recorder.record(
            LearningEventEnvelope(
                event_id=str(uuid4()),
                event_type=event_type,
                actor_key=run.actor_key,
                aggregate_type="harness_run",
                aggregate_id=run.public_id,
                correlation_id=run.request_id,
                causation_id=causation_id,
                harness_run_id=run.id,
                payload=payload,
                occurred_at=self.clock.now(),
            )
        )

    def _operations_response(
        self,
        run,
        context: LearnerContext,
        result: AgentExecutionResult,
        warnings: list[str],
    ) -> LearningResponse:
        return LearningResponse(
            run_id=run.public_id,
            status=result.status,
            selected_agent="operations",
            answer=result.answer,
            proposal=None,
            confirmation=result.confirmation,
            citations=result.citations,
            tutor_answer=None,
            context_version=context.context_version,
            warnings=list(dict.fromkeys(warnings)),
        )

    def _tutor_response(
        self,
        run,
        context: LearnerContext,
        answer: TutorAnswer,
        warnings: list[str],
    ) -> LearningResponse:
        return LearningResponse(
            run_id=run.public_id,
            status="completed",
            selected_agent="tutor",
            answer=answer.answer_markdown,
            proposal=None,
            confirmation=None,
            citations=[item.model_dump(mode="json") for item in answer.citations],
            tutor_answer=answer,
            context_version=context.context_version,
            warnings=list(dict.fromkeys(warnings)),
        )

    def _curriculum_response(
        self,
        run,
        context: LearnerContext,
        result: CurriculumExecutionResult,
        warnings: list[str],
    ) -> LearningResponse:
        return LearningResponse(
            run_id=run.public_id,
            status=result.status,
            selected_agent="curriculum",
            answer=result.answer,
            proposal=result.proposal,
            confirmation={
                "kind": "curriculum_review",
                "proposal_id": result.proposal.proposal_id,
            },
            citations=result.citations,
            tutor_answer=None,
            context_version=context.context_version,
            warnings=list(dict.fromkeys(warnings)),
        )

    def handle(self, request: LearningRequest) -> LearningResponse:
        input_hash = self._input_hash(request.input)
        existing = self.run_store.find_request(request.actor_key, request.request_id)
        if existing is not None:
            if not self.run_store.matches(existing, request, input_hash):
                raise AppError(
                    "request_id_conflict",
                    "The same actor and request_id are already bound to different request content.",
                    status.HTTP_409_CONFLICT,
                )
            return self.run_store.response(existing)

        run, created = self.run_store.create(request, input_hash, self.clock.now())
        if not created:
            if not self.run_store.matches(run, request, input_hash):
                raise AppError(
                    "request_id_conflict",
                    "The same actor and request_id are already bound to different request content.",
                    status.HTTP_409_CONFLICT,
                )
            return self.run_store.response(run)

        try:
            self._record_event(event_type="run.started", run=run, payload={"channel": request.channel})
            context = self._context(
                request.actor_key,
                request.surface_context,
                request.expected_context_version,
            )
            warnings = self._require_allowed(
                self.policy_engine.evaluate(
                    PolicyRequest(
                        phase="pre_route",
                        context=context,
                        expected_context_version=request.expected_context_version,
                    )
                )
            )
            user_intent = self.router.classify_user_intent(
                request.input,
                request.surface_context,
            )
            route = self.router.route(
                RoutingRequest(
                    input=request.input,
                    user_intent=user_intent,
                    context=context,
                    surface_context=request.surface_context,
                )
            )
            self.run_store.set_context_and_route(run, context.context_version, route.selected_agent)

            if route.selected_agent == "tutor":
                tutor_answer = self.tutor_agent.answer(
                    TutorRequest(
                        question=request.input,
                        learner_context=context,
                        material_scope=context.material_scope,
                        conversation_id=request.conversation_id,
                    )
                )
                result_dump = {
                    "status": "completed",
                    "selected_agent": "tutor",
                    "tutor_answer": tutor_answer.model_dump(mode="json"),
                }
            elif route.selected_agent == "curriculum":
                curriculum_result = self.curriculum_adapter.execute(
                    learner_context=context,
                    user_input=request.input,
                    request_id=request.request_id,
                    harness_run_id=run.id,
                )
                result_dump = curriculum_result.model_dump(mode="json")
            else:
                result = self.operations_adapter.execute(
                    conversation_id=request.conversation_id,
                    user_input=request.input,
                    request_id=request.request_id,
                    harness_run_id=run.id,
                )
                result_dump = result.model_dump(mode="json")
            warnings += self._require_allowed(
                self.policy_engine.evaluate(
                    PolicyRequest(phase="after_result", context=context, result=result_dump)
                )
            )

            fresh_context = self._context(request.actor_key, request.surface_context)
            warnings += self._require_allowed(
                self.policy_engine.evaluate(
                    PolicyRequest(
                        phase="before_commit",
                        context=fresh_context,
                        expected_context_version=context.context_version,
                        result=result_dump,
                    )
                )
            )
            if route.selected_agent == "tutor":
                response = self._tutor_response(run, fresh_context, tutor_answer, warnings)
            elif route.selected_agent == "curriculum":
                response = self._curriculum_response(
                    run, fresh_context, curriculum_result, warnings
                )
            else:
                response = self._operations_response(run, fresh_context, result, warnings)
            self.run_store.complete(run, response, result_dump, self.clock.now())
            if route.selected_agent == "tutor":
                self._record_event(
                    event_type="TutorInteractionRecorded",
                    run=run,
                    payload={
                        "conversation_id": request.conversation_id,
                        "course_id": (
                            fresh_context.course.id if fresh_context.course is not None else None
                        ),
                        "knowledge_point_id": (
                            fresh_context.knowledge_point.id
                            if fresh_context.knowledge_point is not None
                            else None
                        ),
                        "teaching_mode": tutor_answer.teaching_mode,
                        "citation_labels": [
                            item.source_label for item in tutor_answer.citations
                        ],
                    },
                )
            elif route.selected_agent == "curriculum":
                self._record_event(
                    event_type="CurriculumProposalCreated",
                    run=run,
                    payload={
                        "proposal_id": curriculum_result.proposal.proposal_id,
                        "goal_id": curriculum_result.proposal.target_id,
                    },
                )
            self._record_event(
                event_type=(
                    "run.completed"
                    if route.selected_agent in {"tutor", "curriculum"}
                    or result.status != "failed"
                    else "run.failed"
                ),
                run=run,
                payload={"status": response.status, "selected_agent": route.selected_agent},
            )
            return response
        except AppError as exc:
            self.run_store.fail(run, exc.code, self.clock.now())
            self._record_event(
                event_type="run.failed",
                run=run,
                payload={"status": "failed", "error_code": exc.code},
            )
            raise
        except Exception as exc:
            self.run_store.fail(run, "learning_runtime_failed", self.clock.now())
            self._record_event(
                event_type="run.failed",
                run=run,
                payload={"status": "failed", "error_code": "learning_runtime_failed"},
            )
            raise AppError(
                "learning_runtime_failed",
                "The Learning Runtime could not complete the request.",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            ) from exc

    def resume(self, run_id: str, decision: str, request_id: str) -> LearningResponse:
        if decision not in {"approve", "reject"}:
            raise AppError(
                "resume_decision_invalid",
                "Resume decision must be approve or reject.",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        request_id = request_id.strip()
        if not 8 <= len(request_id) <= 100:
            raise AppError(
                "resume_request_id_invalid",
                "Resume request_id must contain between 8 and 100 characters.",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        run = self.run_store.get(run_id)
        if run is None:
            raise AppError(
                "harness_run_not_found",
                "The Harness run does not exist.",
                status.HTTP_404_NOT_FOUND,
            )
        summary = dict(run.result_summary or {})
        resume_requests = dict(summary.get("resume_requests") or {})
        replay = resume_requests.get(request_id)
        if replay is not None:
            if replay.get("decision") != decision:
                raise AppError(
                    "request_id_conflict",
                    "The resume request_id is already bound to another decision.",
                    status.HTTP_409_CONFLICT,
                )
            return LearningResponse.model_validate(replay["response"])

        adapter_summary = summary.get("execution_result") or summary.get("adapter_result") or {}
        agent_run_id = adapter_summary.get("agent_run_id")
        if agent_run_id is None:
            raise AppError(
                "harness_run_not_resumable",
                "The Harness run has no resumable Agent execution.",
                status.HTTP_409_CONFLICT,
            )

        surface = SurfaceContext.model_validate(run.surface_context or {})
        try:
            context = self._context(run.actor_key, surface)
            warnings = self._require_allowed(
                self.policy_engine.evaluate(
                    PolicyRequest(
                        phase="pre_route",
                        context=context,
                        expected_context_version=run.context_version,
                    )
                )
            )
            result = self.operations_adapter.resume(
                conversation_id=run.conversation_id,
                agent_run_id=int(agent_run_id),
                decision=decision,
            )
            result_dump = result.model_dump(mode="json")
            warnings += self._require_allowed(
                self.policy_engine.evaluate(
                    PolicyRequest(phase="after_result", context=context, result=result_dump)
                )
            )
            fresh_context = self._context(run.actor_key, surface)
            warnings += self._require_allowed(
                self.policy_engine.evaluate(
                    PolicyRequest(
                        phase="before_commit",
                        context=fresh_context,
                        # The approved Operations Adapter call may itself change
                        # NextLearningAction. That is an authorized result, not a
                        # concurrent context conflict.
                        expected_context_version=None,
                        result=result_dump,
                    )
                )
            )
            response = self._operations_response(run, fresh_context, result, warnings)
            resume_requests[request_id] = {
                "decision": decision,
                "response": response.model_dump(mode="json"),
            }
            self.run_store.complete(
                run,
                response,
                result_dump,
                self.clock.now(),
                resume_requests=resume_requests,
            )
            self._record_event(
                event_type="run.resumed",
                run=run,
                causation_id=request_id,
                payload={"decision": decision, "status": result.status},
            )
            return response
        except AppError as exc:
            self.run_store.fail(run, exc.code, self.clock.now())
            self._record_event(
                event_type="run.failed",
                run=run,
                causation_id=request_id,
                payload={"status": "failed", "error_code": exc.code},
            )
            raise
        except Exception as exc:
            self.run_store.fail(run, "learning_runtime_resume_failed", self.clock.now())
            self._record_event(
                event_type="run.failed",
                run=run,
                causation_id=request_id,
                payload={"status": "failed", "error_code": "learning_runtime_resume_failed"},
            )
            raise AppError(
                "learning_runtime_resume_failed",
                "The Learning Runtime could not resume the request.",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            ) from exc
