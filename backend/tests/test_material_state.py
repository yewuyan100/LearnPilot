from datetime import datetime, timezone

from app.models.material import Material
from app.services.material_state import touch_material


def material_with_revision(value: datetime) -> Material:
    material = Material(
        title="source",
        original_filename="source.md",
        stored_filename="source.md",
        file_path="source.md",
        source_type="markdown",
        mime_type="text/markdown",
        file_size=10,
    )
    material.updated_at = value
    return material


def test_material_revision_advances_when_clock_is_fixed():
    current = datetime(2026, 8, 5, 12, 0)
    material = material_with_revision(current)

    revision = touch_material(
        material, datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)
    )

    assert revision > current
    assert material.updated_at == revision


def test_material_revision_uses_a_later_clock_value():
    current = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)
    later = datetime(2026, 8, 5, 12, 1, tzinfo=timezone.utc)
    material = material_with_revision(current)

    assert touch_material(material, later) == later
