from __future__ import annotations

import logging
from pathlib import Path

from fastapi import status
from sqlalchemy import select

from app.core.clock import Clock
from app.core.errors import AppError
from app.models.maintenance_task import MaintenanceTask
from app.models.material import Material
from app.services.maintenance import MaintenanceTaskStore
from app.services.vector_store.service import MaterialIndexService
from app.services.course_architecture.drafts import CourseArchitectureDraftService


logger = logging.getLogger("personal_learning.material_deletion")


class MaterialDeletionService:
    def __init__(self, db, settings, embedder, clock: Clock):
        self.db = db
        self.settings = settings
        self.embedder = embedder
        self.clock = clock
        self.tasks = MaintenanceTaskStore(db, clock)

    @staticmethod
    def request_key(material_id: int) -> str:
        return f"material-delete:{material_id}"

    def task_for(self, material_id: int) -> MaintenanceTask | None:
        return self.db.scalar(
            select(MaintenanceTask).where(
                MaintenanceTask.request_key == self.request_key(material_id)
            )
        )

    def delete(self, material_id: int) -> dict:
        material = self.db.get(Material, material_id)
        existing = self.task_for(material_id)
        if material is None:
            if existing and existing.status == "completed":
                return self.tasks.serialize(existing)
            raise AppError(
                "material_not_found", "资料不存在", status.HTTP_404_NOT_FOUND
            )

        task = existing or self.tasks.get_or_create(
            task_type="material_delete",
            entity_type="material",
            entity_id=material_id,
            request_key=self.request_key(material_id),
            payload={"material_id": material_id, "file_path": material.file_path},
        )
        if task.status == "completed":
            return self.tasks.serialize(task)

        self.tasks.start(task, "rebuild_index")
        material.deletion_status = "pending"
        material.deletion_error = None
        material.deletion_requested_at = material.deletion_requested_at or self.clock.now()
        material.deletion_attempts += 1
        CourseArchitectureDraftService(self.db, self.clock).mark_stale_for_material(
            material.id, "资料进入删除流程，需要重新选择或重新分析资料。"
        )
        self.db.commit()

        try:
            MaterialIndexService(self.db, self.settings, self.embedder).rebuild()
        except Exception as exc:
            self.db.rollback()
            material = self.db.get(Material, material_id)
            task = self.db.get(MaintenanceTask, task.id)
            material.deletion_status = "failed"
            material.deletion_error = "资料索引更新失败，可重新尝试"
            self.db.commit()
            self.tasks.fail(
                task,
                stage="rebuild_index",
                error_code="material_index_rebuild_failed",
                error_message=type(exc).__name__,
            )
            logger.exception("material_delete_failed material_id=%s stage=rebuild_index", material_id)
            raise AppError(
                "material_delete_pending",
                "资料删除尚未完成，索引更新失败，可重新尝试",
                status.HTTP_503_SERVICE_UNAVAILABLE,
                {"maintenance_task_id": task.id, "stage": "rebuild_index"},
            ) from exc

        task = self.db.get(MaintenanceTask, task.id)
        task.stage = "delete_file"
        self.db.commit()
        try:
            Path(material.file_path).unlink(missing_ok=True)
        except OSError as exc:
            self.db.rollback()
            material = self.db.get(Material, material_id)
            task = self.db.get(MaintenanceTask, task.id)
            material.deletion_status = "failed"
            material.deletion_error = "原始文件删除失败，可重新尝试"
            self.db.commit()
            self.tasks.fail(
                task,
                stage="delete_file",
                error_code="material_file_delete_failed",
                error_message=type(exc).__name__,
            )
            logger.exception("material_delete_failed material_id=%s stage=delete_file", material_id)
            raise AppError(
                "material_delete_pending",
                "资料删除尚未完成，原始文件删除失败，可重新尝试",
                status.HTTP_503_SERVICE_UNAVAILABLE,
                {"maintenance_task_id": task.id, "stage": "delete_file"},
            ) from exc

        path = material.file_path
        self.db.delete(material)
        self.db.flush()
        task = self.db.get(MaintenanceTask, task.id)
        result = {"material_id": material_id, "file_path": path, "index_result": "rebuilt"}
        return self.tasks.serialize(self.tasks.complete(task, result))
