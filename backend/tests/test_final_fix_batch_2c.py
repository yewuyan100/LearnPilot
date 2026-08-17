import json
import re
from pathlib import Path

from app.core.config import Settings


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_VERSION = "6.0.0"


def _env_value(path: Path, key: str) -> str | None:
    prefix = f"{key}="
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix):
            return line.removeprefix(prefix).strip()
    return None


def test_version_sources_and_meta_are_canonical(client):
    http, _ = client
    package = json.loads((PROJECT_ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    package_lock = json.loads((PROJECT_ROOT / "frontend" / "package-lock.json").read_text(encoding="utf-8"))

    assert Settings.model_fields["app_version"].default == CANONICAL_VERSION
    assert _env_value(PROJECT_ROOT / ".env.example", "APP_VERSION") == CANONICAL_VERSION
    if (PROJECT_ROOT / ".env").exists():
        assert _env_value(PROJECT_ROOT / ".env", "APP_VERSION") == CANONICAL_VERSION
    assert package["version"] == CANONICAL_VERSION
    assert package_lock["version"] == CANONICAL_VERSION
    assert package_lock["packages"][""]["version"] == CANONICAL_VERSION
    assert http.get("/api/meta").json()["app_version"] == CANONICAL_VERSION


def test_openapi_uses_product_identity_without_milestone_copy(client):
    http, _ = client
    info = http.get("/openapi.json").json()["info"]

    assert info["title"] == "PersonalLearning"
    assert info["version"] == CANONICAL_VERSION
    assert info["description"] == "PersonalLearning 本地优先个人学习管理 API"
    assert re.search(r"\bV\d+\b", info["description"]) is None


def test_environment_can_still_override_version(monkeypatch):
    monkeypatch.setenv("APP_VERSION", "9.9.9")
    assert Settings(_env_file=None).app_version == "9.9.9"
