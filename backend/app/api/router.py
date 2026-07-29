from fastapi import APIRouter

from app.api.routes import (
    courses,
    daily_tasks,
    dashboard,
    demo,
    health,
    learning_goals,
    learning_sessions,
    materials,
)

api_router = APIRouter()
for router in (
    health.router,
    learning_goals.router,
    materials.router,
    courses.router,
    daily_tasks.router,
    learning_sessions.router,
    dashboard.router,
    demo.router,
):
    api_router.include_router(router)
