from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.material import Material


def touch_material(material: Material, candidate: datetime) -> datetime:
    """Advance the material revision timestamp even under a fixed/coarse clock."""

    current = material.updated_at
    if current is not None and _comparable(candidate) <= _comparable(current):
        candidate = current + timedelta(microseconds=1)
    material.updated_at = candidate
    return candidate


def _comparable(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
