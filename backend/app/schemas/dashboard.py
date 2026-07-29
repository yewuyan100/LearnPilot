from datetime import date, datetime

from pydantic import BaseModel


class ProgressResponse(BaseModel):
    goal_count: int
    active_course_count: int
    knowledge_point_count: int
    completed_knowledge_point_count: int
    today_task_total: int
    today_task_completed: int
    sessions_last_7_days: int
    daily_sessions: list[dict]
    recent_sessions: list[dict]


class ReviewResponse(BaseModel):
    knowledge_points: list[dict]
    unfinished_tasks: list[dict]


class MetaResponse(BaseModel):
    backend_status: str
    database_type: str
    upload_directory: str
    allowed_file_types: list[str]
    max_file_size_mb: int
    app_version: str
    demo_data_enabled: bool
    server_date: date
    server_time: datetime

