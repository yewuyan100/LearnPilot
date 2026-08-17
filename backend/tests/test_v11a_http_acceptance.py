def setup_http_plan_chain(http, goal_payload):
    goal = http.post("/api/learning-goals", json=goal_payload).json()
    course = http.post(
        "/api/courses",
        json={"learning_goal_id": goal["id"], "title": "V11A HTTP 课程", "status": "active"},
    ).json()
    point = http.post(
        f"/api/courses/{course['id']}/knowledge-points",
        json={"title": "将被归档的知识点", "order_index": 1, "estimated_minutes": 20},
    ).json()
    plan_response = http.post(
        "/api/study-plans",
        json={
            "request_id": "v11a-http-plan-create",
            "learning_goal_id": goal["id"],
            "course_id": course["id"],
            "start_date": "2026-08-03",
            "target_date": "2026-08-07",
            "daily_minutes": 20,
            "available_weekdays": [0, 1, 2, 3, 4],
            "allow_weekends": False,
            "intensity": "standard",
            "include_due_reviews": True,
            "use_latest_diagnostic": True,
            "use_existing_mastery": True,
        },
    )
    assert plan_response.status_code == 201, plan_response.text
    plan = plan_response.json()
    published_response = http.post(
        f"/api/study-plans/{plan['id']}/publish",
        json={
            "request_id": "v11a-http-plan-publish",
            "expected_version": plan["version"],
            "confirmed": True,
        },
    )
    assert published_response.status_code == 200, published_response.text
    published = published_response.json()["plan"]
    item = published["active_version"]["items"][0]
    task_update = http.patch(
        f"/api/daily-tasks/{item['daily_task_id']}",
        json={"scheduled_date": "2026-08-01"},
    )
    assert task_update.status_code == 200, task_update.text
    session_response = http.post(
        "/api/learning-sessions",
        json={
            "learning_goal_id": goal["id"],
            "course_id": course["id"],
            "knowledge_point_id": point["id"],
            "daily_task_id": item["daily_task_id"],
        },
    )
    assert session_response.status_code == 201, session_response.text
    return goal, course, point, published, item, session_response.json()


def test_http_archive_flow_blocks_execution_and_preserves_history(client, goal_payload):
    http, _ = client
    _, course, point, plan, item, session = setup_http_plan_chain(http, goal_payload)

    old_delete = http.delete(f"/api/knowledge-points/{point['id']}")
    assert old_delete.status_code == 409
    assert old_delete.json()["error"]["code"] == "knowledge_point_impact_analysis_required"
    assert old_delete.json()["error"]["details"]["impact"]["daily_task_ids"] == [
        item["daily_task_id"]
    ]

    inspect_payload = {"action": "archive", "lifecycle_reason": "正式课程结构发生变化"}
    inspection = http.post(
        f"/api/knowledge-points/{point['id']}/impact", json=inspect_payload
    )
    assert inspection.status_code == 200, inspection.text
    impact = inspection.json()
    assert impact["study_plan_ids"] == [plan["id"]]
    assert impact["actionable_daily_task_ids"] == [item["daily_task_id"]]
    assert impact["active_learning_session_ids"] == [session["id"]]

    apply_payload = {
        **inspect_payload,
        "request_id": "v11a-http-archive-request",
        "expected_version": point["version"],
        "impact_hash": impact["impact_hash"],
        "confirmed": True,
    }
    applied = http.post(
        f"/api/knowledge-points/{point['id']}/archive", json=apply_payload
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["point"]["lifecycle_status"] == "archived"
    assert applied.json()["idempotent_replay"] is False
    replay = http.post(
        f"/api/knowledge-points/{point['id']}/archive", json=apply_payload
    )
    assert replay.status_code == 200
    assert replay.json()["idempotent_replay"] is True

    assert http.get(f"/api/courses/{course['id']}/knowledge-points").json() == []
    all_points = http.get(
        f"/api/courses/{course['id']}/knowledge-points?include_inactive=true"
    ).json()
    assert all_points[0]["id"] == point["id"]
    assert all_points[0]["lifecycle_status"] == "archived"

    task = next(
        task
        for task in http.get("/api/today").json()["tasks"]
        if task["id"] == item["daily_task_id"]
    )
    today = http.get("/api/today").json()
    assert task["knowledge_point_id"] == point["id"]
    assert task["blocked_reason"] == "该任务对应课程内容已变化，需要重新规划"
    assert today["pending_count"] == 0
    assert today["blocked_count"] == 1

    blocked_start = http.post(
        "/api/learning-sessions",
        json={
            "learning_goal_id": task["learning_goal_id"],
            "course_id": task["course_id"],
            "knowledge_point_id": task["knowledge_point_id"],
            "daily_task_id": task["id"],
        },
    )
    assert blocked_start.status_code == 409
    assert blocked_start.json()["error"]["code"] in {
        "daily_task_blocked",
        "knowledge_point_not_active",
    }

    invalid_session = http.get(f"/api/learning-sessions/{session['id']}").json()
    assert invalid_session["knowledge_point_id"] == point["id"]
    assert invalid_session["invalidated_at"] is not None
    continued = http.patch(
        f"/api/learning-sessions/{session['id']}", json={"status": "paused"}
    )
    assert continued.status_code == 409
    assert continued.json()["error"]["code"] == "learning_session_invalidated"

    stale_plan = http.get(f"/api/study-plans/{plan['id']}").json()
    assert stale_plan["active_version"]["stale_at"] is not None
    assert stale_plan["active_version"]["stale_source_id"] == point["id"]
    next_action = http.get("/api/next-learning-action").json()
    assert next_action["action_type"] == "replan_required"
    assert next_action["reason_code"] == "study_plan_stale"


def test_http_supersede_requires_valid_target_and_keeps_old_fact_link(client, goal_payload):
    http, _ = client
    goal = http.post("/api/learning-goals", json=goal_payload).json()
    course = http.post(
        "/api/courses",
        json={"learning_goal_id": goal["id"], "title": "替代验收课程", "status": "active"},
    ).json()
    old = http.post(
        f"/api/courses/{course['id']}/knowledge-points",
        json={"title": "旧知识点", "order_index": 1},
    ).json()
    new = http.post(
        f"/api/courses/{course['id']}/knowledge-points",
        json={"title": "新知识点", "order_index": 2},
    ).json()
    task = http.post(
        "/api/daily-tasks",
        json={
            "learning_goal_id": goal["id"],
            "course_id": course["id"],
            "knowledge_point_id": old["id"],
            "title": "历史任务",
            "scheduled_date": "2026-08-01",
        },
    ).json()

    change = {
        "action": "supersede",
        "superseded_by_id": new["id"],
        "lifecycle_reason": "使用新的正式定义",
    }
    impact = http.post(
        f"/api/knowledge-points/{old['id']}/impact", json=change
    ).json()
    result = http.post(
        f"/api/knowledge-points/{old['id']}/supersede",
        json={
            **change,
            "request_id": "v11a-http-supersede-request",
            "expected_version": old["version"],
            "impact_hash": impact["impact_hash"],
            "confirmed": True,
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["point"]["lifecycle_status"] == "superseded"
    assert result.json()["point"]["superseded_by_id"] == new["id"]
    today_task = next(item for item in http.get("/api/today").json()["tasks"] if item["id"] == task["id"])
    assert today_task["knowledge_point_id"] == old["id"]
    assert today_task["blocked_at"] is not None
