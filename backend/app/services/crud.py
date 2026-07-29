from typing import Any, TypeVar

from sqlalchemy.orm import Session

from app.core.errors import not_found

ModelT = TypeVar("ModelT")


def get_or_404(db: Session, model: type[ModelT], object_id: int, label: str) -> ModelT:
    instance = db.get(model, object_id)
    if instance is None:
        raise not_found(label, object_id)
    return instance


def apply_updates(instance: Any, values: dict[str, Any]) -> None:
    for field, value in values.items():
        setattr(instance, field, value)


def commit(db: Session, instance: ModelT | None = None) -> ModelT | None:
    try:
        db.commit()
        if instance is not None:
            db.refresh(instance)
        return instance
    except Exception:
        db.rollback()
        raise

