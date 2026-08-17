from fastapi import APIRouter, Response, status
from sqlalchemy import select

from app.api.deps import DbSession
from app.models.learning_goal import LearningGoal
from app.schemas.learning_goal import LearningGoalCreate, LearningGoalRead, LearningGoalUpdate
from app.services.crud import apply_updates, commit, get_or_404
from app.services.learning_goals import LearningGoalLifecycle

router = APIRouter(prefix="/learning-goals", tags=["learning goals"])


@router.post("", response_model=LearningGoalRead, status_code=status.HTTP_201_CREATED)
def create_goal(payload: LearningGoalCreate, db: DbSession) -> LearningGoal:
    goal = LearningGoal(**payload.model_dump())
    db.add(goal)
    return commit(db, goal)


@router.get("", response_model=list[LearningGoalRead])
def list_goals(db: DbSession) -> list[LearningGoal]:
    return list(db.scalars(select(LearningGoal).order_by(LearningGoal.created_at.desc())))


@router.get("/{goal_id}", response_model=LearningGoalRead)
def get_goal(goal_id: int, db: DbSession) -> LearningGoal:
    return get_or_404(db, LearningGoal, goal_id, "学习目标")


@router.patch("/{goal_id}", response_model=LearningGoalRead)
def update_goal(goal_id: int, payload: LearningGoalUpdate, db: DbSession) -> LearningGoal:
    goal = get_or_404(db, LearningGoal, goal_id, "学习目标")
    apply_updates(goal, payload.model_dump(exclude_unset=True))
    return commit(db, goal)


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal(goal_id: int, db: DbSession) -> Response:
    LearningGoalLifecycle(db).delete(goal_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
