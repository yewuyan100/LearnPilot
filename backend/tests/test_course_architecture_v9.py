import ast
import re
import threading

from app.api.deps import get_llm_provider
from app.main import app
from app.services.knowledge_point_sources import KnowledgePointSourceService
from app.services.llm.base import LLMUsage, StructuredLLMResult
from app.services.llm.errors import LLMOutputInvalidError
from tests.test_rag import FakeLLMProvider


class FakeArchitectureLLM:
    model_name = "fake-course-architect"

    def __init__(self, *, invalid_chunk: bool = False, fail: bool = False):
        self.invalid_chunk = invalid_chunk
        self.fail = fail
        self.calls = 0
        self.messages = []

    def generate_structured(self, *, messages, schema, temperature=None, max_output_tokens=None):
        self.calls += 1
        self.messages.append(messages)
        if self.fail:
            from app.services.llm.errors import LLMUnavailableError
            raise LLMUnavailableError("unavailable")
        match = re.search(r"允许的 chunk IDs：(\[[^\]]+\])", messages[-1]["content"])
        allowed = ast.literal_eval(match.group(1))
        first = 999999 if self.invalid_chunk else allowed[0]
        value = schema.model_validate(
            {
                "section_summary": "资料介绍协议基础和可靠调用。",
                "courses": [
                    {
                        "title": "协议基础",
                        "description": "从真实资料整理",
                        "learning_outcomes": ["理解协议边界"],
                        "knowledge_points": [
                            {
                                "title": "协议定位",
                                "description": "明确协议解决的问题",
                                "learning_objectives": ["解释协议用途"],
                                "key_terms": ["协议"],
                                "difficulty_label": "beginner",
                                "source_chunk_ids": [first],
                                "prerequisite_titles": [],
                            },
                            {
                                "title": "可靠调用",
                                "description": "理解受控调用",
                                "learning_objectives": ["识别调用边界"],
                                "key_terms": ["调用"],
                                "difficulty_label": "intermediate",
                                "source_chunk_ids": [first],
                                "prerequisite_titles": ["协议定位"],
                            },
                        ],
                    }
                ],
                "prerequisites": [
                    {
                        "prerequisite_title": "协议定位",
                        "dependent_title": "可靠调用",
                        "rationale": "先理解定位再学习调用",
                        "confidence": 0.9,
                    }
                ],
                "unresolved_issues": [],
            }
        )
        return StructuredLLMResult(
            value=value,
            usage=LLMUsage(input_tokens=100, output_tokens=80),
            model=self.model_name,
            latency_ms=5,
        )


class RetryOnceArchitectureLLM(FakeArchitectureLLM):
    def generate_structured(self, **kwargs):
        if self.calls == 0:
            self.calls += 1
            raise LLMOutputInvalidError("invalid JSON", reason="invalid_json")
        return super().generate_structured(**kwargs)


class BlockingArchitectureLLM(FakeArchitectureLLM):
    def __init__(self):
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def generate_structured(self, **kwargs):
        self.started.set()
        assert self.release.wait(timeout=5), "test did not release the provider"
        return super().generate_structured(**kwargs)


def create_goal(http, goal_payload, title="V9 目标"):
    response = http.post("/api/learning-goals", json={**goal_payload, "title": title})
    assert response.status_code == 201
    return response.json()


def create_ready_material(http, name="architect.md"):
    body = (
        "# 协议基础\n协议连接学习应用与受控能力。\n\n"
        "## 可靠调用\n调用必须经过明确边界和确定性验证。\n" * 6
    ).encode()
    uploaded = http.post(
        "/api/materials/upload",
        files={"file": (name, body, "text/markdown")},
    )
    assert uploaded.status_code == 201
    material = uploaded.json()
    processed = http.post(f"/api/materials/{material['id']}/process")
    assert processed.status_code == 200, processed.text
    material = processed.json()
    assert material["ingestion_status"] == "completed"
    assert material["indexing_status"] == "completed"
    chunks = http.get(f"/api/materials/{material['id']}/chunks?page=1&page_size=20").json()
    return material, chunks["items"]


def create_draft(http, goal, material, title="可验证草案"):
    response = http.post(
        "/api/course-architecture/drafts",
        json={
            "learning_goal_id": goal["id"],
            "material_ids": [material["id"]],
            "title": title,
            "description": "只在确认后发布",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def build_manual_ready_draft(http, goal, material, chunks):
    draft = create_draft(http, goal, material)
    draft = http.post(
        f"/api/course-architecture/drafts/{draft['id']}/courses",
        json={"version": draft["version"], "title": "正式发布候选", "order_index": 0},
    ).json()
    course_id = draft["courses"][0]["id"]
    for index, title in enumerate(("基础定位", "可靠边界")):
        response = http.post(
            f"/api/course-architecture/drafts/{draft['id']}/knowledge-points",
            json={
                "version": draft["version"],
                "draft_course_id": course_id,
                "title": title,
                "order_index": index,
            },
        )
        assert response.status_code == 200, response.text
        draft = response.json()
    for index, point in enumerate(draft["courses"][0]["knowledge_points"]):
        response = http.post(
            f"/api/course-architecture/drafts/{draft['id']}/knowledge-points/{point['id']}/sources",
            json={
                "version": draft["version"],
                "material_id": material["id"],
                "material_chunk_id": chunks[index % len(chunks)]["id"],
                "source_role": "primary",
            },
        )
        assert response.status_code == 200, response.text
        draft = response.json()
    points = draft["courses"][0]["knowledge_points"]
    response = http.post(
        f"/api/course-architecture/drafts/{draft['id']}/prerequisites",
        json={
            "version": draft["version"],
            "prerequisite_knowledge_point_id": points[0]["id"],
            "dependent_knowledge_point_id": points[1]["id"],
            "rationale": "先基础后边界",
        },
    )
    assert response.status_code == 200, response.text
    draft = response.json()
    validated = http.post(
        f"/api/course-architecture/drafts/{draft['id']}/validate",
        json={"version": draft["version"]},
    )
    assert validated.status_code == 200, validated.text
    return validated.json()


def test_v9a_draft_preflight_duplicate_materials_and_archive(client, goal_payload):
    http, _ = client
    goal = create_goal(http, goal_payload)
    material, _ = create_ready_material(http)

    missing_goal = http.post(
        "/api/course-architecture/drafts",
        json={"learning_goal_id": 999999, "material_ids": [material["id"]]},
    )
    assert missing_goal.status_code == 404
    duplicate_material = http.post(
        "/api/course-architecture/drafts",
        json={
            "learning_goal_id": goal["id"],
            "material_ids": [material["id"], material["id"]],
        },
    )
    assert duplicate_material.status_code == 422

    draft = create_draft(http, goal, material, "待归档草案")
    archived = http.delete(
        f"/api/course-architecture/drafts/{draft['id']}?version={draft['version']}"
    )
    assert archived.status_code == 204
    assert http.get(f"/api/course-architecture/drafts/{draft['id']}").json()["status"] == "archived"
    hidden = http.get("/api/course-architecture/drafts").json()
    assert all(item["id"] != draft["id"] for item in hidden["items"])

    archived_material, _ = create_ready_material(http, "archived.md")
    assert http.post(f"/api/materials/{archived_material['id']}/archive").status_code == 200
    unavailable = http.post(
        "/api/course-architecture/drafts",
        json={
            "learning_goal_id": goal["id"],
            "material_ids": [archived_material["id"]],
        },
    )
    assert unavailable.status_code == 409
    assert unavailable.json()["error"]["details"]["reason"] == "archived"


def test_v9a_manual_draft_crud_versions_sources_and_dag(client, goal_payload):
    http, _ = client
    goal = create_goal(http, goal_payload)
    material, chunks = create_ready_material(http)
    draft = create_draft(http, goal, material)
    assert draft["status"] == "draft"
    assert draft["materials"][0]["stale"] is False

    conflict = http.patch(
        f"/api/course-architecture/drafts/{draft['id']}",
        json={"version": draft["version"] + 1, "title": "冲突"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "draft_version_conflict"

    ready = build_manual_ready_draft(http, goal, material, chunks)
    assert ready["status"] == "ready"
    assert ready["quality_report"]["blocker_count"] == 0
    points = ready["courses"][0]["knowledge_points"]
    cycle = http.post(
        f"/api/course-architecture/drafts/{ready['id']}/prerequisites",
        json={
            "version": ready["version"],
            "prerequisite_knowledge_point_id": points[1]["id"],
            "dependent_knowledge_point_id": points[0]["id"],
        },
    )
    assert cycle.status_code == 409
    assert cycle.json()["error"]["code"] == "draft_prerequisite_cycle"


def test_v9a_rejects_unavailable_and_out_of_scope_sources(client, goal_payload):
    http, _ = client
    goal = create_goal(http, goal_payload)
    uploaded = http.post(
        "/api/materials/upload",
        files={"file": ("pending.md", b"# pending\nnot processed", "text/markdown")},
    ).json()
    rejected = http.post(
        "/api/course-architecture/drafts",
        json={"learning_goal_id": goal["id"], "material_ids": [uploaded["id"]]},
    )
    assert rejected.status_code == 409
    assert rejected.json()["error"]["details"]["reason"] == "not_processed"

    material, chunks = create_ready_material(http, "one.md")
    other, other_chunks = create_ready_material(http, "two.md")
    draft = create_draft(http, goal, material)
    draft = http.post(
        f"/api/course-architecture/drafts/{draft['id']}/courses",
        json={"version": draft["version"], "title": "课程"},
    ).json()
    draft = http.post(
        f"/api/course-architecture/drafts/{draft['id']}/knowledge-points",
        json={"version": draft["version"], "draft_course_id": draft["courses"][0]["id"], "title": "知识点"},
    ).json()
    point = draft["courses"][0]["knowledge_points"][0]
    response = http.post(
        f"/api/course-architecture/drafts/{draft['id']}/knowledge-points/{point['id']}/sources",
        json={"version": draft["version"], "material_id": other["id"], "material_chunk_id": other_chunks[0]["id"]},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "draft_source_out_of_scope"


def test_v9b_structured_generation_is_traceable_idempotent_and_injection_safe(client, goal_payload):
    http, _ = client
    provider = FakeArchitectureLLM()
    app.dependency_overrides[get_llm_provider] = lambda: provider
    goal = create_goal(http, goal_payload)
    material, _ = create_ready_material(http)
    draft = create_draft(http, goal, material)
    generated = http.post(
        f"/api/course-architecture/drafts/{draft['id']}/generate",
        json={"version": draft["version"], "request_id": "generate-request-001"},
    )
    assert generated.status_code == 200, generated.text
    result = generated.json()
    assert result["generation_status"] == "completed"
    assert result["courses"][0]["knowledge_points"][0]["sources"][0]["context_url"].startswith("/materials/")
    assert any(event["event"] == "section.completed" for event in result["generation_progress"]["events"])
    assert "不可信学习内容" in provider.messages[0][0]["content"]
    initial_calls = provider.calls
    assert initial_calls > 1
    repeated = http.post(
        f"/api/course-architecture/drafts/{draft['id']}/generate",
        json={"version": result["version"], "request_id": "generate-request-001"},
    )
    assert repeated.status_code == 200
    assert provider.calls == initial_calls
    events = http.get(f"/api/course-architecture/drafts/{draft['id']}/events")
    assert events.status_code == 200
    assert "event: draft.ready" in events.text


def test_v9b_structured_generation_retries_a_transient_invalid_output(client, goal_payload):
    http, _ = client
    provider = RetryOnceArchitectureLLM()
    app.dependency_overrides[get_llm_provider] = lambda: provider
    goal = create_goal(http, goal_payload)
    material, _ = create_ready_material(http)
    draft = create_draft(http, goal, material)

    generated = http.post(
        f"/api/course-architecture/drafts/{draft['id']}/generate",
        json={"version": draft["version"], "request_id": "generate-retry-001"},
    )

    assert generated.status_code == 200, generated.text
    assert provider.calls > 1
    assert generated.json()["courses"]


def test_v9b_invalid_chunk_and_missing_provider_never_create_fake_points(client, goal_payload):
    http, _ = client
    goal = create_goal(http, goal_payload)
    material, _ = create_ready_material(http)
    draft = create_draft(http, goal, material, "无模型草案")
    unavailable = http.post(
        f"/api/course-architecture/drafts/{draft['id']}/generate",
        json={"version": draft["version"], "request_id": "missing-provider-001"},
    )
    assert unavailable.status_code == 409
    after = http.get(f"/api/course-architecture/drafts/{draft['id']}").json()
    assert after["courses"] == []
    assert after["generation_status"] == "failed"

    provider = FakeArchitectureLLM(invalid_chunk=True)
    app.dependency_overrides[get_llm_provider] = lambda: provider
    second = create_draft(http, goal, material, "越界草案")
    invalid = http.post(
        f"/api/course-architecture/drafts/{second['id']}/generate",
        json={"version": second["version"], "request_id": "invalid-chunk-001"},
    )
    assert invalid.status_code == 422
    after_invalid = http.get(f"/api/course-architecture/drafts/{second['id']}").json()
    assert after_invalid["courses"] == []
    assert after_invalid["generation_status"] == "failed"


def test_v9b_cancel_in_flight_single_batch_does_not_persist_candidates(client, goal_payload):
    http, _ = client
    provider = BlockingArchitectureLLM()
    app.dependency_overrides[get_llm_provider] = lambda: provider
    goal = create_goal(http, goal_payload)
    material, _ = create_ready_material(http)
    draft = create_draft(http, goal, material, "可取消草案")
    response: dict[str, object] = {}

    def run_generation():
        response["value"] = http.post(
            f"/api/course-architecture/drafts/{draft['id']}/generate",
            json={"version": draft["version"], "request_id": "cancel-request-001"},
        )

    worker = threading.Thread(target=run_generation)
    worker.start()
    assert provider.started.wait(timeout=5)
    running = http.get(f"/api/course-architecture/drafts/{draft['id']}").json()
    assert running["generation_status"] == "running"
    cancelled = http.post(
        f"/api/course-architecture/drafts/{draft['id']}/generate/cancel",
        json={"version": running["version"]},
    )
    assert cancelled.status_code == 200, cancelled.text
    provider.release.set()
    worker.join(timeout=5)
    assert not worker.is_alive()
    generated = response["value"]
    assert generated.status_code == 200
    result = generated.json()
    assert result["generation_status"] == "cancelled"
    assert result["courses"] == []


def test_v9c_publish_is_atomic_idempotent_and_enables_v8_scope(client, goal_payload):
    http, _ = client
    goal = create_goal(http, goal_payload)
    material, chunks = create_ready_material(http)
    ready = build_manual_ready_draft(http, goal, material, chunks)
    payload = {
        "version": ready["version"],
        "publish_request_id": "publish-request-001",
        "confirmed": True,
    }
    published = http.post(
        f"/api/course-architecture/drafts/{ready['id']}/publish", json=payload
    )
    assert published.status_code == 200, published.text
    result = published.json()
    assert len(result["course_ids"]) == 1
    assert len(result["knowledge_point_ids"]) == 2
    assert result["material_link_count"] == 1
    assert result["source_count"] == 2
    assert result["prerequisite_count"] == 1
    course_id = result["course_ids"][0]
    assert [item["material_id"] for item in http.get(f"/api/courses/{course_id}/materials").json()] == [material["id"]]
    for point_id in result["knowledge_point_ids"]:
        assert http.get(f"/api/knowledge-points/{point_id}/sources").json()[0]["material_id"] == material["id"]
    rag_provider = FakeLLMProvider([{
        "answerable": True,
        "blocks": [{
            "content_markdown": "正式课程范围只使用已发布来源。",
            "source_ids": ["S1"],
        }],
        "refusal_reason": None,
    }])
    app.dependency_overrides[get_llm_provider] = lambda: rag_provider
    conversation = http.post("/api/rag/conversations", json={"title": "V9 发布范围"}).json()
    scoped = http.post(
        f"/api/rag/conversations/{conversation['id']}/ask",
        json={
            "question": "正式课程使用了哪些真实资料？",
            "request_id": "v9-published-scope-0001",
            "course_id": course_id,
            "top_k": 3,
        },
    )
    assert scoped.status_code == 200, scoped.text
    scoped_body = scoped.json()
    assert scoped_body["retrieval"]["resolved_material_ids"] == [material["id"]]
    assert {item["material_id"] for item in scoped_body["assistant_message"]["citations"]} == {material["id"]}
    repeated = http.post(
        f"/api/course-architecture/drafts/{ready['id']}/publish", json=payload
    )
    assert repeated.status_code == 200
    assert repeated.json()["course_ids"] == result["course_ids"]
    assert len(http.get("/api/courses").json()) == 1
    immutable = http.patch(
        f"/api/course-architecture/drafts/{ready['id']}",
        json={"version": repeated.json().get("version", ready["version"]), "title": "不应修改"},
    )
    assert immutable.status_code == 409
    new_version = http.post(
        f"/api/course-architecture/drafts/{ready['id']}/versions"
    )
    assert new_version.status_code == 201, new_version.text
    editable = new_version.json()
    assert editable["id"] != ready["id"]
    assert editable["status"] == "review_required"
    assert editable["courses"][0]["published_course_id"] is None
    assert all(
        point["sources"]
        for course in editable["courses"]
        for point in course["knowledge_points"]
    )


def test_v9c_stale_material_blocks_publish(client, goal_payload):
    http, _ = client
    goal = create_goal(http, goal_payload)
    material, chunks = create_ready_material(http)
    ready = build_manual_ready_draft(http, goal, material, chunks)
    assert http.post(f"/api/materials/{material['id']}/archive").status_code == 200
    report = http.get(f"/api/course-architecture/drafts/{ready['id']}/quality-report").json()
    assert report["status"] == "stale"
    published = http.post(
        f"/api/course-architecture/drafts/{ready['id']}/publish",
        json={"version": ready["version"], "publish_request_id": "stale-publish-001", "confirmed": True},
    )
    assert published.status_code == 409


def test_v9c_publish_failure_rolls_back_every_formal_entity(client, goal_payload, monkeypatch):
    http, _ = client
    goal = create_goal(http, goal_payload)
    material, chunks = create_ready_material(http)
    ready = build_manual_ready_draft(http, goal, material, chunks)

    def fail_source(*args, **kwargs):
        raise RuntimeError("simulated source failure")

    monkeypatch.setattr(KnowledgePointSourceService, "create", fail_source)
    failed = http.post(
        f"/api/course-architecture/drafts/{ready['id']}/publish",
        json={"version": ready["version"], "publish_request_id": "rollback-publish-001", "confirmed": True},
    )
    assert failed.status_code == 500
    assert http.get("/api/courses").json() == []
    assert http.get(f"/api/materials/{material['id']}/learning-links").json() == []
    draft = http.get(f"/api/course-architecture/drafts/{ready['id']}").json()
    assert draft["status"] == "review_required"
