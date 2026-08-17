def create_goal(test_client, goal_payload):
    return test_client.post("/api/learning-goals", json=goal_payload).json()


def test_course_and_knowledge_point_crud(client, goal_payload):
    test_client, _ = client
    goal = create_goal(test_client, goal_payload)
    course = test_client.post(
        "/api/courses",
        json={"learning_goal_id": goal["id"], "title": "MCP 基础", "status": "active"},
    )
    assert course.status_code == 201
    course_id = course.json()["id"]
    updated_course = test_client.patch(
        f"/api/courses/{course_id}",
        json={"description": "手动维护的课程结构", "status": "completed"},
    )
    assert updated_course.status_code == 200
    assert updated_course.json()["description"] == "手动维护的课程结构"
    assert updated_course.json()["status"] == "completed"
    point = test_client.post(
        f"/api/courses/{course_id}/knowledge-points",
        json={"title": "MCP 的定位", "order_index": 1, "estimated_minutes": 20},
    )
    assert point.status_code == 201
    point_id = point.json()["id"]

    listed = test_client.get(f"/api/courses/{course_id}/knowledge-points")
    assert listed.status_code == 200
    assert listed.json()[0]["title"] == "MCP 的定位"
    assert test_client.patch(
        f"/api/knowledge-points/{point_id}",
        json={"status": "learning"},
    ).json()["status"] == "learning"
    hard_delete = test_client.delete(f"/api/knowledge-points/{point_id}")
    assert hard_delete.status_code == 409
    assert hard_delete.json()["error"]["code"] == "knowledge_point_impact_analysis_required"
    impact = test_client.post(
        f"/api/knowledge-points/{point_id}/impact",
        json={"action": "archive", "lifecycle_reason": "课程内容已调整"},
    ).json()
    archived = test_client.post(
        f"/api/knowledge-points/{point_id}/archive",
        json={
            "action": "archive",
            "lifecycle_reason": "课程内容已调整",
            "request_id": "archive-point-crud-001",
            "expected_version": point.json()["version"],
            "impact_hash": impact["impact_hash"],
            "confirmed": True,
        },
    )
    assert archived.status_code == 200
    assert archived.json()["point"]["lifecycle_status"] == "archived"
    assert test_client.get(f"/api/courses/{course_id}/knowledge-points").json() == []
    assert test_client.delete(f"/api/courses/{course_id}").status_code == 409


def test_today_and_learning_session_flow(client, goal_payload, business_date):
    test_client, _ = client
    goal = create_goal(test_client, goal_payload)
    course = test_client.post(
        "/api/courses",
        json={"learning_goal_id": goal["id"], "title": "MCP 基础", "status": "active"},
    ).json()
    point = test_client.post(
        f"/api/courses/{course['id']}/knowledge-points",
        json={"title": "Client 与 Server", "order_index": 1, "estimated_minutes": 25},
    ).json()
    task = test_client.post(
        "/api/daily-tasks",
        json={
            "learning_goal_id": goal["id"],
            "course_id": course["id"],
            "knowledge_point_id": point["id"],
            "title": "学习 Client 与 Server",
            "estimated_minutes": 25,
            "scheduled_date": business_date.isoformat(),
        },
    )
    assert task.status_code == 201
    task_id = task.json()["id"]
    assert test_client.get("/api/today").json()["pending_count"] == 1

    session = test_client.post(
        "/api/learning-sessions",
        json={
            "learning_goal_id": goal["id"],
            "course_id": course["id"],
            "knowledge_point_id": point["id"],
            "daily_task_id": task_id,
        },
    )
    assert session.status_code == 201
    session_id = session.json()["id"]
    duplicate = test_client.post(
        "/api/learning-sessions",
        json={
            "learning_goal_id": goal["id"],
            "course_id": course["id"],
            "knowledge_point_id": point["id"],
            "daily_task_id": task_id,
        },
    )
    assert duplicate.json()["id"] == session_id

    paused = test_client.patch(
        f"/api/learning-sessions/{session_id}",
        json={"status": "paused", "notes": "理解了请求方向"},
    )
    assert paused.json()["status"] == "paused"
    completed = test_client.patch(
        f"/api/learning-sessions/{session_id}",
        json={
            "status": "completed",
            "knowledge_point_status": "completed",
            "daily_task_status": "completed",
        },
    )
    assert completed.status_code == 200
    assert completed.json()["ended_at"] is not None
    today = test_client.get("/api/today").json()
    assert today["tasks"][0]["status"] == "completed"
    progress = test_client.get("/api/progress").json()
    assert progress["completed_knowledge_point_count"] == 1
    assert progress["sessions_last_7_days"] == 1


def test_missing_records(client):
    test_client, _ = client
    assert test_client.get("/api/courses/999").status_code == 404
    assert test_client.get("/api/learning-sessions/999").status_code == 404
