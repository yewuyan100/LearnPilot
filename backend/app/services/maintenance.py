from __future__ import annotations

from sqlalchemy import select

from app.models.maintenance_task import MaintenanceTask


class MaintenanceTaskStore:
    def __init__(self, db, clock):
        self.db = db
        self.clock = clock

    def get_or_create(
        self,
        *,
        task_type: str,
        entity_type: str,
        entity_id: int | str,
        request_key: str,
        payload: dict,
    ) -> MaintenanceTask:
        task = self.db.scalar(
            select(MaintenanceTask).where(MaintenanceTask.request_key == request_key)
        )
        if task is None:
            task = MaintenanceTask(
                task_type=task_type,
                entity_type=entity_type,
                entity_id=str(entity_id),
                request_key=request_key,
                payload=payload,
            )
            self.db.add(task)
            self.db.commit()
            self.db.refresh(task)
        return task

    def start(self, task: MaintenanceTask, stage: str) -> MaintenanceTask:
        task.status = "running"
        task.stage = stage
        task.attempts += 1
        task.error_code = None
        task.error_message = None
        self.db.commit()
        return task

    def fail(
        self,
        task: MaintenanceTask,
        *,
        stage: str,
        error_code: str,
        error_message: str,
    ) -> MaintenanceTask:
        task.status = "failed"
        task.stage = stage
        task.error_code = error_code
        task.error_message = error_message[:2000]
        self.db.commit()
        self.db.refresh(task)
        return task

    def complete(self, task: MaintenanceTask, result: dict | None = None) -> MaintenanceTask:
        task.status = "completed"
        task.stage = "completed"
        task.result = result or {}
        task.error_code = None
        task.error_message = None
        task.completed_at = self.clock.now()
        self.db.commit()
        self.db.refresh(task)
        return task

    @staticmethod
    def serialize(task: MaintenanceTask) -> dict:
        return {
            "id": task.id,
            "task_type": task.task_type,
            "entity_type": task.entity_type,
            "entity_id": task.entity_id,
            "status": task.status,
            "stage": task.stage,
            "attempts": task.attempts,
            "error_code": task.error_code,
            "error_message": task.error_message,
            "result": task.result,
            "updated_at": task.updated_at,
            "completed_at": task.completed_at,
        }
