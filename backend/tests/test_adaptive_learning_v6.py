from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.core.config import Settings
from app.services.adaptive_learning.mastery import KnowledgeMasteryService


def prepare_point(client, *, order=0):
    http, _ = client
    goal = http.post("/api/learning-goals", json={
        "title": "V6 学习目标", "description": "", "target_date": None,
        "daily_minutes": 30, "current_level": "入门", "status": "active",
    }).json()
    course = http.post("/api/courses", json={
        "learning_goal_id": goal["id"], "title": "自适应学习",
        "description": "V6", "status": "active",
    }).json()
    point = http.post(f"/api/courses/{course['id']}/knowledge-points", json={
        "title": "确定性掌握度", "description": "规则计算", "order_index": order,
        "estimated_minutes": 20, "status": "learning",
    }).json()
    return goal, course, point


def evidence(kind, score, weight, occurred_at, object_id):
    return SimpleNamespace(
        id=object_id, evidence_type=kind, normalized_score=score, weight=weight,
        occurred_at=occurred_at,
    )


def test_no_evidence_is_unassessed_not_zero(client):
    _, _, point = prepare_point(client)
    rebuilt = client[0].post("/api/mastery/rebuild", json={"knowledge_point_id": point["id"]})
    assert rebuilt.status_code == 200
    detail = client[0].get(f"/api/mastery/{point['id']}").json()
    assert detail["mastery_score"] is None
    assert detail["mastery_level"] == "unassessed"
    assert detail["confidence_score"] == 0
    assert detail["review_schedule"] is None


def test_self_assessment_is_idempotent_and_low_weight(client):
    _, _, point = prepare_point(client)
    payload = {"rating": 5, "request_id": "self-rating-0001"}
    first = client[0].put(f"/api/mastery/{point['id']}/self-assessment", json=payload)
    second = client[0].put(f"/api/mastery/{point['id']}/self-assessment", json=payload)
    assert first.status_code == second.status_code == 200
    assert second.json()["evidence_count"] == 1
    assert second.json()["mastery_score"] == 100
    assert second.json()["confidence_score"] < 50


def test_mastery_missing_categories_are_renormalized():
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    settings = Settings(_env_file=None)
    service = KnowledgeMasteryService(None, settings, now=now)
    result = service.calculate([
        evidence("objective_quiz", 80, .40, now, 1),
        evidence("short_answer_quiz", 40, .25, now, 2),
    ])
    assert result["mastery_score"] == 64.62
    assert result["mastery_level"] == "proficient"


def test_mastery_time_decay_and_recent_n_are_deterministic():
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    settings = Settings(_env_file=None, mastery_max_evidence_per_type=2, mastery_evidence_half_life_days=30)
    service = KnowledgeMasteryService(None, settings, now=now)
    rows = [
        evidence("objective_quiz", 100, .4, now, 3),
        evidence("objective_quiz", 60, .4, now - timedelta(days=30), 2),
        evidence("objective_quiz", 0, .4, now - timedelta(days=60), 1),
    ]
    first = service.calculate(rows)
    second = service.calculate(rows)
    assert first == second
    assert first["selected_evidence_ids"] == [2, 3]
    assert first["mastery_score"] == 86.67


def test_direct_quiz_outweighs_task_completion():
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    settings = Settings(_env_file=None)
    result = KnowledgeMasteryService(None, settings, now=now).calculate([
        evidence("objective_quiz", 20, .40, now, 1),
        evidence("task_completion", 100, .08, now, 2),
    ])
    assert result["mastery_score"] == 33.33
    assert result["mastery_level"] == "beginner"


def test_self_assessment_validation(client):
    _, _, point = prepare_point(client)
    response = client[0].put(f"/api/mastery/{point['id']}/self-assessment", json={
        "rating": 6, "request_id": "invalid-rating-1",
    })
    assert response.status_code == 422


def test_mastery_list_weak_points_and_detail(client):
    _, course, point = prepare_point(client)
    client[0].put(f"/api/mastery/{point['id']}/self-assessment", json={
        "rating": 2, "request_id": "weak-rating-0001",
    })
    listing = client[0].get(f"/api/mastery?course_id={course['id']}").json()
    assert listing["total"] == 1
    assert listing["items"][0]["mastery_level"] == "developing"
    weak = client[0].get(f"/api/mastery/weak-points?course_id={course['id']}").json()
    assert weak[0]["classification"] == "weak"
    detail = client[0].get(f"/api/mastery/{point['id']}").json()
    assert detail["algorithm_version"] == "mastery-rule-v1"
    assert detail["snapshots"]
    assert detail["evidence"][0]["source_type"] == "self_assessment"


def test_review_and_recommendation_accept_are_confirmed_and_idempotent(client):
    _, _, point = prepare_point(client)
    client[0].put(f"/api/mastery/{point['id']}/self-assessment", json={
        "rating": 1, "request_id": "review-rating-001",
    })
    recommendations = client[0].get("/api/adaptive-recommendations").json()
    assert len(recommendations) == 1
    recommendation_id = recommendations[0]["id"]
    denied = client[0].post(f"/api/adaptive-recommendations/{recommendation_id}/accept", json={
        "request_id": "accept-review-001", "confirmed": False,
    })
    assert denied.status_code == 409
    assert client[0].get("/api/today").json()["tasks"] == []
    accepted = client[0].post(f"/api/adaptive-recommendations/{recommendation_id}/accept", json={
        "request_id": "accept-review-001", "confirmed": True,
    })
    assert accepted.status_code == 200
    replay = client[0].post(f"/api/adaptive-recommendations/{recommendation_id}/accept", json={
        "request_id": "accept-review-001", "confirmed": True,
    }).json()
    assert replay["idempotent_replay"] is True
    assert replay["task"]["id"] == accepted.json()["task"]["id"]


def test_recommendation_reject_does_not_create_task(client):
    _, _, point = prepare_point(client)
    client[0].put(f"/api/mastery/{point['id']}/self-assessment", json={
        "rating": 1, "request_id": "reject-rating-001",
    })
    recommendation_id = client[0].get("/api/adaptive-recommendations").json()[0]["id"]
    rejected = client[0].post(f"/api/adaptive-recommendations/{recommendation_id}/reject")
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert client[0].get("/api/today").json()["tasks"] == []
