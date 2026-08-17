def _create_goal(test_client, title: str, status: str):
    response = test_client.post(
        "/api/learning-goals",
        json={
            "title": title,
            "description": "Goal context integrity fixture",
            "target_date": "2026-08-31",
            "daily_minutes": 30,
            "current_level": "baseline",
            "status": status,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_today_recent_session_ownership_comes_from_session_not_current_goal(client):
    test_client, _ = client
    goal_b = _create_goal(test_client, "Goal B", "paused")
    goal_a = _create_goal(test_client, "Goal A", "active")

    session_response = test_client.post(
        "/api/learning-sessions",
        json={
            "learning_goal_id": goal_b["id"],
            "notes": "Goal B recent session content",
        },
    )
    assert session_response.status_code == 201
    session_b = session_response.json()

    response = test_client.get("/api/today")
    assert response.status_code == 200
    today = response.json()

    assert today["current_goal"]["id"] == goal_a["id"]
    assert today["recent_session"]["id"] == session_b["id"]
    assert today["recent_session"]["learning_goal_id"] == goal_b["id"]
    assert today["recent_session"]["learning_goal_id"] != today["current_goal"]["id"]
