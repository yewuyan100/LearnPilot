from datetime import timedelta
from hashlib import sha256

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.clock import clock_from_settings
from app.models import (
    ActivityQuestion, Course, DailyTask, KnowledgePoint, LearningActivity,
    LearningGoal, LearningSession, QuizAnswer, QuizAttempt, WrongAnswer,
)
from app.services.adaptive_learning.lifecycle import refresh_adaptive_learning

DEMO_POINTS = ["掌握度证据", "置信度", "复习调度"]


def seed_demo(db: Session) -> LearningGoal:
    existing = db.scalar(select(LearningGoal).where(LearningGoal.is_demo.is_(True)))
    if existing:
        return existing
    settings = get_settings()
    clock = clock_from_settings(settings)
    now = clock.now()
    today = clock.today()
    goal = LearningGoal(
        title="[DEMO] LearnPilot 自适应闭环",
        description="仅用于演示 V1–V6，不包含任何个人资料。",
        target_date=today + timedelta(days=21), daily_minutes=40,
        current_level="工程演示", status="active", is_demo=True,
    )
    db.add(goal); db.flush()
    course = Course(
        learning_goal_id=goal.id, title="[DEMO] 透明掌握度",
        description="演示证据、快照、薄弱点和受控复习任务。", status="active",
    )
    db.add(course); db.flush()
    points = []
    for index, title in enumerate(DEMO_POINTS):
        point = KnowledgePoint(
            course_id=course.id, title=title, description=f"[DEMO] {title} 演示知识点",
            order_index=index, estimated_minutes=20,
            status="learning" if index == 0 else "not_started",
        )
        db.add(point); points.append(point)
    db.flush()
    db.add(DailyTask(
        learning_goal_id=goal.id, course_id=course.id, knowledge_point_id=points[0].id,
        title="[DEMO] 复习掌握度证据", task_type="learning", estimated_minutes=20,
        scheduled_date=today, status="completed",
    ))
    db.add(LearningSession(
        learning_goal_id=goal.id, course_id=course.id, knowledge_point_id=points[0].id,
        daily_task_id=None, started_at=now - timedelta(minutes=30), ended_at=now,
        status="completed", notes="[DEMO] 完成规则算法学习。",
    ))
    activity = LearningActivity(
        title="[DEMO] 掌握度小测", description="人工构造的演示活动。",
        activity_type="quiz", status="published", course_id=course.id,
        knowledge_point_id=points[0].id, source_scope={"kind": "demo"},
        question_count=1, total_points=2, generation_request_id="demo-v6-activity",
        generation_config_hash=sha256(b"demo-v6-activity").hexdigest(),
        prompt_version="demo-fixture-v1", model_name=None, validation_warnings=[], published_at=now,
    )
    db.add(activity); db.flush()
    question = ActivityQuestion(
        activity_id=activity.id, question_index=1, question_type="single_choice",
        stem="[DEMO] 掌握度是否由真实证据确定性计算？",
        options_json=[{"id": "A", "text": "是"}, {"id": "B", "text": "否"}],
        correct_answer_json=["A"], reference_answer=None, grading_rubric_json=None,
        explanation="V6 不允许 LLM 直接计算掌握度。", difficulty="easy", points=2,
        status="active", content_hash=sha256(b"demo-v6-question").hexdigest(),
    )
    db.add(question); db.flush()
    attempt = QuizAttempt(
        activity_id=activity.id, request_id="demo-v6-attempt", submission_hash=sha256(b"demo-v6-submit").hexdigest(),
        status="completed", started_at=now - timedelta(minutes=10), submitted_at=now,
        graded_at=now, total_points=2, earned_points=0, score_percentage=0,
        correct_count=0, incorrect_count=1, partial_count=0,
    )
    db.add(attempt); db.flush()
    answer = QuizAnswer(
        attempt_id=attempt.id, question_id=question.id, answer_json=["B"], answer_text=None,
        is_correct=False, grading_status="completed", earned_points=0, max_points=2,
        feedback="[DEMO] 请复习确定性证据规则。", matched_rubric_items_json=None,
        missing_rubric_items_json=None,
    )
    db.add(answer); db.flush()
    db.add(WrongAnswer(
        question_id=question.id, attempt_id=attempt.id, answer_id=answer.id,
        course_id=course.id, knowledge_point_id=points[0].id,
        status="active", error_type="incorrect", review_count=0,
    ))
    db.commit()
    refresh_adaptive_learning(
        db, settings, points[0].id,
        trigger_type="quiz_completed", trigger_source_id=attempt.id,
    )
    db.refresh(goal)
    return goal


def clear_demo(db: Session) -> int:
    goals = list(db.scalars(select(LearningGoal).where(LearningGoal.is_demo.is_(True))))
    if not goals:
        return 0
    goal_ids = [goal.id for goal in goals]
    course_ids = list(db.scalars(select(Course.id).where(Course.learning_goal_id.in_(goal_ids))))
    if course_ids:
        activity_ids = list(db.scalars(select(LearningActivity.id).where(LearningActivity.course_id.in_(course_ids))))
        db.execute(delete(WrongAnswer).where(WrongAnswer.course_id.in_(course_ids)))
        if activity_ids:
            db.execute(delete(QuizAttempt).where(QuizAttempt.activity_id.in_(activity_ids)))
            db.execute(delete(LearningActivity).where(LearningActivity.id.in_(activity_ids)))
    db.execute(delete(LearningGoal).where(LearningGoal.id.in_(goal_ids)))
    db.commit()
    return len(goal_ids)
