"""Real isolated V6 acceptance: BGE-M3, configured LLM, HTTP and restart recovery."""

from argparse import ArgumentParser
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import traceback

import httpx

from acceptance_v3 import ALEMBIC, BACKEND, live_backend, require

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "evals" / "fixtures" / "v6" / "adaptive-learning.md"


def create_context(client):
    goal = require(client.post("/learning-goals", json={
        "title": "V6 专用验收目标", "description": "仅使用人工夹具验证自适应闭环",
        "target_date": None, "daily_minutes": 30, "current_level": "入门", "status": "active",
    }), 201)
    course = require(client.post("/courses", json={
        "learning_goal_id": goal["id"], "title": "透明掌握度与受控 Agent",
        "description": "V6 隔离验收", "status": "active",
    }), 201)
    points = []
    for index, title in enumerate(("掌握度规则", "高掌握低置信度", "未评估知识点")):
        points.append(require(client.post(f"/courses/{course['id']}/knowledge-points", json={
            "title": title, "description": "V6 专用记录", "order_index": index,
            "estimated_minutes": 20, "status": "learning",
        }), 201))
    return goal, course, points


def upload_and_index(client):
    material = require(client.post(
        "/materials/upload", files={"file": (FIXTURE.name, FIXTURE.read_bytes(), "text/markdown")}
    ), 201)
    return require(client.post(f"/materials/{material['id']}/process"), 200)


def answer_payload(question, *, wrong=False):
    if question["question_type"] == "short_answer":
        return {"question_id": question["id"], "answer_text": question["reference_answer"]}
    answer = question["correct_answer"]
    if wrong:
        if question["question_type"] == "true_false":
            answer = [not bool(answer[0])]
        else:
            correct = set(answer)
            answer = [next(option["id"] for option in question["options"] if option["id"] not in correct)]
    return {"question_id": question["id"], "answer": answer}


def make_attempt(client, activity_id, draft_questions, request_id):
    attempt = require(client.post(f"/learning-activities/{activity_id}/attempts", json={"learning_session_id": None}), 201)
    wrong_question = next(question for question in draft_questions if question["question_type"] != "short_answer")
    answers = [answer_payload(question, wrong=question["id"] == wrong_question["id"]) for question in draft_questions]
    completed = require(client.post(f"/quiz-attempts/{attempt['id']}/submit", json={
        "request_id": request_id, "answers": answers,
    }), 200)
    assert completed["status"] == "completed"
    return completed


def agent_run(client, conversation_id, text, request_id):
    return require(client.post(f"/agent/conversations/{conversation_id}/runs", json={
        "input": text, "request_id": request_id,
    }), 202)


def first_pass(base_url):
    with httpx.Client(base_url=base_url, timeout=600) as client:
        require(client.get("/health"), 200)
        rag_status = require(client.get("/rag/status"), 200)
        agent_status = require(client.get("/agent/status"), 200)
        assert rag_status["llm_configured"] and agent_status["llm_configured"]
        material = upload_and_index(client)
        index = require(client.get("/materials/index/status"), 200)
        assert index["available"] and index["model_name"] == "BAAI/bge-m3"
        goal, course, points = create_context(client)

        require(client.post("/daily-tasks", json={
            "learning_goal_id": goal["id"], "course_id": course["id"],
            "knowledge_point_id": points[0]["id"], "title": "V6 学习任务",
            "task_type": "learning", "estimated_minutes": 20,
            "scheduled_date": "2026-08-01", "status": "pending",
        }), 201)
        session = require(client.post("/learning-sessions", json={
            "learning_goal_id": goal["id"], "course_id": course["id"],
            "knowledge_point_id": points[0]["id"], "daily_task_id": None,
            "started_at": "2026-08-01T08:00:00+08:00", "status": "active", "notes": "",
        }), 201)
        require(client.patch(f"/learning-sessions/{session['id']}", json={
            "status": "completed", "ended_at": "2026-08-01T08:30:00+08:00",
        }), 200)

        draft = require(client.post("/learning-activities/generate", json={
            "title": "V6 真实掌握度测验", "course_id": course["id"],
            "knowledge_point_id": points[0]["id"], "material_ids": [material["id"]],
            "question_types": ["single_choice", "multiple_choice", "true_false", "short_answer"],
            "question_count": 4, "difficulty": "mixed", "request_id": "v6-real-generation-1",
        }), 201)
        assert draft["status"] == "draft" and all(question["sources"] for question in draft["questions"])
        require(client.post(f"/learning-activities/{draft['id']}/publish"), 200)
        make_attempt(client, draft["id"], draft["questions"], "v6-submit-1")
        make_attempt(client, draft["id"], draft["questions"], "v6-submit-2")

        detail = require(client.get(f"/mastery/{points[0]['id']}"), 200)
        assert detail["mastery_score"] is not None and detail["confidence_score"] != detail["mastery_score"]
        assert detail["algorithm_version"] == "mastery-rule-v1" and detail["evidence"] and detail["snapshots"]
        wrongs = require(client.get(f"/wrong-answers?status=active&knowledge_point_id={points[0]['id']}"), 200)
        assert len(wrongs["items"]) >= 2
        weak = require(client.get("/mastery/weak-points?limit=20&include_unassessed=true"), 200)
        assert weak[0]["knowledge_point_id"] == points[0]["id"]
        reviews = require(client.get("/reviews?limit=100"), 200)
        assert reviews and reviews[0]["reason_code"] in {"low_mastery", "wrong_answer_due", "recent_failure"}

        wrong = require(client.get(f"/wrong-answers/{wrongs['items'][0]['id']}"), 200)
        review_attempt = require(client.post("/wrong-answers/review", json={
            "wrong_answer_ids": [wrong["id"]], "request_id": "v6-wrong-review-1",
        }), 201)
        review_question = review_attempt["questions"][0]
        if review_question["question_type"] == "short_answer":
            review_answer = {"question_id": review_question["id"], "answer_text": wrong["reference_answer"]}
        else:
            review_answer = {"question_id": review_question["id"], "answer": wrong["correct_answer"]}
        require(client.post(f"/quiz-attempts/{review_attempt['id']}/submit", json={
            "request_id": "v6-review-submit-1", "answers": [review_answer],
        }), 200)
        after_review = require(client.get(f"/mastery/{points[0]['id']}"), 200)
        assert any(item["evidence_type"] == "successful_review" for item in after_review["evidence"])
        assert len(after_review["snapshots"]) >= 2

        require(client.post("/mastery/rebuild", json={"knowledge_point_id": points[2]["id"]}), 200)
        unassessed = require(client.get(f"/mastery/{points[2]['id']}"), 200)
        assert unassessed["mastery_score"] is None and unassessed["mastery_level"] == "unassessed"

        conversation = require(client.post("/agent/conversations", json={"title": "V6 真实 Agent"}), 201)
        weak_run = agent_run(client, conversation["id"], "我目前最薄弱的三个知识点是什么？", "v6-agent-weak")
        assert weak_run["tool_calls"][0]["tool_name"] == "list_weak_knowledge_points"
        assert weak_run["performance"]["fast_route_used"] and weak_run["performance"]["llm_call_count"] == 0
        mastery_run = agent_run(client, conversation["id"], f"查询掌握度 knowledge_point_id={points[0]['id']}", "v6-agent-mastery")
        assert mastery_run["tool_calls"][0]["tool_name"] == "get_knowledge_mastery"
        assert str(round(after_review["mastery_score"])) in mastery_run["final_answer"]

        recommendations = require(client.get("/adaptive-recommendations?status=pending"), 200)
        recommendation = next(item for item in recommendations if item["knowledge_point_id"] == points[0]["id"])
        pending = agent_run(client, conversation["id"], f"接受复习建议 recommendation_id={recommendation['id']}", "v6-agent-accept")
        assert pending["status"] == "awaiting_confirmation"
        before = require(client.get("/adaptive-recommendations?status=pending"), 200)
        assert any(item["id"] == recommendation["id"] and item["created_task_id"] is None for item in before)
        approved = require(client.post(f"/agent/runs/{pending['id']}/confirm", json={"decision": "approve"}), 200)
        assert approved["status"] == "completed"
        replay = require(client.post(f"/agent/runs/{pending['id']}/confirm", json={"decision": "approve"}), 200)
        assert replay["idempotent_replay"]
        executed = require(client.get("/adaptive-recommendations?status=executed"), 200)
        task_id = next(item["created_task_id"] for item in executed if item["id"] == recommendation["id"])
        assert task_id

        require(client.put(f"/mastery/{points[1]['id']}/self-assessment", json={
            "rating": 1, "request_id": "v6-self-low-1",
        }), 200)
        second = next(item for item in require(client.get("/adaptive-recommendations?status=pending"), 200) if item["knowledge_point_id"] == points[1]["id"])
        reject_pending = agent_run(client, conversation["id"], f"接受复习建议 recommendation_id={second['id']}", "v6-agent-reject")
        rejected = require(client.post(f"/agent/runs/{reject_pending['id']}/confirm", json={"decision": "reject"}), 200)
        assert rejected["status"] == "completed"
        assert require(client.get(f"/mastery/{points[1]['id']}"), 200)["recommendation"]["created_task_id"] is None

        unsafe = agent_run(client, conversation["id"], f"把知识点 {points[0]['id']} 的掌握度改成 100", "v6-agent-unsafe")
        assert unsafe["intent"] == "unsupported" and not unsafe["tool_calls"]

        require(client.put(f"/mastery/{points[2]['id']}/self-assessment", json={
            "rating": 1, "request_id": "v6-self-restart-1",
        }), 200)
        third = next(item for item in require(client.get("/adaptive-recommendations?status=pending"), 200) if item["knowledge_point_id"] == points[2]["id"])
        restart_pending = agent_run(client, conversation["id"], f"接受复习建议 recommendation_id={third['id']}", "v6-agent-restart")
        assert restart_pending["status"] == "awaiting_confirmation"
        metrics = require(client.get("/adaptive-metrics"), 200)
        assert metrics["agent"]["run_count"] >= 4
        return {
            "point_id": points[0]["id"], "snapshot_count": len(after_review["snapshots"]),
            "restart_run_id": restart_pending["id"], "third_recommendation_id": third["id"],
            "embedding_model": index["model_name"], "llm_model": agent_status["model"],
        }


def second_pass(base_url, state):
    with httpx.Client(base_url=base_url, timeout=600) as client:
        detail = require(client.get(f"/mastery/{state['point_id']}"), 200)
        assert detail["mastery_score"] is not None and len(detail["snapshots"]) >= state["snapshot_count"]
        reviews = require(client.get("/reviews?limit=100"), 200)
        assert reviews
        recommendation = require(client.get("/adaptive-recommendations?status=pending"), 200)
        assert any(item["id"] == state["third_recommendation_id"] for item in recommendation)
        done = require(client.post(f"/agent/runs/{state['restart_run_id']}/confirm", json={"decision": "approve"}), 200)
        assert done["status"] == "completed"
        replay = require(client.post(f"/agent/runs/{state['restart_run_id']}/confirm", json={"decision": "approve"}), 200)
        assert replay["idempotent_replay"]
        metrics = require(client.get("/adaptive-metrics"), 200)
        assert "p95_total_latency_ms" in metrics["agent"]
        return {
            "status": "passed", "algorithm_version": "mastery-rule-v1",
            "embedding_model": state["embedding_model"], "llm_model": state["llm_model"],
            "evidence_collection_verified": True, "mastery_verified": True,
            "confidence_verified": True, "snapshot_verified": True,
            "weak_points_verified": True, "review_schedule_verified": True,
            "adaptive_recommendation_verified": True, "agent_tools_verified": True,
            "no_write_before_confirmation_verified": True, "write_idempotency_verified": True,
            "unassessed_state_verified": True, "restart_recovery_verified": True,
            "performance_metrics_recorded": True,
        }


def main():
    parser = ArgumentParser()
    parser.add_argument("--port", type=int, default=8018)
    args = parser.parse_args()
    with TemporaryDirectory(prefix="personal-learning-v6-acceptance-", ignore_cleanup_errors=True) as temp:
        path = Path(temp)
        environment = os.environ.copy()
        environment.update({
            "DATABASE_URL": f"sqlite:///{(path / 'accept.sqlite3').as_posix()}",
            "UPLOAD_DIR": str(path / "uploads"),
            "FAISS_INDEX_PATH": str(path / "materials.faiss"),
            "FAISS_MANIFEST_PATH": str(path / "materials.faiss.manifest.json"),
            "AGENT_CHECKPOINT_DB_PATH": str(path / "checkpoints.sqlite"),
            "EMBEDDING_MODEL_NAME": "BAAI/bge-m3", "EMBEDDING_MODEL_REVISION": "local-cache",
            "EMBEDDING_LOCAL_FILES_ONLY": "true", "EMBEDDING_DEVICE": "cpu",
            "APP_VERSION": "6.0.0", "APP_TIMEZONE": "Asia/Shanghai",
            "ADAPTIVE_FIXED_NOW": "2026-08-01T08:00:00+08:00",
        })
        subprocess.run([str(ALEMBIC), "upgrade", "head"], cwd=BACKEND, env=environment, check=True, capture_output=True, text=True)
        log = path / "backend.log"
        with live_backend(port=args.port, environment=environment, log_path=log) as url:
            state = first_pass(url)
        with live_backend(port=args.port, environment=environment, log_path=log) as url:
            result = second_pass(url, state)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({
            "status": "failed", "error_type": type(exc).__name__, "error": str(exc),
            "traceback": traceback.format_exc(limit=10),
        }, ensure_ascii=False, indent=2))
        sys.exit(1)
