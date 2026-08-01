import json
from datetime import date, datetime, timezone
from hashlib import sha256
from time import perf_counter
from typing import Any, Callable
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from sqlalchemy import func, select

from app.core.errors import AppError
from app.models import (
    Course, DailyTask, KnowledgePoint, LearningActivity, LearningGoal,
    LearningSession, QuizAttempt, WrongAnswer,
)
from app.schemas.daily_task import DailyTaskCreate, DailyTaskUpdate
from app.schemas.learning_activity import ActivityGenerateRequest
from app.services.crud import apply_updates, get_or_404
from app.services.learning_activities.service import ActivityGenerationService
from app.services.llm.schemas import RagModelAnswer
from app.services.quiz_attempts import QuizAttemptService
from app.services.rag.prompts import REPAIR_SYSTEM_PROMPT, answer_messages
from app.services.llm.errors import LLMOutputInvalidError
from app.services.rag.retrieval import retrieve_sources
from app.services.rag.validation import is_prompt_injection_request, validate_answer
from app.services.vector_store.service import MaterialIndexService
from app.services.wrong_answers import WrongAnswerService


READ_TOOLS = (
    "answer_from_materials", "search_materials", "list_courses", "list_knowledge_points",
    "list_daily_tasks", "get_learning_progress", "list_learning_activities",
    "get_activity_summary", "list_quiz_attempts", "get_wrong_answers",
)
WRITE_TOOLS = (
    "create_daily_task", "update_daily_task_status", "save_learning_note",
    "generate_learning_activity", "create_wrong_answer_review", "start_quiz_attempt",
)
FORBIDDEN_TOKENS = (
    "delete", "drop ", "truncate", "shell", "powershell", "cmd.exe", "python",
    "sql", "filesystem", "file_path", "api_key", "environment", "score_percentage",
    "correct_answer", "grading_rubric", "reference_answer",
)
REQUIRED_ARGS = {
    "answer_from_materials": {"question"}, "search_materials": {"query"},
    "get_activity_summary": {"activity_id"}, "create_daily_task": {"learning_goal_id", "title", "scheduled_date"},
    "update_daily_task_status": {"task_id", "status"}, "save_learning_note": {"learning_goal_id", "note"},
    "generate_learning_activity": {"title", "material_ids", "question_types", "question_count", "difficulty"},
    "create_wrong_answer_review": {"wrong_answer_ids"}, "start_quiz_attempt": {"activity_id"},
}


def stable_hash(value: Any) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def result(tool: str, data: Any = None, summary: str = "", *, ids: dict | None = None,
           citations: list | None = None, error_code: str | None = None, retryable: bool = False) -> dict:
    return {
        "success": error_code is None, "tool": tool, "data": data,
        "user_summary": summary, "resource_ids": ids or {}, "citations": citations or [],
        "error_code": error_code, "retryable": retryable,
    }


class ToolRegistry:
    def __init__(self, db, settings, embedder, provider):
        self.db, self.settings, self.embedder, self.provider = db, settings, embedder, provider

    @property
    def read_names(self) -> list[str]:
        return list(READ_TOOLS)

    @property
    def write_names(self) -> list[str]:
        return list(WRITE_TOOLS)

    def validate_plan(self, steps: list[dict]) -> list[dict]:
        if len(steps) > self.settings.agent_max_steps:
            raise ValueError("plan_too_many_steps")
        reads = writes = 0
        normalized = []
        write_seen = False
        for raw in steps:
            name = str(raw.get("tool_name", ""))
            args = raw.get("arguments") or {}
            if name not in READ_TOOLS + WRITE_TOOLS or not isinstance(args, dict):
                raise ValueError("tool_not_allowed")
            if not REQUIRED_ARGS.get(name, set()).issubset(args):
                raise ValueError("tool_arguments_invalid")
            unsafe = json.dumps({"name": name, "arguments": args}, ensure_ascii=False).lower()
            if any(token in unsafe for token in FORBIDDEN_TOKENS):
                raise ValueError("unsafe_tool_arguments")
            if name in WRITE_TOOLS:
                writes += 1
                write_seen = True
            else:
                reads += 1
                if write_seen:
                    raise ValueError("read_after_write")
            normalized.append({"tool_name": name, "arguments": args, "kind": "write" if name in WRITE_TOOLS else "read"})
        if reads > self.settings.agent_max_read_tools or writes > 1:
            raise ValueError("tool_limit_exceeded")
        return normalized

    def execute(self, name: str, args: dict, *, run_id: int, request_id: str) -> dict:
        handler: Callable = getattr(self, f"_tool_{name}")
        try:
            return handler(args, run_id=run_id, request_id=request_id)
        except (ValidationError, ValueError) as exc:
            return result(name, summary="工具参数不完整或无效。", error_code="tool_arguments_invalid")
        except AppError as exc:
            return result(name, summary=exc.message, error_code=exc.code, retryable=exc.status_code >= 500)
        except Exception:
            self.db.rollback()
            return result(name, summary="工具执行失败，请稍后重试。", error_code="tool_execution_failed", retryable=True)

    def _tool_search_materials(self, a, **_):
        response = MaterialIndexService(self.db, self.settings, self.embedder).search(
            query=str(a["query"]), top_k=min(int(a.get("top_k", 5)), self.settings.search_top_k_max),
            material_ids=a.get("material_ids"), min_score=a.get("min_score"))
        return result("search_materials", response.model_dump(mode="json"), f"找到 {len(response.results)} 个资料片段。")

    def _tool_answer_from_materials(self, a, **_):
        question = str(a.get("question") or a.get("query") or "").strip()
        if is_prompt_injection_request(question):
            return result("answer_from_materials", summary="不能泄露或绕过内部提示与安全规则。", error_code="security_rejection")
        retrieval = retrieve_sources(db=self.db, settings=self.settings, embedder=self.embedder,
            query=question, top_k=min(int(a.get("top_k", self.settings.rag_top_k_default)), self.settings.rag_top_k_max),
            material_ids=a.get("material_ids"))
        if not retrieval.sources:
            return result("answer_from_materials", {"answer":"当前资料不足以可靠回答。"}, "当前资料不足以可靠回答。")
        if self.provider is None:
            return result("answer_from_materials", summary="LLM 尚未配置。", error_code="llm_not_configured")
        reason = "llm_output_invalid"
        try:
            answer = self.provider.generate_structured(messages=answer_messages(question, retrieval.sources), schema=RagModelAnswer).value
            valid, reason = validate_answer(answer, retrieval.sources)
        except LLMOutputInvalidError:
            valid = False
            answer = None
        if not valid:
            allowed = ", ".join(source.source_label for source in retrieval.sources)
            repaired = self.provider.generate_structured(messages=[
                {"role":"system","content":REPAIR_SYSTEM_PROMPT},
                {"role":"user","content":f"问题：{question}\n校验失败原因：{reason}\n允许来源：{allowed}\n请重新依据资料生成合规答案。"},
                *answer_messages(question,retrieval.sources)[1:2],
            ],schema=RagModelAnswer)
            answer = repaired.value
            valid, reason = validate_answer(answer,retrieval.sources)
        if not valid:
            return result("answer_from_materials", summary="资料回答的引用校验失败。", error_code=reason or "citation_invalid")
        citations = [{
            "source_label": s.source_label, "material_id": s.material_id, "chunk_id": s.chunk_id,
            "original_filename": s.original_filename, "page_number": s.page_number,
            "section_title": s.section_title, "content_excerpt": s.content[:self.settings.rag_citation_excerpt_chars],
        } for s in retrieval.sources if s.source_label in answer.cited_source_ids]
        return result("answer_from_materials", {"answer": answer.answer_markdown}, answer.answer_markdown, citations=citations)

    def _tool_list_courses(self, a, **_):
        rows = self.db.scalars(select(Course).order_by(Course.updated_at.desc()).limit(int(a.get("limit", 50)))).all()
        data = [{"id": x.id, "title": x.title, "status": x.status, "description": x.description} for x in rows]
        return result("list_courses", data, f"共有 {len(data)} 门课程。")

    def _tool_list_knowledge_points(self, a, **_):
        stmt = select(KnowledgePoint).order_by(KnowledgePoint.course_id, KnowledgePoint.order_index)
        if a.get("course_id"): stmt = stmt.where(KnowledgePoint.course_id == int(a["course_id"]))
        rows = self.db.scalars(stmt.limit(100)).all()
        data = [{"id": x.id, "course_id": x.course_id, "title": x.title, "status": x.status} for x in rows]
        return result("list_knowledge_points", data, f"共有 {len(data)} 个知识点。")

    def _tool_list_daily_tasks(self, a, **_):
        target = date.fromisoformat(a["scheduled_date"]) if a.get("scheduled_date") else datetime.now(ZoneInfo(self.settings.app_timezone)).date()
        stmt = select(DailyTask).where(DailyTask.scheduled_date == target).order_by(DailyTask.id)
        rows = self.db.scalars(stmt).all()
        data = [{"id": x.id, "title": x.title, "status": x.status, "scheduled_date": x.scheduled_date.isoformat(), "estimated_minutes": x.estimated_minutes} for x in rows]
        return result("list_daily_tasks", data, f"{target.isoformat()} 有 {len(data)} 个任务。")

    def _tool_get_learning_progress(self, a, **_):
        total = self.db.scalar(select(func.count()).select_from(KnowledgePoint)) or 0
        done = self.db.scalar(select(func.count()).select_from(KnowledgePoint).where(KnowledgePoint.status == "completed")) or 0
        sessions = self.db.scalar(select(func.count()).select_from(LearningSession)) or 0
        data = {"knowledge_point_count": total, "completed_knowledge_point_count": done, "session_count": sessions}
        return result("get_learning_progress", data, f"已完成 {done}/{total} 个知识点，累计 {sessions} 次学习记录。")

    def _tool_list_learning_activities(self, a, **_):
        stmt = select(LearningActivity).order_by(LearningActivity.created_at.desc()).limit(50)
        if a.get("status"): stmt = stmt.where(LearningActivity.status == a["status"])
        rows = self.db.scalars(stmt).all()
        data = [{"id": x.id, "title": x.title, "status": x.status, "question_count": x.question_count, "total_points": x.total_points} for x in rows]
        return result("list_learning_activities", data, f"共有 {len(data)} 个学习活动。")

    def _tool_get_activity_summary(self, a, **_):
        x = get_or_404(self.db, LearningActivity, int(a["activity_id"]), "学习活动")
        data = {"id": x.id, "title": x.title, "status": x.status, "description": x.description, "question_count": x.question_count, "total_points": x.total_points}
        return result("get_activity_summary", data, f"{x.title}：{x.question_count} 题，状态为 {x.status}。")

    def _tool_list_quiz_attempts(self, a, **_):
        stmt = select(QuizAttempt).order_by(QuizAttempt.created_at.desc()).limit(int(a.get("limit", 20)))
        if a.get("activity_id"): stmt = stmt.where(QuizAttempt.activity_id == int(a["activity_id"]))
        rows = self.db.scalars(stmt).all()
        data = [{"id": x.id, "activity_id": x.activity_id, "status": x.status, "started_at": x.started_at.isoformat(), "score_percentage": x.score_percentage} for x in rows]
        return result("list_quiz_attempts", data, f"找到 {len(data)} 次测验记录。")

    def _tool_get_wrong_answers(self, a, **_):
        page = WrongAnswerService(self.db, self.settings).list(page=1, page_size=min(int(a.get("limit", 20)), 100),
            status_filter=a.get("status", "active"), course_id=a.get("course_id"), knowledge_point_id=a.get("knowledge_point_id"), question_type=a.get("question_type"))
        data = [x.model_dump(mode="json") for x in page.items]
        return result("get_wrong_answers", data, f"找到 {len(data)} 道错题。")

    def _tool_create_daily_task(self, a, **_):
        payload = DailyTaskCreate.model_validate(a)
        get_or_404(self.db, LearningGoal, payload.learning_goal_id, "学习目标")
        if payload.course_id: get_or_404(self.db, Course, payload.course_id, "课程")
        if payload.knowledge_point_id: get_or_404(self.db, KnowledgePoint, payload.knowledge_point_id, "知识点")
        task = DailyTask(**payload.model_dump())
        self.db.add(task); self.db.commit(); self.db.refresh(task)
        return result("create_daily_task", {"id": task.id, "title": task.title}, f"已创建任务“{task.title}”。", ids={"daily_task_id": task.id})

    def _tool_update_daily_task_status(self, a, **_):
        task = get_or_404(self.db, DailyTask, int(a["task_id"]), "每日任务")
        status = str(a["status"])
        if status not in {"pending", "in_progress", "completed", "skipped"}: raise ValueError("invalid_status")
        apply_updates(task, DailyTaskUpdate(status=status).model_dump(exclude_unset=True)); self.db.commit(); self.db.refresh(task)
        return result("update_daily_task_status", {"id": task.id, "status": task.status}, f"任务状态已更新为 {task.status}。", ids={"daily_task_id": task.id})

    def _tool_save_learning_note(self, a, **_):
        goal = get_or_404(self.db, LearningGoal, int(a["learning_goal_id"]), "学习目标")
        now = datetime.now(timezone.utc)
        session = LearningSession(learning_goal_id=goal.id, course_id=a.get("course_id"), knowledge_point_id=a.get("knowledge_point_id"),
            started_at=now, ended_at=now, status="completed", notes=str(a["note"]).strip())
        self.db.add(session); self.db.commit(); self.db.refresh(session)
        return result("save_learning_note", {"id": session.id}, "学习笔记已保存。", ids={"learning_session_id": session.id})

    def _tool_generate_learning_activity(self, a, *, request_id, **_):
        values = dict(a); values["request_id"] = values.get("request_id") or f"agent-{request_id}"
        detail = ActivityGenerationService(self.db, self.settings, self.embedder, self.provider).generate(ActivityGenerateRequest.model_validate(values))
        if detail.status != "draft": raise ValueError("activity_must_be_draft")
        return result("generate_learning_activity", {"id": detail.id, "title": detail.title, "status": detail.status, "question_count": detail.question_count},
            f"已生成草稿活动“{detail.title}”，请在发布前检查题目。", ids={"activity_id": detail.id})

    def _tool_create_wrong_answer_review(self, a, *, request_id, **_):
        rid = str(a.get("request_id") or f"agent-{request_id}")
        attempt = WrongAnswerService(self.db, self.settings).create_review_attempt(wrong_answer_ids=[int(x) for x in a["wrong_answer_ids"]], request_id=rid)
        return result("create_wrong_answer_review", {"attempt_id": attempt.id, "activity_id": attempt.activity_id, "status": attempt.status},
            "已创建错题复习测验。", ids={"attempt_id": attempt.id, "activity_id": attempt.activity_id})

    def _tool_start_quiz_attempt(self, a, *, request_id, **_):
        marker = f"agent-{request_id}"[:64]
        existing = self.db.scalar(select(QuizAttempt).where(QuizAttempt.request_id == marker))
        if existing:
            attempt = QuizAttemptService(self.db, self.settings, self.provider).serialize(existing)
        else:
            attempt = QuizAttemptService(self.db, self.settings, self.provider).start(int(a["activity_id"]), a.get("learning_session_id"))
            row = get_or_404(self.db, QuizAttempt, attempt.id, "测验"); row.request_id = marker; self.db.commit()
        safe = {"id": attempt.id, "activity_id": attempt.activity_id, "status": attempt.status, "question_count": len(attempt.questions)}
        return result("start_quiz_attempt", safe, "测验已开始；答案与评分标准不会提前显示。", ids={"attempt_id": attempt.id})


def confirmation_summary(tool_name: str, args: dict) -> str:
    labels = {
        "create_daily_task": "创建每日任务", "update_daily_task_status": "更新任务状态",
        "save_learning_note": "保存学习笔记", "generate_learning_activity": "生成测验草稿",
        "create_wrong_answer_review": "创建错题复习", "start_quiz_attempt": "开始测验",
    }
    safe_args = {k: v for k, v in args.items() if k not in {"correct_answer", "reference_answer", "grading_rubric"}}
    return f"将执行：{labels.get(tool_name, tool_name)}。参数：{json.dumps(safe_args, ensure_ascii=False, default=str)}"
