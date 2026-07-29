def test_health(client):
    test_client, _ = client
    response = test_client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_goal_crud_and_persistence(client, goal_payload):
    test_client, _ = client
    created = test_client.post("/api/learning-goals", json=goal_payload)
    assert created.status_code == 201
    goal_id = created.json()["id"]

    updated = test_client.patch(
        f"/api/learning-goals/{goal_id}",
        json={"daily_minutes": 50, "status": "paused"},
    )
    assert updated.status_code == 200
    assert updated.json()["daily_minutes"] == 50

    listed = test_client.get("/api/learning-goals")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == goal_id

    deleted = test_client.delete(f"/api/learning-goals/{goal_id}")
    assert deleted.status_code == 204
    assert test_client.get(f"/api/learning-goals/{goal_id}").status_code == 404


def test_goal_validation(client):
    test_client, _ = client
    response = test_client.post(
        "/api/learning-goals",
        json={"title": "", "daily_minutes": 1},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"

