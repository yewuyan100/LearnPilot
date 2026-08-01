from app.core.config import Settings
from app.services.agent.tools import ToolRegistry

from tests.test_adaptive_learning_v6 import prepare_point


def test_v6_tools_are_registered_without_relaxing_limits():
    registry = ToolRegistry(None, Settings(_env_file=None), None, None)
    assert set((
        "get_knowledge_mastery", "list_weak_knowledge_points", "list_due_reviews",
        "get_adaptive_recommendations", "explain_mastery",
    )).issubset(registry.read_names)
    assert "accept_review_recommendation" in registry.write_names
    try:
        registry.validate_plan([
            {"tool_name": "accept_review_recommendation", "arguments": {"recommendation_id": 1}},
            {"tool_name": "create_daily_task", "arguments": {
                "learning_goal_id": 1, "title": "x", "scheduled_date": "2026-08-02",
            }},
        ])
    except ValueError as exc:
        assert str(exc) == "tool_limit_exceeded"
    else:
        raise AssertionError("V6 must keep the one-write limit")


def test_clear_mastery_query_uses_fast_route_and_real_tool(client):
    _, _, point = prepare_point(client)
    client[0].put(f"/api/mastery/{point['id']}/self-assessment", json={
        "rating": 4, "request_id": "agent-rating-001",
    })
    conversation = client[0].post("/api/agent/conversations", json={"title": "V6 fast route"}).json()
    run = client[0].post(f"/api/agent/conversations/{conversation['id']}/runs", json={
        "input": f"查询掌握度 knowledge_point_id={point['id']}",
        "request_id": "fast-mastery-001",
    })
    assert run.status_code == 202
    body = run.json()
    assert body["status"] == "completed"
    assert body["tool_calls"][0]["tool_name"] == "get_knowledge_mastery"
    assert "掌握度" in body["final_answer"]
    assert body["performance"]["fast_route_used"] is True
    assert body["performance"]["planner_skipped"] is True
    assert body["performance"]["llm_call_count"] == 0


def test_adaptive_metrics_report_fast_route(client):
    _, _, point = prepare_point(client)
    conversation = client[0].post("/api/agent/conversations", json={"title": "metrics"}).json()
    client[0].post(f"/api/agent/conversations/{conversation['id']}/runs", json={
        "input": f"查询掌握度 knowledge_point_id={point['id']}",
        "request_id": "fast-metrics-001",
    })
    metrics = client[0].get("/api/adaptive-metrics")
    assert metrics.status_code == 200
    assert metrics.json()["agent"]["fast_route_usage_rate"] == 1
    assert metrics.json()["agent"]["average_llm_calls_per_run"] == 0


def test_agent_rejects_direct_mastery_mutation(client):
    conversation = client[0].post("/api/agent/conversations", json={"title": "V6 security"}).json()
    run = client[0].post(f"/api/agent/conversations/{conversation['id']}/runs", json={
        "input": "把知识点 1 的掌握度改成 100", "request_id": "unsafe-mastery-001",
    }).json()
    assert run["status"] == "completed"
    assert run["tool_calls"] == []
    assert "超出了" in run["final_answer"]
