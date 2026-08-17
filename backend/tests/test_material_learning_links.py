def create_structure(http, goal_payload, suffix="A"):
    goal_data = {**goal_payload, "title": f"Goal {suffix}"}
    goal = http.post("/api/learning-goals", json=goal_data).json()
    course = http.post(
        "/api/courses",
        json={"learning_goal_id": goal["id"], "title": f"Course {suffix}", "status": "active"},
    ).json()
    point = http.post(
        f"/api/courses/{course['id']}/knowledge-points",
        json={"title": f"Point {suffix}", "order_index": 1, "estimated_minutes": 20},
    ).json()
    return goal, course, point


def upload_material(http, name="scope.md"):
    response = http.post(
        "/api/materials/upload",
        files={"file": (name, b"# Scoped source\nDeterministic learning material.", "text/markdown")},
    )
    assert response.status_code == 201
    return response.json()


def link_payload(target_type, target_id, relation_type="reference"):
    field = {
        "learning_goal": "learning_goal_id",
        "course": "course_id",
        "knowledge_point": "knowledge_point_id",
    }[target_type]
    return {
        "target_type": target_type,
        field: target_id,
        "relation_type": relation_type,
        "is_primary": relation_type == "primary_source",
    }


def archive_point(http, point, reason="测试归档知识点"):
    change = {"action": "archive", "lifecycle_reason": reason}
    impact_response = http.post(
        f"/api/knowledge-points/{point['id']}/impact", json=change
    )
    assert impact_response.status_code == 200
    response = http.post(
        f"/api/knowledge-points/{point['id']}/archive",
        json={
            **change,
            "request_id": f"archive-material-point-{point['id']}",
            "expected_version": point["version"],
            "impact_hash": impact_response.json()["impact_hash"],
            "confirmed": True,
        },
    )
    assert response.status_code == 200
    return response.json()


def test_material_links_all_learning_levels_and_are_idempotent(client, goal_payload):
    http, _ = client
    goal, course, point = create_structure(http, goal_payload)
    material = upload_material(http)

    created = []
    for target_type, target_id in (
        ("learning_goal", goal["id"]),
        ("course", course["id"]),
        ("knowledge_point", point["id"]),
    ):
        response = http.post(
            f"/api/materials/{material['id']}/learning-links",
            json=link_payload(target_type, target_id),
        )
        assert response.status_code == 201
        created.append(response.json())

    duplicate = http.post(
        f"/api/materials/{material['id']}/learning-links",
        json=link_payload("course", course["id"]),
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == created[1]["id"]

    listed = http.get(f"/api/materials/{material['id']}/learning-links").json()
    assert len(listed) == 3
    assert {item["target_title"] for item in listed} == {"Goal A", "Course A", "Point A"}


def test_invalid_target_and_cross_goal_hierarchy_are_rejected(client, goal_payload):
    http, _ = client
    _, course_a, _ = create_structure(http, goal_payload, "A")
    _, course_b, _ = create_structure(http, goal_payload, "B")
    material = upload_material(http)

    missing = http.post(
        f"/api/materials/{material['id']}/learning-links",
        json=link_payload("course", 99999),
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "material_learning_target_not_found"

    first = http.post(
        f"/api/materials/{material['id']}/learning-links",
        json=link_payload("course", course_a["id"]),
    )
    assert first.status_code == 201
    conflict = http.post(
        f"/api/materials/{material['id']}/learning-links",
        json=link_payload("course", course_b["id"]),
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "material_learning_hierarchy_conflict"


def test_cross_course_knowledge_point_conflict_is_rejected(client, goal_payload):
    http, _ = client
    goal, course_a, _ = create_structure(http, goal_payload, "A")
    course_b = http.post(
        "/api/courses",
        json={"learning_goal_id": goal["id"], "title": "Course B", "status": "active"},
    ).json()
    point_b = http.post(
        f"/api/courses/{course_b['id']}/knowledge-points",
        json={"title": "Point B", "order_index": 1, "estimated_minutes": 20},
    ).json()
    material = upload_material(http)
    assert http.post(
        f"/api/materials/{material['id']}/learning-links",
        json=link_payload("course", course_a["id"]),
    ).status_code == 201
    conflict = http.post(
        f"/api/materials/{material['id']}/learning-links",
        json=link_payload("knowledge_point", point_b["id"]),
    )
    assert conflict.status_code == 409


def test_bulk_linking_is_atomic_and_conflicting_duplicate_is_rejected(client, goal_payload):
    http, _ = client
    goal, course, _ = create_structure(http, goal_payload)
    material = upload_material(http)
    success = http.post(
        f"/api/materials/{material['id']}/learning-links/bulk",
        json={"links": [
            link_payload("learning_goal", goal["id"]),
            link_payload("course", course["id"], "primary_source"),
        ]},
    )
    assert success.status_code == 201
    assert len(success.json()) == 2

    other = upload_material(http, "other.md")
    failed = http.post(
        f"/api/materials/{other['id']}/learning-links/bulk",
        json={"links": [
            link_payload("learning_goal", goal["id"]),
            link_payload("course", 99999),
        ]},
    )
    assert failed.status_code == 404
    assert http.get(f"/api/materials/{other['id']}/learning-links").json() == []

    duplicate_conflict = http.post(
        f"/api/materials/{other['id']}/learning-links/bulk",
        json={"links": [
            link_payload("course", course["id"], "reference"),
            link_payload("course", course["id"], "supplementary"),
        ]},
    )
    assert duplicate_conflict.status_code == 422


def test_effective_scope_distinguishes_direct_inherited_and_descendant(client, goal_payload):
    http, _ = client
    goal, course, point = create_structure(http, goal_payload)
    goal_material = upload_material(http, "goal.md")
    course_material = upload_material(http, "course.md")
    point_material = upload_material(http, "point.md")
    for material, target_type, target_id in (
        (goal_material, "learning_goal", goal["id"]),
        (course_material, "course", course["id"]),
        (point_material, "knowledge_point", point["id"]),
    ):
        assert http.post(
            f"/api/materials/{material['id']}/learning-links",
            json=link_payload(target_type, target_id),
        ).status_code == 201

    goal_scope = http.get(f"/api/learning-goals/{goal['id']}/materials").json()
    goal_visibility = {
        item["material_id"]: item["contexts"][0]["visibility"] for item in goal_scope
    }
    assert goal_visibility == {
        goal_material["id"]: "direct",
        course_material["id"]: "descendant",
        point_material["id"]: "descendant",
    }

    course_scope = http.get(f"/api/courses/{course['id']}/materials").json()
    course_visibility = {
        item["material_id"]: item["contexts"][0]["visibility"] for item in course_scope
    }
    assert course_visibility == {
        goal_material["id"]: "inherited",
        course_material["id"]: "direct",
        point_material["id"]: "descendant",
    }

    point_scope = http.get(f"/api/knowledge-points/{point['id']}/materials").json()
    point_visibility = {
        item["material_id"]: item["contexts"][0]["visibility"] for item in point_scope
    }
    assert point_visibility == {
        goal_material["id"]: "inherited",
        course_material["id"]: "inherited",
        point_material["id"]: "direct",
    }


def test_unlink_and_target_archive_never_delete_material(client, goal_payload):
    http, _ = client
    _, course, point = create_structure(http, goal_payload)
    material = upload_material(http)
    link = http.post(
        f"/api/materials/{material['id']}/learning-links",
        json=link_payload("course", course["id"]),
    ).json()
    assert http.delete(
        f"/api/materials/{material['id']}/learning-links/{link['id']}"
    ).status_code == 204
    assert http.get(f"/api/materials/{material['id']}").status_code == 200

    point_link = http.post(
        f"/api/materials/{material['id']}/learning-links",
        json=link_payload("knowledge_point", point["id"]),
    )
    assert point_link.status_code == 201
    archive_point(http, point)
    assert http.get(f"/api/materials/{material['id']}").status_code == 200
    retained_links = http.get(f"/api/materials/{material['id']}/learning-links").json()
    assert len(retained_links) == 1
    assert retained_links[0]["target_type"] == "knowledge_point"


def test_course_with_knowledge_points_cannot_cascade_delete_material_link(client, goal_payload):
    http, _ = client
    _, course, _ = create_structure(http, goal_payload)
    material = upload_material(http)
    assert http.post(
        f"/api/materials/{material['id']}/learning-links",
        json=link_payload("course", course["id"]),
    ).status_code == 201
    assert http.delete(f"/api/courses/{course['id']}").status_code == 409
    assert http.get(f"/api/materials/{material['id']}").status_code == 200
    assert len(http.get(f"/api/materials/{material['id']}/learning-links").json()) == 1


def test_cross_material_batch_reports_partial_failure_without_hiding_it(client, goal_payload):
    http, _ = client
    _, course_a, _ = create_structure(http, goal_payload, "A")
    _, course_b, _ = create_structure(http, goal_payload, "B")
    material_a = upload_material(http, "a.md")
    material_b = upload_material(http, "b.md")
    assert http.post(
        f"/api/materials/{material_a['id']}/learning-links",
        json=link_payload("course", course_a["id"]),
    ).status_code == 201
    response = http.post(
        "/api/material-learning-links/bulk-materials",
        json={
            "material_ids": [material_a["id"], material_b["id"]],
            "link": link_payload("course", course_b["id"]),
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["requested"] == 2
    assert result["succeeded"] == 1
    assert result["failed"] == 1
    failed = next(item for item in result["items"] if not item["success"])
    assert failed["material_id"] == material_a["id"]
    assert failed["error_code"] == "material_learning_hierarchy_conflict"
    contexts = http.get("/api/material-learning-links").json()
    assert {(item["material_id"], item["target_title"]) for item in contexts} == {
        (material_a["id"], "Course A"),
        (material_b["id"], "Course B"),
    }


def test_archived_material_leaves_and_returns_to_effective_scope(client, goal_payload):
    http, _ = client
    _, course, _ = create_structure(http, goal_payload)
    material = upload_material(http)
    assert http.post(
        f"/api/materials/{material['id']}/learning-links",
        json=link_payload("course", course["id"]),
    ).status_code == 201
    assert len(http.get(f"/api/courses/{course['id']}/materials").json()) == 1
    archived = http.post(
        "/api/materials/archive/bulk", json={"material_ids": [material["id"]]}
    )
    assert archived.status_code == 200
    assert archived.json()["archived_ids"] == [material["id"]]
    assert http.get(f"/api/courses/{course['id']}/materials").json() == []
    restored = http.post(f"/api/materials/{material['id']}/unarchive")
    assert restored.status_code == 200
    assert restored.json()["archived_at"] is None
    assert len(http.get(f"/api/courses/{course['id']}/materials").json()) == 1
