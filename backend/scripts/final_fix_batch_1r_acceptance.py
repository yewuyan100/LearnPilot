import argparse
import json
import re
import sys
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.models import Material
from app.models.rag_citation import RagCitation
from app.models.rag_message import RagMessage
from app.schemas.agent import AgentConversationContext
from app.services.agent.runtime import AgentRuntime
from app.services.agent.service import AgentService
from app.services.embedding.service import build_embedder
from app.services.llm.openai_compatible import OpenAICompatibleProvider
from app.services.rag.service import RagConversationService
from app.services.vector_store.faiss_store import FaissStore


QUESTION = "根据这份资料帮我梳理最重要的内容。"
CONTEXT_MARKER = "\n\n[系统已带入的协作上下文]"
FORBIDDEN_OUTPUT_MARKERS = (
    "answer_missing_citations",
    "citation_declaration_mismatch",
    "tool_arguments_invalid",
    "grounded_answer_invalid",
    "invalid_json",
    "ValueError",
    "traceback",
)
CITATION_PATTERN = re.compile(r"\[(S\d+)\]")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--material-id", type=int, default=1)
    parser.add_argument("--runs", type=int, default=3)
    return parser.parse_args()


def source_record(source) -> dict:
    return {
        "source_label": source.source_label,
        "chunk_id": source.chunk_id,
        "material_id": source.material_id,
        "original_filename": source.original_filename,
        "chunk_index": source.chunk_index,
        "page_number": source.page_number,
        "section_title": source.section_title,
        "score": source.score,
    }


def citation_record(citation) -> dict:
    return {
        "source_label": citation.source_label,
        "chunk_id": citation.chunk_id,
        "material_id": citation.material_id,
        "original_filename": citation.original_filename,
        "chunk_index": citation.chunk_index,
        "page_number": citation.page_number,
        "section_title": citation.section_title,
        "score": citation.score,
    }


def persisted_citation_is_retrieved(citation: dict, source_by_label: dict) -> bool:
    source = source_by_label.get(citation["source_label"])
    if source is None:
        return False
    return (
        citation["chunk_id"] == source.chunk_id
        and citation["material_id"] == source.material_id
        and citation["original_filename"] == source.original_filename
        and citation["chunk_index"] == source.chunk_index
        and citation["page_number"] == source.page_number
        and citation["section_title"] == source.section_title
        and abs(citation["score"] - source.score) < 1e-9
    )


def grounding_evidence(capture: dict) -> dict:
    grounded = capture["result"]
    calls = capture["provider_calls"]
    successful_calls = [call for call in calls if call["success"]]
    final_call = successful_calls[-1] if successful_calls else None
    draft = final_call["structured_value"] if final_call else None
    blocks = (draft or {}).get("blocks") or []
    generation_latency_ms = sum(call["latency_ms"] for call in calls)
    return {
        "model": grounded.model_name,
        "initial_finish_reason": grounded.initial_finish_reason,
        "finish_reason": grounded.finish_reason,
        "provider_content_nonempty": bool(
            final_call and final_call["provider_content_nonempty"]
        ),
        "structured_schema_validation": bool(final_call),
        "structured_draft": draft,
        "answerable": grounded.answer.answerable,
        "evidence_block_count": len(blocks),
        "validated_block_source_ids": [block.get("source_ids", []) for block in blocks],
        "repair_triggered": grounded.repair_attempted,
        "repair_count": int(grounded.repair_attempted),
        "initial_validation_reason": grounded.initial_validation_reason,
        "provider_calls": calls,
        "model_generation_latency_ms": generation_latency_ms,
    }


def main() -> int:
    args = parse_args()
    database = args.database.resolve()
    output = args.output.resolve()
    if not database.is_file():
        raise SystemExit(f"Database copy does not exist: {database}")

    settings = Settings(
        database_url=f"sqlite:///{database.as_posix()}",
        agent_checkpoint_enabled=False,
    )
    if not settings.llm_configured:
        raise SystemExit("Real LLM is not configured")

    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    embedder = build_embedder(settings)
    provider = OpenAICompatibleProvider(settings)

    import app.services.agent.tools as agent_tools_module
    import app.services.rag.service as service_module

    real_provider_generate = provider.generate_structured
    real_retrieve = service_module.retrieve_sources
    real_ground = service_module.generate_grounded_answer
    real_faiss_load = FaissStore.load
    provider_calls: list[dict] = []
    captured_retrievals = []
    captured_grounding: list[dict] = []
    faiss_load_calls = 0

    def capture_provider_generate(**kwargs):
        started = perf_counter()
        schema_name = kwargs["schema"].__name__
        try:
            result = real_provider_generate(**kwargs)
        except Exception as exc:
            provider_calls.append(
                {
                    "schema": schema_name,
                    "success": False,
                    "model": settings.llm_structured_model_name,
                    "finish_reason": None,
                    "provider_content_nonempty": False,
                    "structured_value": None,
                    "error_type": type(exc).__name__,
                    "error_reason": getattr(exc, "reason", None),
                    "latency_ms": round((perf_counter() - started) * 1000),
                }
            )
            raise
        provider_calls.append(
            {
                "schema": schema_name,
                "success": True,
                "model": result.model,
                "finish_reason": result.finish_reason,
                "provider_content_nonempty": True,
                "structured_value": result.value.model_dump(mode="json"),
                "input_tokens": result.usage.input_tokens,
                "output_tokens": result.usage.output_tokens,
                "latency_ms": result.latency_ms,
            }
        )
        return result

    def capture_retrieval(**kwargs):
        result = real_retrieve(**kwargs)
        captured_retrievals.append(result)
        return result

    def capture_grounding(**kwargs):
        provider_call_index = len(provider_calls)
        result = real_ground(**kwargs)
        grounding_calls = [
            call
            for call in provider_calls[provider_call_index:]
            if call["schema"] == "RagGroundedAnswerDraft"
        ]
        captured_grounding.append(
            {"result": result, "provider_calls": grounding_calls}
        )
        return result

    def capture_faiss_load(self, **kwargs):
        nonlocal faiss_load_calls
        faiss_load_calls += 1
        return real_faiss_load(self, **kwargs)

    provider.generate_structured = capture_provider_generate
    service_module.retrieve_sources = capture_retrieval
    service_module.generate_grounded_answer = capture_grounding
    agent_tools_module.retrieve_sources = capture_retrieval
    agent_tools_module.generate_grounded_answer = capture_grounding
    FaissStore.load = capture_faiss_load

    report = {
        "question": QUESTION,
        "material_id": args.material_id,
        "database_copy": str(database),
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_structured_model_name,
        "embedding_model": settings.embedding_model_name,
        "rag_prompt_version": settings.rag_prompt_version,
        "runs": [],
    }

    runtime = AgentRuntime(settings)
    try:
        with session_factory() as db:
            material = db.get(Material, args.material_id)
            if material is None:
                raise SystemExit(f"Material does not exist: {args.material_id}")
            report["material"] = {
                "id": material.id,
                "title": material.title,
                "original_filename": material.original_filename,
                "ingestion_status": material.ingestion_status,
                "indexing_status": material.indexing_status,
                "chunk_count": material.chunk_count,
                "indexed_chunk_count": material.indexed_chunk_count,
            }
            citations_before = db.scalar(select(func.count()).select_from(RagCitation)) or 0
            messages_before = db.scalar(select(func.count()).select_from(RagMessage)) or 0
            service = RagConversationService(db, settings, embedder, provider)

            for run_number in range(1, args.runs + 1):
                conversation = service.create_conversation(
                    title=f"Final Fix 1R Acceptance {run_number}",
                    default_top_k=settings.rag_top_k_default,
                )
                retrieval_index = len(captured_retrievals)
                grounding_index = len(captured_grounding)
                faiss_before = faiss_load_calls
                embedding_loaded_before = getattr(embedder, "_model", None) is not None
                started = perf_counter()
                response = service.ask(
                    conversation_id=conversation.id,
                    question=QUESTION,
                    request_id=f"final-fix-1r-rag-{run_number:04d}",
                    top_k=settings.rag_top_k_default,
                    material_ids=[args.material_id],
                )
                total_latency_ms = round((perf_counter() - started) * 1000)
                retrieval = captured_retrievals[retrieval_index]
                grounding_capture = captured_grounding[grounding_index]
                evidence = grounding_evidence(grounding_capture)
                grounded = grounding_capture["result"]
                citations = response.assistant_message.citations
                sources = retrieval.sources
                source_by_label = {source.source_label: source for source in sources}
                allowed_ids = list(source_by_label)
                final_cited_ids = grounded.answer.cited_source_ids
                rendered_ids = CITATION_PATTERN.findall(response.assistant_message.content)
                unknown_source_ids = sorted(set(final_cited_ids) - set(allowed_ids))
                fabricated_source_ids = sorted(set(rendered_ids) - set(allowed_ids))
                persisted_citations = [citation_record(citation) for citation in citations]
                persistence_subset = all(
                    persisted_citation_is_retrieved(citation, source_by_label)
                    for citation in persisted_citations
                )
                forbidden_output_markers = [
                    marker
                    for marker in FORBIDDEN_OUTPUT_MARKERS
                    if marker.lower() in response.assistant_message.content.lower()
                ]
                run_record = {
                    "run": run_number,
                    "conversation_id": response.conversation_id,
                    "retrieval": {
                        "query": retrieval.query,
                        "resolved_material_ids": response.retrieval.resolved_material_ids,
                        "retrieved_count": retrieval.retrieved_count,
                        "filtered_count": retrieval.filtered_count,
                        "final_source_count": len(sources),
                        "candidate_count": retrieval.candidate_count,
                        "allowed_source_ids": allowed_ids,
                        "chunk_ids": [source.chunk_id for source in sources],
                        "material_ids": [source.material_id for source in sources],
                        "source_scores": [
                            {"source_label": source.source_label, "score": source.score}
                            for source in sources
                        ],
                        "sources": [source_record(source) for source in sources],
                        "duration_ms": retrieval.duration_ms,
                    },
                    "generation": evidence,
                    "deterministic_result": {
                        "final_answer_markdown": response.assistant_message.content,
                        "final_cited_source_ids": final_cited_ids,
                        "rendered_citation_ids": rendered_ids,
                        "citation_count": len(citations),
                        "unknown_source_ids": unknown_source_ids,
                        "fabricated_source_ids": fabricated_source_ids,
                        "forbidden_output_markers": forbidden_output_markers,
                        "answer_status": response.assistant_message.status,
                        "refusal_reason": response.assistant_message.refusal_reason,
                    },
                    "persistence": {
                        "citations": persisted_citations,
                        "all_persisted_citations_are_retrieved_sources": persistence_subset,
                    },
                    "latency": {
                        "temperature": (
                            "cold" if not embedding_loaded_before else "warm"
                        ),
                        "retrieval_duration_ms": retrieval.duration_ms,
                        "model_generation_latency_ms": evidence[
                            "model_generation_latency_ms"
                        ],
                        "total_latency_ms": total_latency_ms,
                        "embedding_loaded_before": embedding_loaded_before,
                        "embedding_loaded_after": getattr(embedder, "_model", None)
                        is not None,
                        "faiss_load_calls": faiss_load_calls - faiss_before,
                        "repair_added_llm_latency": evidence["repair_triggered"],
                    },
                }
                run_record["passed"] = (
                    run_record["generation"]["finish_reason"] == "stop"
                    and run_record["generation"]["provider_content_nonempty"]
                    and run_record["generation"]["structured_schema_validation"]
                    and run_record["generation"]["answerable"]
                    and run_record["generation"]["evidence_block_count"] >= 1
                    and all(
                        block_ids
                        for block_ids in run_record["generation"][
                            "validated_block_source_ids"
                        ]
                    )
                    and run_record["generation"]["repair_count"] <= 1
                    and run_record["deterministic_result"]["answer_status"]
                    == "completed"
                    and run_record["deterministic_result"]["citation_count"] >= 1
                    and not unknown_source_ids
                    and not fabricated_source_ids
                    and not forbidden_output_markers
                    and persistence_subset
                    and all(
                        citation["chunk_id"] is not None
                        and citation["material_id"] == args.material_id
                        for citation in persisted_citations
                    )
                )
                report["runs"].append(run_record)

            agent_retrieval_index = len(captured_retrievals)
            agent_grounding_index = len(captured_grounding)
            agent_provider_index = len(provider_calls)
            agent_started = perf_counter()
            agent_service = AgentService(
                db,
                settings,
                embedder,
                provider,
                runtime.checkpointer,
            )
            agent_conversation = agent_service.create_conversation(
                "Final Fix 1R Agent Acceptance",
                AgentConversationContext(
                    context_type="material", context_id=args.material_id
                ),
            )
            agent_input = (
                f"{QUESTION}{CONTEXT_MARKER}\nmaterial_ids=[{args.material_id}]"
            )
            agent_run = agent_service.start_run(
                agent_conversation.id,
                agent_input,
                "final-fix-1r-agent-0001",
            )
            agent_total_latency_ms = round((perf_counter() - agent_started) * 1000)
            agent_retrievals = captured_retrievals[agent_retrieval_index:]
            agent_groundings = captured_grounding[agent_grounding_index:]
            agent_citations = agent_run.citations
            agent_forbidden_output_markers = [
                marker
                for marker in FORBIDDEN_OUTPUT_MARKERS
                if marker.lower() in (agent_run.final_answer or "").lower()
            ]
            agent_tool_names = [call.tool_name for call in agent_run.tool_calls]
            agent_grounding_record = (
                grounding_evidence(agent_groundings[0]) if agent_groundings else None
            )
            report["agent_answer_materials"] = {
                "conversation_id": agent_run.conversation_id,
                "run_id": agent_run.id,
                "input": agent_input,
                "visible_question": QUESTION,
                "conversation_context": agent_conversation.context.model_dump(mode="json"),
                "intent": agent_run.intent,
                "status": agent_run.status,
                "error_code": agent_run.error_code,
                "final_answer": agent_run.final_answer,
                "citation_count": len(agent_citations),
                "citations": agent_citations,
                "citation_source_ids": [item["source_label"] for item in agent_citations],
                "citation_chunk_ids": [item["chunk_id"] for item in agent_citations],
                "citation_material_ids": [item["material_id"] for item in agent_citations],
                "tool_names": agent_tool_names,
                "shared_generate_grounded_answer_seam_used": len(agent_groundings) == 1,
                "grounding": agent_grounding_record,
                "retrievals": [
                    {
                        "query": retrieval.query,
                        "allowed_source_ids": [
                            source.source_label for source in retrieval.sources
                        ],
                        "chunk_ids": [source.chunk_id for source in retrieval.sources],
                        "material_ids": [
                            source.material_id for source in retrieval.sources
                        ],
                        "source_scores": [
                            {"source_label": source.source_label, "score": source.score}
                            for source in retrieval.sources
                        ],
                        "retrieved_count": retrieval.retrieved_count,
                        "filtered_count": retrieval.filtered_count,
                        "final_source_count": len(retrieval.sources),
                        "duration_ms": retrieval.duration_ms,
                    }
                    for retrieval in agent_retrievals
                ],
                "provider_calls": provider_calls[agent_provider_index:],
                "performance": agent_run.performance,
                "total_latency_ms": agent_total_latency_ms,
                "forbidden_output_markers": agent_forbidden_output_markers,
            }
            report["agent_answer_materials"]["passed"] = (
                agent_run.intent == "answer_materials"
                and agent_run.status == "completed"
                and agent_run.error_code is None
                and "answer_from_materials" in agent_tool_names
                and len(agent_groundings) == 1
                and bool((agent_run.final_answer or "").strip())
                and len(agent_citations) >= 1
                and all(
                    item["chunk_id"] is not None
                    and item["material_id"] == args.material_id
                    for item in agent_citations
                )
                and not agent_forbidden_output_markers
                and agent_grounding_record is not None
                and agent_grounding_record["repair_count"] <= 1
            )
            report["database_evidence"] = {
                "rag_messages_before": messages_before,
                "rag_messages_after": db.scalar(
                    select(func.count()).select_from(RagMessage)
                )
                or 0,
                "rag_citations_before": citations_before,
                "rag_citations_after": db.scalar(
                    select(func.count()).select_from(RagCitation)
                )
                or 0,
            }
    finally:
        runtime.close()
        engine.dispose()

    report["acceptance_passed"] = (
        len(report["runs"]) == args.runs
        and all(run["passed"] for run in report["runs"])
        and report["agent_answer_materials"]["passed"]
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["acceptance_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
