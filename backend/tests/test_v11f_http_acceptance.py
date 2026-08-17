from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import socket
from threading import Thread
import time
from uuid import uuid4

import httpx
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
import uvicorn

from app.api.deps import get_embedder, get_llm_provider
from app.core.config import Settings, get_settings
from app.db.base import Base, TimestampMixin
from app.db.session import get_db
from app.main import app
from app.models import (
    ActivityQuestion,
    DailyTask,
    LearningActivity,
    LearningEvent,
    LearningProposal,
    Lesson,
    LessonVersion,
    LessonVersionKnowledgePoint,
    MasteryEvidence,
    StudyPlanVersion,
    WrongAnswer,
)
from tests.fakes import FakeEmbedder


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _ok(response: httpx.Response, expected: int = 200) -> dict:
    assert response.status_code == expected, response.text
    return response.json() if response.content else {}


def _install_fixed_timestamp_clock(session_factory, now: datetime) -> None:
    """Keep database-managed fixture timestamps on the application test clock."""

    @event.listens_for(session_factory, "before_flush")
    def align_timestamp_ownership(session, flush_context, instances):  # noqa: ANN001
        for record in session.new:
            if isinstance(record, TimestampMixin):
                record.created_at = now
                record.updated_at = now
        for record in session.dirty:
            if isinstance(record, TimestampMixin):
                record.updated_at = now


def test_v11f_lesson_quiz_mastery_proposal_confirmation_plan_loop(tmp_path: Path):
    database_path = tmp_path / "v11f-http.sqlite3"
    engine = create_engine(
        f"sqlite:///{database_path}", connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    now = datetime(2026, 8, 1, 4, 0, tzinfo=timezone.utc)
    _install_fixed_timestamp_clock(Session, now)
    settings = Settings(
        database_url=f"sqlite:///{database_path}",
        upload_dir=tmp_path / "uploads",
        faiss_index_path=tmp_path / "materials.faiss",
        faiss_manifest_path=tmp_path / "materials.faiss.manifest.json",
        agent_checkpoint_db_path=tmp_path / "agent_checkpoints.sqlite",
        agent_checkpoint_enabled=False,
        embedding_model_name="fake/bge-m3",
        embedding_model_revision="test",
        llm_api_key=None,
        llm_base_url=None,
        llm_model=None,
        clock_fixed_now=now,
        review_interval_beginner_days=1,
    )

    def override_db():
        with Session() as db:
            yield db

    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_embedder] = lambda: FakeEmbedder()
    app.dependency_overrides[get_llm_provider] = lambda: None

    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    )
    thread = Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.025)
    assert server.started, "isolated V11F HTTP server did not start"

    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=30) as http:
            openapi = _ok(http.get("/openapi.json"))
            assert "/api/plan-adjustments/{proposal_id}/decision" in openapi["paths"]

            goal = _ok(
                http.post(
                    "/api/learning-goals",
                    json={
                        "title": "V11F adaptive goal",
                        "description": "Close the real learning feedback loop.",
                        "target_date": "2026-08-10",
                        "daily_minutes": 60,
                        "current_level": "beginner",
                        "status": "active",
                    },
                ),
                201,
            )
            course = _ok(
                http.post(
                    "/api/courses",
                    json={
                        "learning_goal_id": goal["id"],
                        "title": "State modeling",
                        "description": "A formal course used by V11F acceptance.",
                        "status": "active",
                    },
                ),
                201,
            )
            point = _ok(
                http.post(
                    f"/api/courses/{course['id']}/knowledge-points",
                    json={
                        "title": "State merge semantics",
                        "description": "Understand deterministic state merging.",
                        "order_index": 1,
                        "estimated_minutes": 20,
                        "status": "not_started",
                    },
                ),
                201,
            )

            with Session() as db:
                lesson = Lesson(
                    public_id=str(uuid4()),
                    course_id=course["id"],
                    title="State merge lesson",
                    description="Published lesson for the closed loop.",
                    order_index=1,
                    status="published",
                    current_version_number=1,
                    active_version_number=1,
                )
                db.add(lesson)
                db.flush()
                lesson_version = LessonVersion(
                    lesson_id=lesson.id,
                    version_number=1,
                    status="published",
                    objectives=["Explain State merge semantics"],
                    content_markdown="A complete lesson explanation.",
                    examples=[{"title": "Merge", "explanation_markdown": "Combine updates."}],
                    guided_practice=[
                        {
                            "prompt": "Merge two updates.",
                            "hint": "Use the reducer.",
                            "expected_approach": "Apply both in order.",
                        }
                    ],
                    checks=[
                        {
                            "prompt": "What controls the merge?",
                            "check_type": "short_answer",
                            "expected_concepts": ["reducer"],
                        }
                    ],
                    estimated_minutes=20,
                    source_snapshot_hash="1" * 64,
                    generation_request_id="v11f-lesson-version-0001",
                    model_name="acceptance-fixture",
                    prompt_version="v11f.fixture.1",
                    quality_report={"status": "passed"},
                    published_at=now,
                )
                db.add(lesson_version)
                db.flush()
                db.add(
                    LessonVersionKnowledgePoint(
                        lesson_version_id=lesson_version.id,
                        knowledge_point_id=point["id"],
                        order_index=1,
                        role="primary",
                    )
                )
                activity = LearningActivity(
                    title="State merge assessment",
                    description="One objective assessment.",
                    activity_type="quiz",
                    status="published",
                    course_id=course["id"],
                    knowledge_point_id=point["id"],
                    source_scope={"kind": "knowledge_point", "id": point["id"]},
                    question_count=1,
                    total_points=1,
                    generation_request_id="v11f-activity-0001",
                    generation_config_hash="2" * 64,
                    prompt_version="v11f.fixture.1",
                    model_name="acceptance-fixture",
                    validation_warnings=[],
                    published_at=now,
                )
                db.add(activity)
                db.flush()
                question = ActivityQuestion(
                    activity_id=activity.id,
                    question_index=1,
                    question_type="single_choice",
                    stem="Which option correctly applies the reducer?",
                    options_json=[
                        {"id": "A", "text": "Apply both updates in order"},
                        {"id": "B", "text": "Discard all updates"},
                        {"id": "C", "text": "Choose a random update"},
                    ],
                    correct_answer_json=["A"],
                    explanation="The reducer deterministically combines updates.",
                    difficulty="medium",
                    points=1,
                    status="active",
                    content_hash=sha256(b"v11f-question").hexdigest(),
                )
                db.add(question)
                db.commit()
                lesson_version_id = lesson_version.id
                activity_id = activity.id
                question_id = question.id

            plan = _ok(
                http.post(
                    "/api/study-plans",
                    json={
                        "request_id": "v11f-initial-study-plan",
                        "learning_goal_id": goal["id"],
                        "course_id": course["id"],
                        "start_date": "2026-08-01",
                        "target_date": "2026-08-10",
                        "daily_minutes": 60,
                        "available_weekdays": [0, 1, 2, 3, 4, 5, 6],
                        "allow_weekends": True,
                        "intensity": "standard",
                        "include_due_reviews": True,
                        "use_latest_diagnostic": True,
                        "use_existing_mastery": True,
                    },
                ),
                201,
            )
            published = _ok(
                http.post(
                    f"/api/study-plans/{plan['id']}/publish",
                    json={
                        "request_id": "v11f-initial-plan-publish",
                        "expected_version": plan["version"],
                        "confirmed": True,
                    },
                )
            )
            assert published["plan"]["active_version_number"] == 1
            initial_task_id = published["created_task_ids"][0]

            session = _ok(
                http.post(
                    "/api/learning-sessions",
                    json={
                        "learning_goal_id": goal["id"],
                        "course_id": course["id"],
                        "knowledge_point_id": point["id"],
                        "daily_task_id": initial_task_id,
                        "lesson_version_id": lesson_version_id,
                    },
                ),
                201,
            )
            attempt = _ok(
                http.post(
                    f"/api/learning-activities/{activity_id}/attempts",
                    json={"learning_session_id": session["id"]},
                ),
                201,
            )
            submit_payload = {
                "request_id": "v11f-quiz-submit-0001",
                "answers": [{"question_id": question_id, "answer": ["B"]}],
            }
            result = _ok(
                http.post(f"/api/quiz-attempts/{attempt['id']}/submit", json=submit_payload)
            )
            assert result["status"] == "completed"
            assert result["score_percentage"] == 0

            proposals = _ok(http.get("/api/plan-adjustments?status=pending"))
            assert len(proposals) == 1
            proposal = proposals[0]
            assert proposal["proposal_type"] == "plan_adjustment"
            assert proposal["mastery_change"]["new_level"] == "beginner"
            assert proposal["mastery_evidence_ids"]

            next_action = _ok(http.get("/api/next-learning-action"))
            assert next_action["action_type"] == "review_proposal"
            assert next_action["reason_code"] == "pending_plan_adjustment"
            assert proposal["proposal_id"] in next_action["cta_href"]

            replay = _ok(
                http.post(f"/api/quiz-attempts/{attempt['id']}/submit", json=submit_payload)
            )
            assert replay["idempotent_replay"] is True
            assert len(_ok(http.get("/api/plan-adjustments?status=pending"))) == 1

            before = _ok(http.get(f"/api/study-plans/{plan['id']}"))
            denied = http.post(
                f"/api/plan-adjustments/{proposal['proposal_id']}/decision",
                json={
                    "request_id": "v11f-proposal-denied-without-confirm",
                    "decision": "accept",
                    "expected_version": proposal["version"],
                    "context_version": proposal["context_version"],
                    "confirmed": False,
                },
            )
            assert denied.status_code == 409
            assert _ok(
                http.get(f"/api/plan-adjustments/{proposal['proposal_id']}")
            )["status"] == "pending"
            unchanged = _ok(http.get(f"/api/study-plans/{plan['id']}"))
            assert unchanged["version"] == before["version"]
            assert unchanged["current_version_number"] == 1
            assert unchanged["active_version_number"] == 1

            decision_payload = {
                "request_id": "v11f-proposal-confirm-0001",
                "decision": "accept",
                "expected_version": proposal["version"],
                "context_version": proposal["context_version"],
                "confirmed": True,
            }
            accepted = _ok(
                http.post(
                    f"/api/plan-adjustments/{proposal['proposal_id']}/decision",
                    json=decision_payload,
                )
            )
            assert accepted["status"] == "accepted"
            assert accepted["application"]["new_plan_version"] == 2
            assert accepted["application"]["active_plan_version"] == 2

            updated = _ok(http.get(f"/api/study-plans/{plan['id']}"))
            assert updated["current_version_number"] == 2
            assert updated["active_version_number"] == 2
            assert any(item["is_due_review"] for item in updated["active_version"]["items"])
            assert _ok(
                http.post(
                    f"/api/plan-adjustments/{proposal['proposal_id']}/decision",
                    json=decision_payload,
                )
            )["application"]["active_plan_version"] == 2

            with Session() as db:
                wrong_answer = db.scalar(select(WrongAnswer))
                completed_task = db.get(DailyTask, initial_task_id)
                assert wrong_answer is not None
                assert completed_task is not None
                assert wrong_answer.created_at.replace(tzinfo=timezone.utc) == now
                assert completed_task.updated_at.replace(tzinfo=timezone.utc) == now
                events = list(
                    db.scalars(
                        select(LearningEvent).where(
                            LearningEvent.event_type.in_(
                                ("QuizFinished", "LessonCompleted", "MasteryChanged")
                            )
                        )
                    )
                )
                event_types = [item.event_type for item in events]
                assert event_types.count("QuizFinished") == 1
                assert event_types.count("LessonCompleted") == 1
                assert event_types.count("MasteryChanged") == 1
                quiz_event = next(item for item in events if item.event_type == "QuizFinished")
                assert quiz_event.payload == {
                    "quiz_attempt_id": attempt["id"],
                    "course_id": course["id"],
                    "lesson_id": lesson.id,
                    "knowledge_point_ids": [point["id"]],
                    "score": 0.0,
                }
                mastery_event = next(
                    item for item in events if item.event_type == "MasteryChanged"
                )
                assert mastery_event.payload["knowledge_point_id"] == point["id"]
                assert mastery_event.payload["old_level"] == "unassessed"
                assert mastery_event.payload["new_level"] == "beginner"
                assert mastery_event.payload["evidence_ids"]
                assert db.scalar(
                    select(func.count())
                    .select_from(MasteryEvidence)
                    .where(MasteryEvidence.source_type == "learning_event")
                ) == 0
                assert db.scalar(
                    select(func.count())
                    .select_from(LearningProposal)
                    .where(LearningProposal.proposal_type == "plan_adjustment")
                ) == 1
                assert db.scalar(
                    select(func.count())
                    .select_from(StudyPlanVersion)
                    .where(StudyPlanVersion.study_plan_id == plan["id"])
                ) == 2
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        app.dependency_overrides.clear()
        engine.dispose()
