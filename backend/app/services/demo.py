from datetime import date, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.course import Course
from app.models.daily_task import DailyTask
from app.models.knowledge_point import KnowledgePoint
from app.models.learning_goal import LearningGoal

DEMO_POINTS = [
    "MCP 的定位",
    "Client 与 Server",
    "Tools",
    "Resources",
    "Prompts",
    "Transport",
]


def seed_demo(db: Session) -> LearningGoal:
    existing = db.scalar(select(LearningGoal).where(LearningGoal.is_demo.is_(True)))
    if existing:
        return existing
    goal = LearningGoal(
        title="三周入门 MCP",
        description="理解 MCP 的核心概念并完成一个基础 Server",
        target_date=date.today() + timedelta(days=21),
        daily_minutes=40,
        current_level="了解普通 API",
        status="active",
        is_demo=True,
    )
    db.add(goal)
    db.flush()
    course = Course(
        learning_goal_id=goal.id,
        title="MCP 基础",
        description="从协议定位到 Transport 的手动学习课程。",
        status="active",
    )
    db.add(course)
    db.flush()
    points = []
    for order_index, title in enumerate(DEMO_POINTS, start=1):
        point = KnowledgePoint(
            course_id=course.id,
            title=title,
            description=f"理解 {title} 的基本职责、边界与常见使用方式。",
            order_index=order_index,
            estimated_minutes=20,
            status="learning" if order_index == 1 else "not_started",
        )
        db.add(point)
        points.append(point)
    db.flush()
    db.add(
        DailyTask(
            learning_goal_id=goal.id,
            course_id=course.id,
            knowledge_point_id=points[0].id,
            title="学习 MCP 的定位",
            task_type="learning",
            estimated_minutes=20,
            scheduled_date=date.today(),
            status="pending",
        )
    )
    db.commit()
    db.refresh(goal)
    return goal


def clear_demo(db: Session) -> int:
    ids = list(db.scalars(select(LearningGoal.id).where(LearningGoal.is_demo.is_(True))))
    if not ids:
        return 0
    db.execute(delete(LearningGoal).where(LearningGoal.id.in_(ids)))
    db.commit()
    return len(ids)

