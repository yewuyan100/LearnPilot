from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class NextActionAcceptance(TimestampMixin, Base):
    """Small idempotency/audit record; recommendations themselves remain computed state."""

    __tablename__ = "next_action_acceptances"
    __table_args__ = (
        UniqueConstraint("request_id", name="uq_next_action_acceptances_request_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    action_signature: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    original_target_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    original_target_id: Mapped[int | None] = mapped_column(nullable=True)
    outcome: Mapped[dict] = mapped_column(JSON, nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
