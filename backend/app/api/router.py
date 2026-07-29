from fastapi import APIRouter

from app.api.routes import (
    courses,
    daily_tasks,
    dashboard,
    demo,
    health,
    learning_goals,
    learning_sessions,
    learning_activities,
    materials,
    quiz_attempts,
    rag,
    wrong_answers,
)

api_router = APIRouter()
for router in (
    health.router,
    learning_goals.router,
    materials.router,
    courses.router,
    daily_tasks.router,
    learning_sessions.router,
    learning_activities.router,
    dashboard.router,
    demo.router,
    rag.router,
    quiz_attempts.router,
    wrong_answers.router,
):
    api_router.include_router(router)
