from pathlib import Path

import pytest

from app.core.config import Settings


def test_depth_defaults_preserve_phase_a_18_6():
    settings = Settings(_env_file=None)

    assert settings.rag_candidate_top_k == 18
    assert settings.rag_final_context_top_k == 6
    assert settings.rag_max_sources_per_material == 3


def test_explicit_top7_keeps_candidate_depth_18():
    settings = Settings(_env_file=None, rag_final_context_top_k=7)

    assert settings.rag_candidate_top_k == 18
    assert settings.rag_final_context_top_k == 7


def test_final_depth_cannot_exceed_candidate_depth():
    with pytest.raises(ValueError, match="RAG_FINAL_CONTEXT_TOP_K"):
        Settings(
            _env_file=None,
            rag_candidate_top_k=6,
            rag_final_context_top_k=7,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("rag_candidate_top_k", 0, "RAG_CANDIDATE_TOP_K"),
        ("rag_final_context_top_k", 0, "RAG_FINAL_CONTEXT_TOP_K"),
    ],
)
def test_depths_must_be_positive(field, value, message):
    with pytest.raises(ValueError, match=message):
        Settings(_env_file=None, **{field: value})


def test_explicit_new_env_keys_win_and_legacy_keys_are_ignored(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "RAG_TOP_K_DEFAULT=2\n"
        "RAG_MAX_SOURCES=2\n"
        "RAG_CANDIDATE_TOP_K=18\n"
        "RAG_FINAL_CONTEXT_TOP_K=7\n"
        "RAG_MAX_SOURCES_PER_MATERIAL=3\n",
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_path)

    assert settings.rag_candidate_top_k == 18
    assert settings.rag_final_context_top_k == 7
    assert settings.rag_max_sources_per_material == 3
    assert "rag_top_k_default" not in Settings.model_fields
    assert "rag_max_sources" not in Settings.model_fields
