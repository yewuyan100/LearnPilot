from app.core.config import Settings


def test_csv_tuple_settings_match_env_example(monkeypatch):
    monkeypatch.setenv("ALLOWED_FILE_EXTENSIONS", ".pdf,.md,.txt")
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
    settings = Settings(_env_file=None)
    assert settings.allowed_file_extensions == (".pdf", ".md", ".txt")
    assert settings.cors_origins == (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )
