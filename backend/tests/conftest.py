from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings, get_settings
from app.api.deps import get_embedder
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from tests.fakes import FakeEmbedder


@pytest.fixture()
def client(tmp_path: Path):
    database_path = tmp_path / "test.sqlite3"
    upload_path = tmp_path / "uploads"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    settings = Settings(
        database_url=f"sqlite:///{database_path}",
        upload_dir=upload_path,
        max_upload_size_mb=1,
        demo_data_enabled=False,
        material_chunk_size=160,
        material_chunk_overlap=30,
        material_min_chunk_size=20,
        embedding_model_name="fake/bge-m3",
        embedding_model_revision="test",
        faiss_index_path=tmp_path / "materials.faiss",
        faiss_manifest_path=tmp_path / "materials.faiss.manifest.json",
        search_top_k_default=3,
        search_top_k_max=10,
    )
    fake_embedder = FakeEmbedder()

    def override_db():
        with TestingSession() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_embedder] = lambda: fake_embedder
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client, upload_path
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def goal_payload():
    return {
        "title": "三周入门 MCP",
        "description": "理解 MCP 的核心概念",
        "target_date": "2026-08-19",
        "daily_minutes": 40,
        "current_level": "了解普通 API",
        "status": "active",
    }
