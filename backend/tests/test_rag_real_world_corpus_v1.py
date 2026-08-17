from __future__ import annotations

from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "evals" / "rag_real_world_corpus" / "v1"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manifest_is_frozen_licensed_and_balanced():
    manifest = json.loads((BASE / "corpus_manifest.json").read_text(encoding="utf-8"))
    documents = manifest["documents"]
    assert manifest["corpus_id"] == "learnpilot-rag-real-world-corpus"
    assert manifest["corpus_version"] == "v1"
    assert manifest["document_count"] == len(documents) == 11
    assert manifest["format_plan"] == {"md": 8, "txt": 1, "pdf": 2}
    assert manifest["topic_plan"] == {
        "rag_retrieval": 2,
        "agent_engineering": 3,
        "ai_app_backend": 3,
        "evaluation_reliability": 3,
    }
    assert len({item["document_id"] for item in documents}) == len(documents)
    assert {item["license"] for item in documents} <= {"MIT", "Apache-2.0", "CC-BY-4.0"}
    for item in documents:
        corpus_path = ROOT / item["repository_path"]
        license_path = ROOT / item["license_repository_path"]
        assert corpus_path.is_file()
        assert license_path.is_file()
        assert sha256(corpus_path.read_bytes()).hexdigest() == item["corpus_sha256"]
        assert sha256(license_path.read_bytes()).hexdigest() == item["license_sha256"]
        assert len(item["upstream_commit_sha"]) == 40
        assert item["upstream_commit_sha"] in item["license_source"]


def test_frozen_validation_report_and_projected_shape():
    # validate_corpus.py is the acquisition-phase gate and intentionally rejects
    # co-located Gold output. Once gold/v1 exists, validate the frozen report here;
    # executable Gold-phase validation belongs to gold/v1/validate_gold.py.
    validation = json.loads((BASE / "validation_report.json").read_text(encoding="utf-8"))
    duplicate_analysis = json.loads((BASE / "duplicate_overlap_analysis.json").read_text(encoding="utf-8"))
    assert validation["status"] == "passed"
    assert validation["projected_chunk_count"] == 442
    assert 150 <= validation["projected_chunk_count"] <= 600
    assert validation["exact_duplicates"] == 0
    assert validation["near_duplicates"] == 0
    assert validation["all_licenses_verified"] is True
    assert duplicate_analysis["exact_duplicate_hashes"] == []
    assert duplicate_analysis["near_duplicates"] == []


def test_ingestion_runner_is_isolated_and_has_no_answer_model_path(monkeypatch, tmp_path):
    runner = load_module("rag_real_world_ingestion", BASE / "run_ingestion.py")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "must-not-survive")
    monkeypatch.setenv("SOME_SECRET", "must-not-survive")
    environment = runner.sanitized_environment(tmp_path)
    assert "DEEPSEEK_API_KEY" not in environment
    assert "SOME_SECRET" not in environment
    assert environment["LLM_API_KEY"] == ""
    assert environment["LLM_BASE_URL"] == ""
    assert environment["LLM_MODEL"] == ""
    assert environment["EMBEDDING_LOCAL_FILES_ONLY"] == "true"
    source = (BASE / "run_ingestion.py").read_text(encoding="utf-8")
    assert '"POST", "/materials/upload"' in source
    assert '/materials/{uploaded[\'id\']}/process' in source
    assert "/rag/conversations" not in source
    assert "api.deepseek.com" not in source


def test_gold_contract_is_separate_from_frozen_corpus_artifacts():
    frozen_input_names = {path.name.lower() for path in (BASE / "corpus").rglob("*") if path.is_file()}
    assert not any("gold" in name for name in frozen_input_names)
    for name in ("corpus_manifest.json", "acquisition_lock.json", "source_decisions.json"):
        assert '"gold' not in (BASE / name).read_text(encoding="utf-8").casefold()
    assert (BASE / "gold" / "v1" / "gold_cases.json").is_file()
