from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest
from pydantic import SecretStr


ROOT = Path(__file__).resolve().parents[2]
V1 = ROOT / "evals/rag_real_world_corpus/v1"
PHASE = V1 / "hybrid_rerank_phase3_v1_1"
if str(PHASE) not in sys.path:
    sys.path.insert(0, str(PHASE))

from experiment import (  # noqa: E402
    ABLATION_DESIGN_SHA256,
    ARMS,
    DESIGN_VERSION,
    ENDPOINT_PATH,
    MAX_NORMAL_GENERATION_REQUESTS,
    MODEL_NAME,
    PHASE2_RUN_ID,
    PROVIDER_HOST,
    ContractViolation,
    DeepSeekGenerationAdapter,
    GenerationContract,
    TransportResponse,
    freeze_phase2_contexts,
    json_sha256,
    sources_from_frozen_context,
    validate_generation_result,
)


PHASE2_DIR = V1 / f"results/hybrid_rerank_phase2_v1_1/{PHASE2_RUN_ID}"
GOLD_PATH = V1 / "gold/v1/gold_cases.json"


def file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def settings() -> SimpleNamespace:
    return SimpleNamespace(
        llm_configured=True,
        llm_provider="openai_compatible",
        llm_base_url="https://api.deepseek.com",
        llm_model=MODEL_NAME,
        llm_structured_model_name=MODEL_NAME,
        llm_temperature=0.1,
        llm_structured_reasoning_enabled=False,
        llm_structured_max_output_tokens=2400,
        llm_timeout_seconds=60,
        llm_max_retries=2,
        rag_prompt_version="rag-answer-v2-evidence-binding",
        llm_api_key=SecretStr("test-only-key"),
    )


def response(content: dict, *, status: int = 200, model: str = MODEL_NAME) -> TransportResponse:
    body = {
        "id": "deepseek-response-test",
        "model": model,
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "content": json.dumps(content, ensure_ascii=False, separators=(",", ":"))
                },
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
    }
    return TransportResponse(
        status_code=status,
        body_text=json.dumps(body, ensure_ascii=False),
        elapsed_ms=5.0,
        response_headers={"x-request-id": "provider-request-test"},
    )


class ScriptedTransport:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls: list[dict] = []

    def post(self, **kwargs):
        self.calls.append(
            {
                "base_url": kwargs["base_url"],
                "endpoint_path": kwargs["endpoint_path"],
                "payload": kwargs["payload"],
                "timeout_seconds": kwargs["timeout_seconds"],
                "authorization_present": bool(kwargs["headers"].get("Authorization")),
            }
        )
        value = self.outcomes.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


@pytest.fixture(scope="module")
def frozen_contexts():
    gold = json.loads(GOLD_PATH.read_text(encoding="utf-8"))["cases"]
    return freeze_phase2_contexts(phase2_run_dir=PHASE2_DIR, gold_cases=gold)


def adapter(outcomes):
    ledger: list[dict] = []
    transport = ScriptedTransport(outcomes)
    value = DeepSeekGenerationAdapter(
        settings=settings(),
        contract=GenerationContract.from_settings(settings()),
        transport=transport,
        ledger_sink=ledger.append,
    )
    return value, transport, ledger


def test_phase3_frozen_identities_are_exact():
    assert DESIGN_VERSION == "V1.1"
    assert ABLATION_DESIGN_SHA256 == "442bedce1c43b27b3557b0055708342edd278e98bcac0c12a68c1390fe88f655"
    assert PHASE2_RUN_ID == "20260814T095542Z-1317c6a7"
    assert MODEL_NAME == "deepseek-v4-flash"
    assert PROVIDER_HOST == "api.deepseek.com"
    assert ARMS == ("B", "C", "D")
    assert MAX_NORMAL_GENERATION_REQUESTS == 216


def test_hard_gate_frozen_hashes_and_phase2_manifest_are_unchanged():
    expected = {
        V1 / "ablation_design_v1_1/ablation_design_manifest.json": ABLATION_DESIGN_SHA256,
        GOLD_PATH: "33a0b69901fa47e3fe45be0277228cd4a5519fe780fe5b9d2c52b1bfe614927a",
        V1 / "corpus_manifest.json": "6f67d510cd35197f107400d33033972c0c3c84478174e4991e491f6c8e4ab563",
        V1 / "results/dense_only_baseline_v1/20260814T052007Z-593cd2ac/raw_results.json": "bf718aed08e226149c9310cbf20bf25c403708217e2908789120178ac5574e28",
    }
    assert {path: file_hash(path) for path in expected} == expected
    latest = json.loads(
        (V1 / "results/hybrid_rerank_phase2_v1_1/latest_run.json").read_text(encoding="utf-8")
    )
    manifest_path = PHASE2_DIR / "artifact_manifest.json"
    assert latest["run_id"] == PHASE2_RUN_ID and latest["status"] == "PASS"
    assert file_hash(manifest_path) == latest["artifact_manifest_sha256"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for item in manifest["result_files"] + manifest["implementation_and_report_files"]:
        path = ROOT / item["path"]
        assert path.stat().st_size == item["size_bytes"]
        assert file_hash(path) == item["sha256"]


def test_generation_contract_matches_frozen_historical_configuration():
    contract = GenerationContract.from_settings(settings())
    assert contract.model == MODEL_NAME
    assert contract.provider_host == PROVIDER_HOST
    assert contract.endpoint_path == ENDPOINT_PATH
    assert contract.temperature == 0.1
    assert contract.reasoning_enabled is False
    assert contract.max_output_tokens == 2400
    assert contract.timeout_seconds == 60
    assert contract.max_retries == 2
    assert contract.grounding_repair_limit == 1
    assert contract.identity == json_sha256(
        {key: value for key, value in contract.as_public_dict().items() if key != "identity"}
    )


def test_generation_contract_rejects_wrong_host_or_model():
    wrong = settings()
    wrong.llm_base_url = "https://example.com"
    with pytest.raises(ContractViolation, match="generation contract drift"):
        GenerationContract.from_settings(wrong)
    wrong = settings()
    wrong.llm_structured_model_name = "another-model"
    with pytest.raises(ContractViolation, match="generation contract drift"):
        GenerationContract.from_settings(wrong)


def test_phase2_context_freeze_has_exact_216_records(frozen_contexts):
    assert len(frozen_contexts) == 216
    assert {arm: sum(row["arm"] == arm for row in frozen_contexts) for arm in ARMS} == {
        "B": 72,
        "C": 72,
        "D": 72,
    }
    assert len({(row["arm"], row["case_id"]) for row in frozen_contexts}) == 216
    assert all(row["source_count"] <= 6 for row in frozen_contexts)
    assert all(row["context_raw_text_chars"] <= 12000 for row in frozen_contexts)
    for row in frozen_contexts:
        sources = sources_from_frozen_context(row)
        assert [source.source_label for source in sources] == [
            f"S{index}" for index in range(1, len(sources) + 1)
        ]
        assert row["selected_candidate_identities"] == [
            item["identity"] for item in row["selected_sources"]
        ]


def test_context_freeze_detects_exact_text_tampering(frozen_contexts):
    tampered = json.loads(json.dumps(frozen_contexts[0], ensure_ascii=False))
    tampered["selected_sources"][0]["raw_text"] += "x"
    with pytest.raises(ContractViolation, match="CONTEXT_FREEZE_MISMATCH"):
        sources_from_frozen_context(tampered)


def test_payload_is_exact_structured_contract_and_contains_no_secret(frozen_contexts):
    value, _, _ = adapter([])
    payload = value._payload(frozen_contexts[0]["generation_messages"])
    assert set(payload) == {
        "model",
        "messages",
        "max_tokens",
        "response_format",
        "thinking",
        "temperature",
    }
    assert payload["model"] == MODEL_NAME
    assert payload["thinking"] == {"type": "disabled"}
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["temperature"] == 0.1 and payload["max_tokens"] == 2400
    assert payload["messages"][-1]["role"] == "system"
    assert "JSON Schema contract" in payload["messages"][-1]["content"]
    assert "test-only-key" not in json.dumps(payload, ensure_ascii=False)


def test_successful_generation_freezes_raw_parsed_and_rendered(frozen_contexts):
    outcome = {
        "answerable": True,
        "blocks": [{"content_markdown": "受资料支持。", "source_ids": ["S1"]}],
        "refusal_reason": None,
    }
    value, transport, ledger = adapter([response(outcome)])
    result = value.generate(frozen_contexts[0], phase3_run_id="phase3-test")
    assert result["status"] == "COMPLETED"
    assert result["parse_status"] == "parsed"
    assert result["answer_markdown"] == "受资料支持。[S1]"
    assert result["citation_ids"] == ["S1"]
    assert result["raw_provider_responses"][0]["raw_provider_response"]
    assert result["parsed_structured_result"] == outcome
    assert result["usage"] == {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}
    assert len(transport.calls) == 1 and transport.calls[0]["base_url"] == "https://api.deepseek.com"
    assert [event["event"] for event in ledger] == [
        "http_request_started",
        "http_request_completed",
    ]
    assert not validate_generation_result(
        result, frozen_contexts[0], contract_identity=value.contract.identity
    )


def test_grounding_repair_uses_frozen_single_repair_contract(frozen_contexts):
    invalid = {
        "answerable": True,
        "blocks": [{"content_markdown": "缺少来源", "source_ids": []}],
        "refusal_reason": None,
    }
    repaired = {
        "answerable": True,
        "blocks": [{"content_markdown": "已绑定来源", "source_ids": ["S1"]}],
        "refusal_reason": None,
    }
    value, transport, _ = adapter([response(invalid), response(repaired)])
    result = value.generate(frozen_contexts[0], phase3_run_id="phase3-test")
    assert result["status"] == "COMPLETED"
    assert result["repair_attempted"] is True
    assert result["structured_call_count"] == 2
    assert result["attempt_count"] == 2
    assert "allowed_source_ids" in json.dumps(
        transport.calls[1]["payload"]["messages"], ensure_ascii=False
    )


def test_transport_retry_reuses_identical_payload_and_is_not_new_sample(frozen_contexts):
    retry = TransportResponse(429, "rate limited", 3.0, {})
    valid = {
        "answerable": False,
        "blocks": [],
        "refusal_reason": "资料不足",
    }
    value, transport, _ = adapter([retry, response(valid)])
    result = value.generate(frozen_contexts[0], phase3_run_id="phase3-test")
    assert result["status"] == "COMPLETED"
    assert result["retry_count"] == 1
    assert result["attempt_count"] == 2
    assert value.normal_generation_calls == 1
    assert transport.calls[0]["payload"] == transport.calls[1]["payload"]


def test_parse_failure_uses_repair_without_changing_normal_sample_count(frozen_contexts):
    malformed = TransportResponse(200, '{"id":"x","choices":[', 2.0, {})
    repaired = {
        "answerable": False,
        "blocks": [],
        "refusal_reason": "资料不足",
    }
    value, _, _ = adapter([malformed, response(repaired)])
    result = value.generate(frozen_contexts[0], phase3_run_id="phase3-test")
    assert result["status"] == "COMPLETED"
    assert result["repair_attempted"] is True
    assert value.normal_generation_calls == 1


def test_provider_model_mismatch_blocks_result(frozen_contexts):
    valid = {
        "answerable": False,
        "blocks": [],
        "refusal_reason": "资料不足",
    }
    value, _, _ = adapter([response(valid, model="unexpected-model")])
    result = value.generate(frozen_contexts[0], phase3_run_id="phase3-test")
    assert result["status"] == "FAILED"
    assert result["provider_failure"] is True
    assert "model_mismatch" in result["parse_status"]


def test_unknown_citation_cannot_pass_machine_validation(frozen_contexts):
    invalid = {
        "answerable": True,
        "blocks": [{"content_markdown": "错误引用", "source_ids": ["S99"]}],
        "refusal_reason": None,
    }
    value, _, _ = adapter([response(invalid), response(invalid)])
    result = value.generate(frozen_contexts[0], phase3_run_id="phase3-test")
    assert result["status"] == "FAILED"
    assert result["validation_status"] == "FAIL"


def test_normal_request_cap_is_hard(frozen_contexts):
    value, _, _ = adapter([])
    value.normal_generation_calls = MAX_NORMAL_GENERATION_REQUESTS
    with pytest.raises(ContractViolation, match="cap"):
        value.generate(frozen_contexts[0], phase3_run_id="phase3-test")


def test_result_identity_detects_post_generation_edit(frozen_contexts):
    valid = {
        "answerable": False,
        "blocks": [],
        "refusal_reason": "资料不足",
    }
    value, _, _ = adapter([response(valid)])
    result = value.generate(frozen_contexts[0], phase3_run_id="phase3-test")
    result["refusal_reason"] = "edited"
    assert "result_identity_mismatch" in validate_generation_result(
        result, frozen_contexts[0], contract_identity=value.contract.identity
    )
