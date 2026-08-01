from typing import Any

from fastapi import status


V6_ERROR_CODES = frozenset({
    "mastery_not_found", "mastery_unassessed", "mastery_calculation_failed",
    "mastery_evidence_invalid", "mastery_rebuild_failed", "self_assessment_invalid",
    "review_schedule_not_found", "review_schedule_conflict", "review_already_completed",
    "adaptive_recommendation_not_found", "adaptive_recommendation_expired",
    "adaptive_recommendation_conflict", "adaptive_task_creation_failed",
})


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: Any | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)


def not_found(resource: str, resource_id: int) -> AppError:
    return AppError(
        "not_found",
        f"{resource}不存在",
        status.HTTP_404_NOT_FOUND,
        {"id": resource_id},
    )
