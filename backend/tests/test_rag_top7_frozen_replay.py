import importlib.util
from pathlib import Path

import pytest


RUNNER = (
    Path(__file__).resolve().parents[2]
    / "evals/rag_real_world_corpus/v1/results/rag_candidate_final_depth_decoupling"
    / "20260816T101548Z-depthdecouple/replay_frozen.py"
)


@pytest.fixture(scope="module")
def replay_module():
    spec = importlib.util.spec_from_file_location("top7_frozen_replay", RUNNER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def phase_a_rows(replay_module):
    return [replay_module.replay_case(trace, 6) for trace in replay_module.traces]


@pytest.fixture(scope="module")
def phase_b_rows(replay_module):
    return [replay_module.replay_case(trace, 7) for trace in replay_module.traces]


def test_phase_a_frozen_18_6_is_exact_noop(replay_module, phase_a_rows):
    assert len(phase_a_rows) == 72
    assert all(row["candidate_count"] == 18 for row in phase_a_rows)
    assert all(row["reranker_input_count"] == 18 for row in phase_a_rows)
    assert all(
        row["selected_ids"]
        == replay_module.cuda_by_id[row["case_id"]]["cuda_top6"]
        for row in phase_a_rows
    )
    assert all(
        row["context_digest"]
        == replay_module.cuda_by_id[row["case_id"]]["cuda_context_digest"]
        for row in phase_a_rows
    )


def test_phase_b_frozen_18_7_reaches_expected_coverage(phase_b_rows):
    assert len(phase_b_rows) == 72
    assert all(row["candidate_count"] == 18 for row in phase_b_rows)
    assert all(row["reranker_input_count"] == 18 for row in phase_b_rows)
    assert sum(row["full_required_coverage"] for row in phase_b_rows) == 59


def test_top7_order_is_deterministic(replay_module):
    trace = next(
        row for row in replay_module.traces
        if row["case_id"] == "rw-gold-v1-disambig-fastapi-async-deps"
    )
    first = replay_module.replay_case(trace, 7)
    second = replay_module.replay_case(trace, 7)

    assert first["selected_ids"] == second["selected_ids"]
    assert first["context_digest"] == second["context_digest"]


def test_fastapi_and_multi_agent_top7_regressions(phase_b_rows):
    by_id = {row["case_id"]: row for row in phase_b_rows}
    fastapi = by_id["rw-gold-v1-disambig-fastapi-async-deps"]
    multi = by_id["rw-gold-v1-multi-agent-resume"]

    assert fastapi["full_required_coverage"] is True
    assert 314 in fastapi["selected_chunk_ids"]
    assert multi["full_required_coverage"] is True
    assert 237 in multi["selected_chunk_ids"]


def test_top7_context_budget_and_actual_selected_count(phase_b_rows):
    assert not any(row["budget_violation"] for row in phase_b_rows)
    assert max(row["serialized_chars"] for row in phase_b_rows) == 7146
    assert all(row["selected_count"] <= 7 for row in phase_b_rows)
