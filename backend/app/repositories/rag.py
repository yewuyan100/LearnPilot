from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.clock import Clock
from app.models.rag_citation import RagCitation
from app.models.rag_conversation import RagConversation
from app.models.rag_message import RagMessage


class RagRepository:
    def __init__(self, db: Session, clock: Clock):
        self.db = db
        self.clock = clock

    def get_conversation(self, conversation_id: int) -> RagConversation:
        conversation = self.db.get(RagConversation, conversation_id)
        if conversation is None:
            raise AppError(
                "rag_conversation_not_found",
                "资料问答会话不存在",
                status.HTTP_404_NOT_FOUND,
                {"id": conversation_id},
            )
        return conversation

    def list_conversations(
        self, *, status_filter: str | None, offset: int, limit: int
    ) -> tuple[list[RagConversation], int]:
        filters = (
            [RagConversation.status == status_filter] if status_filter else []
        )
        rows = self.db.scalars(
            select(RagConversation)
            .where(*filters)
            .order_by(
                RagConversation.last_message_at.desc().nullslast(),
                RagConversation.created_at.desc(),
                RagConversation.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        ).all()
        total = self.db.scalar(
            select(func.count(RagConversation.id)).where(*filters)
        ) or 0
        return list(rows), total

    def messages(
        self, conversation_id: int, *, offset: int = 0, limit: int = 100
    ) -> tuple[list[RagMessage], int]:
        filters = [RagMessage.conversation_id == conversation_id]
        rows = self.db.scalars(
            select(RagMessage)
            .where(*filters)
            .order_by(RagMessage.created_at, RagMessage.id)
            .offset(offset)
            .limit(limit)
        ).all()
        total = self.db.scalar(select(func.count(RagMessage.id)).where(*filters)) or 0
        return list(rows), total

    def recent_completed_messages(
        self, conversation_id: int, *, limit: int
    ) -> list[RagMessage]:
        rows = self.db.scalars(
            select(RagMessage)
            .where(
                RagMessage.conversation_id == conversation_id,
                RagMessage.status == "completed",
            )
            .order_by(RagMessage.created_at.desc(), RagMessage.id.desc())
            .limit(limit)
        ).all()
        return list(reversed(rows))

    def citations(self, assistant_message_id: int) -> list[RagCitation]:
        return list(
            self.db.scalars(
                select(RagCitation)
                .where(RagCitation.assistant_message_id == assistant_message_id)
                .order_by(RagCitation.rank, RagCitation.id)
            ).all()
        )

    def find_by_request(
        self, conversation_id: int, request_id: str
    ) -> RagMessage | None:
        return self.db.scalar(
            select(RagMessage).where(
                RagMessage.conversation_id == conversation_id,
                RagMessage.request_id == request_id,
                RagMessage.role == "assistant",
            )
        )

    def touch(self, conversation: RagConversation) -> None:
        conversation.last_message_at = self.clock.now()
