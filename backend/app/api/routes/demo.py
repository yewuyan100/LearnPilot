from fastapi import APIRouter, status

from app.api.deps import DbSession
from app.schemas.learning_goal import LearningGoalRead
from app.services.demo import clear_demo, seed_demo

router = APIRouter(prefix="/demo-data", tags=["demo data"])


@router.post("", response_model=LearningGoalRead, status_code=status.HTTP_201_CREATED)
def create_demo_data(db: DbSession):
    return seed_demo(db)


@router.delete("")
def delete_demo_data(db: DbSession) -> dict:
    return {"deleted_goals": clear_demo(db)}

