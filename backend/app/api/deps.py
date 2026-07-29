from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.services.embedding.base import Embedder
from app.services.embedding.service import build_embedder

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def get_embedder(settings: AppSettings) -> Embedder:
    return build_embedder(settings)


EmbedderDep = Annotated[Embedder, Depends(get_embedder)]
