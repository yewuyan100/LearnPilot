from __future__ import annotations

from pathlib import Path
import socket
from threading import Thread
import time

import httpx
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
import uvicorn

from app.api.deps import get_embedder, get_llm_provider
from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from tests.fakes import FakeEmbedder, FakeLearningLLM
from tests.test_rag import FakeLLMProvider


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _assert_ok(response: httpx.Response, expected: int = 200) -> dict:
    assert response.status_code == expected, response.text
    return response.json() if response.content else {}


def test_v8_real_tcp_http_material_learning_chain(tmp_path: Path, goal_payload):
    """Exercise V8 through a real TCP socket while every resource stays temporary."""
    database_path = tmp_path / "v8-http.sqlite3"
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
    )
    provider = {"current": FakeLLMProvider([])}

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
    assert server.started, "isolated V8 HTTP server did not start"

    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=30) as http:
            openapi = _assert_ok(http.get("/openapi.json"))
            assert "/api/materials/{material_id}/learning-links" in openapi["paths"]
            assert "/api/knowledge-points/{knowledge_point_id}/sources" in openapi["paths"]
            assert "MaterialLearningLinkCreate" in openapi["components"]["schemas"]
            goal = _assert_ok(
                http.post(
                    "/api/learning-goals",
                    json={**goal_payload, "title": "V8 HTTP Goal"},
                ),
                201,
            )
            course = _assert_ok(
                http.post(
                    "/api/courses",
                    json={
                        "learning_goal_id": goal["id"],
                        "title": "V8 scoped course",
                        "status": "active",
                    },
                ),
                201,
            )
            point = _assert_ok(
                http.post(
                    f"/api/courses/{course['id']}/knowledge-points",
                    json={
                        "title": "Traceable chunks",
                        "order_index": 1,
                        "estimated_minutes": 20,
                    },
                ),
                201,
            )
            empty_course = _assert_ok(
                http.post(
                    "/api/courses",
                    json={
                        "learning_goal_id": goal["id"],
                        "title": "Empty scoped course",
                        "status": "active",
                    },
                ),
                201,
            )

            def upload(name: str, body: bytes) -> dict:
                uploaded = _assert_ok(
                    http.post(
                        "/api/materials/upload",
                        files={"file": (name, body, "text/plain")},
                    ),
                    201,
                )
                return _assert_ok(http.post(f"/api/materials/{uploaded['id']}/process"))

            linked = upload(
                "linked-course.txt",
                b"Scoped course evidence explains deterministic source tracing. " * 12,
            )
            outside = upload(
                "outside-global.txt",
                b"Outside global evidence must never enter a scoped answer. " * 12,
            )
            link = _assert_ok(
                http.post(
                    f"/api/materials/{linked['id']}/learning-links",
                    json={
                        "target_type": "course",
                        "course_id": course["id"],
                        "relation_type": "primary_source",
                        "is_primary": True,
                    },
                ),
                201,
            )
            assert _assert_ok(http.get(f"/api/learning-goals/{goal['id']}/materials"))[0][
                "material_id"
            ] == linked["id"]
            course_material = _assert_ok(
                http.get(f"/api/courses/{course['id']}/materials")
            )[0]
            assert course_material["contexts"][0]["visibility"] == "direct"
            point_material = _assert_ok(
                http.get(f"/api/knowledge-points/{point['id']}/materials")
            )[0]
            assert point_material["contexts"][0]["visibility"] == "inherited"

            source_chunk = _assert_ok(
                http.get(
                    f"/api/knowledge-points/{point['id']}/source-chunks",
                    params={"material_id": linked["id"], "search": "source tracing"},
                )
            )["items"][0]
            source = _assert_ok(
                http.post(
                    f"/api/knowledge-points/{point['id']}/sources",
                    json={
                        "material_id": linked["id"],
                        "material_chunk_id": source_chunk["id"],
                        "source_type": "chunk",
                        "quoted_text": source_chunk["content"][:160],
                    },
                ),
                201,
            )
            assert source["context_url"].endswith(
                f"/materials/{linked['id']}?chunk={source_chunk['id']}"
            )

            note = _assert_ok(
                http.post(
                    "/api/notes",
                    json={
                        "title": "V8 source note",
                        "content_markdown": "A note must survive material deletion.",
                        "note_type": "material",
                        "links": [
                            {"entity_type": "material", "entity_id": linked["id"]}
                        ],
                        "sources": [
                            {
                                "material_id": linked["id"],
                                "chunk_id": source_chunk["id"],
                                "quoted_text": source_chunk["content"][:100],
                            }
                        ],
                    },
                ),
                201,
            )

            provider["current"] = FakeLLMProvider(
                [
                    {
                        "answerable": True,
                        "blocks": [{
                            "content_markdown": "The scoped evidence is traceable.",
                            "source_ids": ["S1"],
                        }],
                        "refusal_reason": None,
                    }
                ]
            )
            conversation = _assert_ok(
                http.post("/api/rag/conversations", json={"title": "V8 HTTP scope"}),
                201,
            )
            answer = _assert_ok(
                http.post(
                    f"/api/rag/conversations/{conversation['id']}/ask",
                    json={
                        "question": "What makes the evidence traceable?",
                        "request_id": "v8-http-rag-0001",
                        "course_id": course["id"],
                        "top_k": 3,
                    },
                )
            )
            assert answer["retrieval"]["resolved_material_ids"] == [linked["id"]]
            assert {
                item["material_id"] for item in answer["assistant_message"]["citations"]
            } == {linked["id"]}
            assert outside["id"] not in answer["retrieval"]["resolved_material_ids"]

            provider["current"] = FakeLLMProvider([])
            empty = _assert_ok(
                http.post(
                    f"/api/rag/conversations/{conversation['id']}/ask",
                    json={
                        "question": "Do not fall back to global sources.",
                        "request_id": "v8-http-rag-empty",
                        "course_id": empty_course["id"],
                    },
                )
            )
            assert empty["retrieval"]["resolved_material_ids"] == []
            assert empty["assistant_message"]["refusal_reason"] == "empty_material_scope"

            provider["current"] = FakeLearningLLM()
            activity = _assert_ok(
                http.post(
                    "/api/learning-activities/generate",
                    json={
                        "title": "Scoped V8 activity",
                        "course_id": course["id"],
                        "knowledge_point_id": point["id"],
                        "question_types": [
                            "single_choice",
                            "multiple_choice",
                            "true_false",
                            "short_answer",
                        ],
                        "question_count": 4,
                        "difficulty": "mixed",
                        "request_id": "v8-http-activity-0001",
                    },
                ),
                201,
            )
            activity_sources = [
                item
                for question in activity["questions"]
                for item in question["sources"]
            ]
            assert activity_sources
            assert {item["material_id"] for item in activity_sources} == {linked["id"]}

            assert http.delete(
                f"/api/materials/{linked['id']}/learning-links/{link['id']}"
            ).status_code == 204
            assert _assert_ok(http.get(f"/api/courses/{course['id']}/materials")) == []
            assert _assert_ok(http.get(f"/api/materials/{linked['id']}"))["id"] == linked["id"]

            # Re-link before exercising V7's recoverable deletion boundary.
            _assert_ok(
                http.post(
                    f"/api/materials/{linked['id']}/learning-links",
                    json={
                        "target_type": "course",
                        "course_id": course["id"],
                        "relation_type": "reference",
                    },
                ),
                201,
            )
            assert http.delete(f"/api/materials/{linked['id']}").status_code == 204
            assert http.get(f"/api/materials/{linked['id']}").status_code == 404
            assert _assert_ok(http.get(f"/api/courses/{course['id']}/materials")) == []
            assert _assert_ok(
                http.get(f"/api/knowledge-points/{point['id']}/sources")
            ) == []
            surviving_note = _assert_ok(http.get(f"/api/notes/{note['id']}"))
            assert surviving_note["sources"][0]["source_available"] is False
            assert surviving_note["links"][0]["source_available"] is False
            index_status = _assert_ok(http.get("/api/materials/index/status"))
            assert index_status["chunk_count"] == outside["indexed_chunk_count"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()

    assert not thread.is_alive()
