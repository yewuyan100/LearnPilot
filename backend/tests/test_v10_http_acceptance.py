from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import socket
from threading import Thread
import time

import httpx
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
import uvicorn

from app.api.deps import get_embedder, get_llm_provider
from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import DailyTask
from app.services.study_plans.service import StudyPlanService
from tests.fakes import FakeEmbedder
from tests.test_diagnostics_v10 import DiagnosticProvider


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _ok(response: httpx.Response, expected: int = 200) -> dict:
    assert response.status_code == expected, response.text
    return response.json() if response.content else {}


def test_v10_real_tcp_diagnostic_plan_next_action_and_rollback(tmp_path: Path, monkeypatch):
    database_path = tmp_path / "v10-http.sqlite3"
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
    settings = Settings(
        database_url=f"sqlite:///{database_path}",
        upload_dir=tmp_path / "uploads",
        faiss_index_path=tmp_path / "materials.faiss",
        faiss_manifest_path=tmp_path / "materials.faiss.manifest.json",
        agent_checkpoint_db_path=tmp_path / "agent_checkpoints.sqlite",
        agent_checkpoint_enabled=False,
        material_chunk_size=160,
        material_chunk_overlap=30,
        material_min_chunk_size=20,
        embedding_model_name="fake/bge-m3",
        embedding_model_revision="test",
        search_top_k_default=3,
        search_top_k_max=10,
        llm_api_key=None,
        llm_base_url=None,
        llm_model=None,
        clock_fixed_now=datetime(2026, 8, 1, 4, 0, tzinfo=timezone.utc),
    )
    provider = {"current": DiagnosticProvider()}

    def override_db():
        with Session() as db:
            yield db

    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_embedder] = lambda: FakeEmbedder()
    app.dependency_overrides[get_llm_provider] = lambda: provider["current"]

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
    assert server.started, "isolated V10 HTTP server did not start"

    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=30) as http:
            openapi = _ok(http.get("/openapi.json"))
            assert "/api/courses/{course_id}/diagnostics" in openapi["paths"]
            assert "/api/study-plans/{plan_id}/publish" in openapi["paths"]
            assert "/api/next-learning-action/accept" in openapi["paths"]

            goal = _ok(
                http.post(
                    "/api/learning-goals",
                    json={
                        "title": "V10 HTTP 目标",
                        "description": "隔离真实 HTTP 验收",
                        "target_date": "2026-08-10",
                        "daily_minutes": 40,
                        "current_level": "初学",
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
                        "title": "V10 HTTP 课程",
                        "description": "真实 TCP 调用",
                        "status": "active",
                    },
                ),
                201,
            )
            points = []
            for index in range(2):
                points.append(
                    _ok(
                        http.post(
                            f"/api/courses/{course['id']}/knowledge-points",
                            json={
                                "title": f"HTTP 知识点 {index + 1}",
                                "description": "受控调用与确定性验证",
                                "order_index": index + 1,
                                "estimated_minutes": 20,
                                "status": "not_started",
                            },
                        ),
                        201,
                    )
                )
            body = ("受控调用必须经过明确边界和确定性验证。\n" * 20).encode()
            material = _ok(
                http.post(
                    "/api/materials/upload",
                    files={"file": ("v10-http.txt", body, "text/plain")},
                ),
                201,
            )
            _ok(http.post(f"/api/materials/{material['id']}/process"))
            _ok(
                http.post(
                    f"/api/materials/{material['id']}/learning-links",
                    json={
                        "target_type": "course",
                        "course_id": course["id"],
                        "relation_type": "primary_source",
                        "is_primary": True,
                    },
                ),
                201,
            )

            objective = _ok(
                http.post(
                    f"/api/courses/{course['id']}/diagnostics",
                    json={
                        "request_id": "v10-http-diagnostic-objective",
                        "questions_per_point": 1,
                        "question_types": ["single_choice"],
                        "difficulty": "medium",
                    },
                ),
                201,
            )
            assert objective["status"] == "pending"
            assert objective["coverage_report"]["coverage_rate"] == 1
            objective_answers = [
                {"question_id": question["id"], "answer": ["A"]}
                for question in objective["attempt"]["questions"]
            ]
            submitted = _ok(
                http.post(
                    f"/api/diagnostics/{objective['id']}/submit",
                    json={
                        "request_id": "v10-http-submit-objective",
                        "expected_version": objective["version"],
                        "answers": objective_answers,
                    },
                )
            )
            assert submitted["status"] == "submitted"
            assert all(answer["earned_points"] == 2 for answer in submitted["attempt"]["answers"])
            assert all(result["mastery_evidence_id"] for result in submitted["results"])

            provider["current"] = DiagnosticProvider(confidence=0.2)
            short = _ok(
                http.post(
                    f"/api/courses/{course['id']}/diagnostics/reassess",
                    json={
                        "request_id": "v10-http-diagnostic-short",
                        "questions_per_point": 1,
                        "question_types": ["short_answer"],
                        "difficulty": "medium",
                        "supersedes_session_id": objective["id"],
                    },
                ),
                201,
            )
            short_result = _ok(
                http.post(
                    f"/api/diagnostics/{short['id']}/submit",
                    json={
                        "request_id": "v10-http-submit-short",
                        "expected_version": short["version"],
                        "answers": [
                            {
                                "question_id": question["id"],
                                "answer_text": "调用必须经过明确边界。",
                            }
                            for question in short["attempt"]["questions"]
                        ],
                    },
                )
            )
            assert short_result["status"] == "review_required"
            assert all(answer["earned_points"] is None for answer in short_result["attempt"]["answers"])

            provider["current"] = DiagnosticProvider(fail=True)
            failed_generation = _ok(
                http.post(
                    f"/api/courses/{course['id']}/diagnostics/reassess",
                    json={
                        "request_id": "v10-http-diagnostic-provider-failure",
                        "questions_per_point": 1,
                        "question_types": ["single_choice"],
                        "difficulty": "medium",
                        "supersedes_session_id": short["id"],
                    },
                ),
                201,
            )
            assert failed_generation["status"] == "generation_failed"
            assert failed_generation["last_error_code"] == "llm_unavailable"

            common_plan = {
                "learning_goal_id": goal["id"],
                "course_id": course["id"],
                "start_date": "2026-08-01",
                "target_date": "2026-08-02",
                "available_weekdays": [5, 6],
                "allow_weekends": True,
                "intensity": "standard",
                "include_due_reviews": True,
                "use_latest_diagnostic": True,
                "use_existing_mastery": True,
            }
            infeasible = _ok(
                http.post(
                    "/api/study-plans",
                    json={
                        **common_plan,
                        "request_id": "v10-http-plan-infeasible",
                        "daily_minutes": 10,
                    },
                ),
                201,
            )
            assert infeasible["status"] == "infeasible"
            assert infeasible["latest_version"]["gap_minutes"] > 0

            ready = _ok(
                http.post(
                    "/api/study-plans",
                    json={
                        **common_plan,
                        "request_id": "v10-http-plan-ready",
                        "daily_minutes": 40,
                    },
                ),
                201,
            )
            assert ready["status"] == "ready"
            original_create = StudyPlanService._create_daily_task
            calls = {"count": 0}

            def fail_second(self, item):
                calls["count"] += 1
                if calls["count"] == 2:
                    raise RuntimeError("forced HTTP publication failure")
                return original_create(self, item)

            monkeypatch.setattr(StudyPlanService, "_create_daily_task", fail_second)
            failed_publish = http.post(
                f"/api/study-plans/{ready['id']}/publish",
                json={
                    "request_id": "v10-http-plan-publish",
                    "expected_version": ready["version"],
                    "confirmed": True,
                },
            )
            assert failed_publish.status_code == 503
            assert _ok(http.get(f"/api/study-plans/{ready['id']}"))["status"] == "ready"
            with Session() as db:
                assert db.scalar(select(func.count()).select_from(DailyTask)) == 0

            monkeypatch.setattr(StudyPlanService, "_create_daily_task", original_create)
            publish_payload = {
                "request_id": "v10-http-plan-publish",
                "expected_version": ready["version"],
                "confirmed": True,
            }
            published = _ok(
                http.post(f"/api/study-plans/{ready['id']}/publish", json=publish_payload)
            )
            assert published["plan"]["status"] == "active"
            assert len(published["created_task_ids"]) == 2
            replay = _ok(
                http.post(f"/api/study-plans/{ready['id']}/publish", json=publish_payload)
            )
            assert replay["idempotent_replay"] is True
            with Session() as db:
                assert db.scalar(select(func.count()).select_from(DailyTask)) == 2

            action = _ok(http.get("/api/next-learning-action"))
            assert action["reason_code"] == "today_formal_plan"
            accepted = _ok(
                http.post(
                    "/api/next-learning-action/accept",
                    json={
                        "request_id": "v10-http-next-accept",
                        "action_signature": action["action_signature"],
                    },
                )
            )
            assert accepted["learning_session_id"] is not None
            assert _ok(http.get("/api/next-learning-action"))["action_type"] == "resume_session"

            completed_task = published["created_task_ids"][0]
            _ok(
                http.patch(
                    f"/api/daily-tasks/{completed_task}", json={"status": "completed"}
                )
            )
            replanned = _ok(
                http.post(
                    f"/api/study-plans/{ready['id']}/replan",
                    json={
                        "request_id": "v10-http-replan",
                        "expected_version": published["plan"]["version"],
                        "reason": "真实 HTTP 验证完成任务保持不变",
                        "target_date": "2026-08-03",
                        "daily_minutes": 40,
                        "available_weekdays": [0, 5, 6],
                        "allow_weekends": True,
                    },
                )
            )
            assert replanned["current_version_number"] == 2
            assert replanned["active_version_number"] == 1
            assert all(
                item["daily_task_id"] != completed_task
                for item in replanned["latest_version"]["items"]
            )
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()

    assert not thread.is_alive()
