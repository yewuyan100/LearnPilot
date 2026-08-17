from __future__ import annotations

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
from app.models.course import Course
from app.models.course_architecture import KnowledgePointPrerequisite
from app.models.knowledge_point import KnowledgePoint
from app.models.knowledge_point_source import KnowledgePointSource
from app.models.material_learning_link import MaterialLearningLink
from tests.fakes import FakeEmbedder
from tests.test_course_architecture_v9 import (
    FakeArchitectureLLM,
    build_manual_ready_draft,
    create_draft,
    create_goal,
    create_ready_material,
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _ok(response: httpx.Response, expected: int = 200) -> dict:
    assert response.status_code == expected, response.text
    return response.json() if response.content else {}


def test_v9_real_tcp_draft_generation_edit_publish_and_failure(
    tmp_path: Path, goal_payload
):
    """Exercise the V9 boundary over TCP without touching workspace resources."""
    database_path = tmp_path / "v9-http.sqlite3"
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
        llm_api_key=None,
        llm_base_url=None,
        llm_model=None,
        course_architecture_max_chunks_per_batch=4,
        course_architecture_max_batches=24,
    )
    provider = {"current": FakeArchitectureLLM()}

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
    assert server.started, "isolated V9 HTTP server did not start"

    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=30) as http:
            openapi = _ok(http.get("/openapi.json"))
            assert "/api/course-architecture/drafts/{draft_id}/publish" in openapi["paths"]
            assert "CourseArchitectureDraftCreate" in openapi["components"]["schemas"]

            goal = create_goal(http, goal_payload, "V9 HTTP 目标")
            material, chunks = create_ready_material(http, "v9-http.md")

            # Scenario 1: the manual aggregate is usable without an LLM.
            manual = build_manual_ready_draft(http, goal, material, chunks)
            assert manual["status"] == "ready"
            assert manual["quality_report"]["blocker_count"] == 0
            assert manual["prerequisites"]

            # Scenario 5/6: explicit confirmation publishes once and is idempotent.
            declined = http.post(
                f"/api/course-architecture/drafts/{manual['id']}/publish",
                json={
                    "version": manual["version"],
                    "publish_request_id": "v9-http-publish-0001",
                    "confirmed": False,
                },
            )
            assert declined.status_code == 422
            published = _ok(
                http.post(
                    f"/api/course-architecture/drafts/{manual['id']}/publish",
                    json={
                        "version": manual["version"],
                        "publish_request_id": "v9-http-publish-0001",
                        "confirmed": True,
                    },
                )
            )
            repeated = _ok(
                http.post(
                    f"/api/course-architecture/drafts/{manual['id']}/publish",
                    json={
                        "version": manual["version"],
                        "publish_request_id": "v9-http-publish-0001",
                        "confirmed": True,
                    },
                )
            )
            assert repeated == published
            assert len(published["course_ids"]) == 1
            assert len(published["knowledge_point_ids"]) == 2
            assert _ok(http.get(f"/api/courses/{published['course_ids'][0]}/materials"))
            for point_id in published["knowledge_point_ids"]:
                assert _ok(http.get(f"/api/knowledge-points/{point_id}/sources"))

            with Session() as db:
                assert db.scalar(select(func.count(Course.id))) == 1
                assert db.scalar(select(func.count(KnowledgePoint.id))) == 2
                assert db.scalar(select(func.count(MaterialLearningLink.id))) == 1
                assert db.scalar(select(func.count(KnowledgePointSource.id))) == 2
                assert db.scalar(select(func.count(KnowledgePointPrerequisite.id))) == 1

            # Scenario 2: structured generation stays bounded and source-traceable.
            automatic = create_draft(http, goal, material, "自动生成草案")
            generated = _ok(
                http.post(
                    f"/api/course-architecture/drafts/{automatic['id']}/generate",
                    json={
                        "version": automatic["version"],
                        "request_id": "v9-http-generate-0001",
                    },
                )
            )
            assert generated["status"] in {"review_required", "ready"}
            generated_points = [
                point
                for course in generated["courses"]
                for point in course["knowledge_points"]
            ]
            assert generated_points and all(point["sources"] for point in generated_points)
            assert {
                source["material_id"]
                for point in generated_points
                for source in point["sources"]
            } == {material["id"]}
            stream = http.get(
                f"/api/course-architecture/drafts/{automatic['id']}/events"
            )
            assert stream.status_code == 200
            assert "event: section.completed" in stream.text
            assert "event: draft.ready" in stream.text

            # Scenario 3: edit, reorder, move and merge preserve a real source.
            first_course = generated["courses"][0]
            generated = _ok(
                http.patch(
                    f"/api/course-architecture/drafts/{automatic['id']}/courses/{first_course['id']}",
                    json={"version": generated["version"], "title": "用户确认的课程"},
                )
            )
            first_course = generated["courses"][0]
            points = first_course["knowledge_points"]
            generated = _ok(
                http.post(
                    f"/api/course-architecture/drafts/{automatic['id']}/knowledge-points/reorder",
                    json={
                        "version": generated["version"],
                        "items": [
                            {"id": point["id"], "order_index": len(points) - index - 1}
                            for index, point in enumerate(points)
                        ],
                    },
                )
            )
            generated = _ok(
                http.post(
                    f"/api/course-architecture/drafts/{automatic['id']}/courses",
                    json={"version": generated["version"], "title": "移动目标课程"},
                )
            )
            first_course, second_course = generated["courses"][:2]
            point = first_course["knowledge_points"][0]
            generated = _ok(
                http.post(
                    f"/api/course-architecture/drafts/{automatic['id']}/knowledge-points/move",
                    json={
                        "version": generated["version"],
                        "knowledge_point_id": point["id"],
                        "target_course_id": second_course["id"],
                        "order_index": 0,
                    },
                )
            )
            moved = generated["courses"][1]["knowledge_points"][0]
            assert moved["sources"]
            generated = _ok(
                http.post(
                    f"/api/course-architecture/drafts/{automatic['id']}/knowledge-points",
                    json={
                        "version": generated["version"],
                        "draft_course_id": second_course["id"],
                        "title": "待合并知识点",
                    },
                )
            )
            merge_point = generated["courses"][1]["knowledge_points"][-1]
            generated = _ok(
                http.post(
                    f"/api/course-architecture/drafts/{automatic['id']}/knowledge-points/{merge_point['id']}/sources",
                    json={
                        "version": generated["version"],
                        "material_id": material["id"],
                        "material_chunk_id": chunks[-1]["id"],
                        "source_role": "supporting",
                    },
                )
            )
            generated = _ok(
                http.post(
                    f"/api/course-architecture/drafts/{automatic['id']}/knowledge-points/merge",
                    json={
                        "version": generated["version"],
                        "keep_knowledge_point_id": moved["id"],
                        "merge_knowledge_point_ids": [merge_point["id"]],
                        "title": "合并后的知识点",
                    },
                )
            )
            merged = generated["courses"][1]["knowledge_points"][0]
            assert merged["title"] == "合并后的知识点"
            assert len(merged["sources"]) >= 1

            # Scenario 4: a changed material snapshot blocks a previously ready draft.
            stale = build_manual_ready_draft(http, goal, material, chunks)
            _ok(http.post(f"/api/materials/{material['id']}/process"))
            stale = _ok(
                http.post(
                    f"/api/course-architecture/drafts/{stale['id']}/validate",
                    json={"version": stale["version"]},
                )
            )
            assert stale["quality_status"] == "stale"
            blocked = http.post(
                f"/api/course-architecture/drafts/{stale['id']}/publish",
                json={
                    "version": stale["version"],
                    "publish_request_id": "v9-http-stale-0001",
                    "confirmed": True,
                },
            )
            assert blocked.status_code == 409

            # Scenario 8: provider failure leaves an explicit, empty, retryable draft.
            provider["current"] = FakeArchitectureLLM(fail=True)
            failed_draft = create_draft(http, goal, material, "失败不造假")
            failed = http.post(
                f"/api/course-architecture/drafts/{failed_draft['id']}/generate",
                json={
                    "version": failed_draft["version"],
                    "request_id": "v9-http-generate-failure",
                },
            )
            assert failed.status_code == 503
            failed_draft = _ok(
                http.get(f"/api/course-architecture/drafts/{failed_draft['id']}")
            )
            assert failed_draft["status"] == "failed"
            assert failed_draft["courses"] == []
            assert failed_draft["last_error_message"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()

    assert not thread.is_alive()
