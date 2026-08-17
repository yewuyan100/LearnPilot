from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.clock import Clock, clock_from_settings
from app.db.session import get_db
from app.services.embedding.base import Embedder
from app.services.embedding.service import build_embedder
from app.services.llm.base import LLMProvider
from app.services.llm.openai_compatible import OpenAICompatibleProvider

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def get_clock(request: Request, settings: AppSettings) -> Clock:
    return getattr(request.app.state, "clock", None) or clock_from_settings(settings)


AppClock = Annotated[Clock, Depends(get_clock)]


def get_embedder(settings: AppSettings) -> Embedder:
    return build_embedder(settings)


EmbedderDep = Annotated[Embedder, Depends(get_embedder)]


def get_llm_provider(settings: AppSettings) -> LLMProvider | None:
    if not settings.llm_configured:
        return None
    return OpenAICompatibleProvider(settings)


LLMProviderDep = Annotated[LLMProvider | None, Depends(get_llm_provider)]
