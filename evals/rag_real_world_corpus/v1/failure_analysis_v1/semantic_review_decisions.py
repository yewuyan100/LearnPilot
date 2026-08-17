"""Human semantic-claim decisions for Real-world Dense-only Baseline V1.

This module is deliberately data-only.  It contains the evidence-based decisions
made from the frozen gold claim, the model answer, and the actually selected
project-owned context.  No model or retrieval code is invoked by importing it.
"""

from __future__ import annotations


def _decision(verdict: str, reason: str) -> dict[str, str]:
    return {"verdict": verdict, "review_reason": reason}


SEMANTIC_DECISIONS: dict[str, dict[str, str]] = {
    "rw-gold-v1-single-faiss-cosine-claim-01": _decision(
        "SUPPORTED",
        "The answer states that cosine similarity is a dot product after vector normalization, matching the cited Faiss passage and the full claim obligation.",
    ),
    "rw-gold-v1-single-persist-thread-id-claim-02": _decision(
        "SUPPORTED",
        "The answer recommends a UUID or deterministic hash as the thread identifier; this directly satisfies the claim even though its UUID4 example is merely one possible implementation.",
    ),
    "rw-gold-v1-semantic-bge-functions-claim-01": _decision(
        "SUPPORTED",
        "The answer names dense, sparse, and multi-vector retrieval, exactly covering the three BGE-M3 retrieval functions in the selected evidence.",
    ),
    "rw-gold-v1-semantic-checkpointer-store-claim-01": _decision(
        "SUPPORTED",
        "The answer attributes durable execution continuity, interruption/failure recovery, and memory continuity to the checkpointer, which covers the claim.",
    ),
    "rw-gold-v1-semantic-checkpointer-store-claim-02": _decision(
        "SUPPORTED",
        "The answer contrasts thread-scoped checkpoints with a Store used across threads for preferences and other shared memory, matching the evidence.",
    ),
    "rw-gold-v1-semantic-context-order-claim-01": _decision(
        "SUPPORTED",
        "The answer explains that placing relevant chunks earlier rewards the intended relevant context, which is the ordering effect required by the claim.",
    ),
    "rw-gold-v1-semantic-context-order-claim-02": _decision(
        "SUPPORTED",
        "The answer says an irrelevant chunk placed first changes the example score from approximately 1 to 0.5, matching the selected evaluation evidence.",
    ),
    "rw-gold-v1-semantic-deps-automatic-claim-01": _decision(
        "PARTIALLY_SUPPORTED",
        "The answer says to declare the dependency and not call it manually, but it does not explicitly say that the callable itself is passed to Depends without being invoked.",
    ),
    "rw-gold-v1-semantic-deps-automatic-claim-02": _decision(
        "SUPPORTED",
        "The answer states that FastAPI invokes the dependency with its parameters and injects the returned value, satisfying the automatic-execution claim.",
    ),
    "rw-gold-v1-semantic-error-raise-claim-01": _decision(
        "SUPPORTED",
        "The answer states that raising the exception stops the remaining path operation code, directly matching the claim.",
    ),
    "rw-gold-v1-semantic-error-raise-claim-02": _decision(
        "SUPPORTED",
        "The answer states that the resulting HTTP error is sent to the client, matching the cited FastAPI behavior.",
    ),
    "rw-gold-v1-semantic-faiss-compression-claim-01": _decision(
        "SUPPORTED",
        "The answer explains that a compressed Faiss index may store a compact representation instead of retaining the original vectors, covering the claim.",
    ),
    "rw-gold-v1-semantic-faiss-compression-claim-02": _decision(
        "SUPPORTED",
        "The answer identifies reduced search precision as the trade-off of compression, which is the required consequence.",
    ),
    "rw-gold-v1-semantic-fastapi-blocking-claim-01": _decision(
        "SUPPORTED",
        "The answer recommends a normal def path operation for a blocking library that has no await support, matching the selected FastAPI guidance.",
    ),
    "rw-gold-v1-semantic-fastapi-blocking-claim-02": _decision(
        "SUPPORTED",
        "The answer explains that normal def handlers run in a thread pool and may be mixed with async def handlers, covering both parts of the claim.",
    ),
    "rw-gold-v1-semantic-interrupt-replay-claim-01": _decision(
        "SUPPORTED",
        "The answer explains that resumption replays the node from its beginning rather than continuing at the interrupt line, exactly matching the claim.",
    ),
    "rw-gold-v1-semantic-ragas-data-claim-02": _decision(
        "SUPPORTED",
        "The answer maps the prepared gold answer to the Ragas reference field, satisfying this claim obligation.",
    ),
    "rw-gold-v1-semantic-trace-correlation-claim-01": _decision(
        "SUPPORTED",
        "The answer recommends a trace or correlation identifier to connect otherwise independent request traces, which is the required technique.",
    ),
    "rw-gold-v1-long-async-threadpool-claim-01": _decision(
        "SUPPORTED",
        "The answer says normal def path operations and dependencies execute in an external thread pool instead of being awaited directly, matching the evidence.",
    ),
    "rw-gold-v1-long-async-threadpool-claim-02": _decision(
        "SUPPORTED",
        "The answer correctly distinguishes utility functions called directly by application code from FastAPI-managed path operations and dependencies.",
    ),
    "rw-gold-v1-long-async-threadpool-claim-03": _decision(
        "SUPPORTED",
        "The answer states that directly called utility functions are not automatically moved to a thread pool and must be awaited when async, covering the claim.",
    ),
    "rw-gold-v1-long-bge-query-instruction-claim-01": _decision(
        "SUPPORTED",
        "The answer states that query-side instructions are unnecessary for BGE-M3, exactly matching the selected model guidance.",
    ),
    "rw-gold-v1-long-bge-score-mix-claim-01": _decision(
        "UNSUPPORTED",
        "The answer refuses for insufficient information even though the selected BGE-M3 context contains the required dense/sparse score-weighting guidance; it never states the claim.",
    ),
    "rw-gold-v1-long-bge-training-claim-01": _decision(
        "UNSUPPORTED",
        "The answer refuses and never states that self-knowledge distillation integrates multiple relevance signals into training.",
    ),
    "rw-gold-v1-long-bge-training-claim-02": _decision(
        "UNSUPPORTED",
        "The answer refuses and does not describe the unified fine-tuning of dense, sparse, and multi-vector retrieval modes required by the claim.",
    ),
    "rw-gold-v1-long-bge-training-claim-03": _decision(
        "UNSUPPORTED",
        "The answer refuses and therefore omits the claim about BGE-M3's long-document and multilingual capability.",
    ),
    "rw-gold-v1-long-deps-hierarchy-claim-01": _decision(
        "UNSUPPORTED",
        "The answer refuses despite selected FastAPI context describing hierarchical dependencies; it provides no dependency-tree explanation.",
    ),
    "rw-gold-v1-long-deps-hierarchy-claim-02": _decision(
        "UNSUPPORTED",
        "The answer refuses and never states that dependency requirements and schemas are integrated into OpenAPI documentation.",
    ),
    "rw-gold-v1-long-interrupt-static-claim-01": _decision(
        "PARTIALLY_SUPPORTED",
        "The answer identifies static interrupts as debugging breakpoints, but it does not state the documented caution that they are not recommended for human-in-the-loop workflows.",
    ),
    "rw-gold-v1-long-interrupt-static-claim-02": _decision(
        "SUPPORTED",
        "The answer correctly places static interrupts in graph compilation through interrupt_before or interrupt_after options.",
    ),
    "rw-gold-v1-long-interrupt-static-claim-03": _decision(
        "UNSUPPORTED",
        "The answer does not mention the alternative per-invocation runtime configuration, so this distinct configuration claim is absent.",
    ),
    "rw-gold-v1-long-interrupt-validation-claim-01": _decision(
        "PARTIALLY_SUPPORTED",
        "The answer says to call interrupt once per node and describes state-related validation risk, but it omits the specific recommendation to store the question in graph state.",
    ),
    "rw-gold-v1-long-interrupt-validation-claim-02": _decision(
        "SUPPORTED",
        "The answer states that the input order must remain stable across replay, directly satisfying the claim.",
    ),
    "rw-gold-v1-long-interrupt-validation-claim-03": _decision(
        "PARTIALLY_SUPPORTED",
        "The answer explains replay/loop risk from multiple interrupts but does not explain the evidence's specific nondeterministic ordering problem.",
    ),
    "rw-gold-v1-long-langgraph-positioning-claim-01": _decision(
        "SUPPORTED",
        "The answer identifies LangGraph as a low-level orchestration framework/runtime for long-running, stateful agents, matching the claim.",
    ),
    "rw-gold-v1-long-langgraph-positioning-claim-02": _decision(
        "PARTIALLY_SUPPORTED",
        "The answer says LangGraph provides low-level infrastructure to build and manage agents, but it does not explicitly state the promised fine-grained control over workflow and state.",
    ),
    "rw-gold-v1-long-otel-links-claim-01": _decision(
        "SUPPORTED",
        "The answer explains that span links associate causally related spans without imposing a parent-child hierarchy, covering the core claim.",
    ),
    "rw-gold-v1-long-otel-links-claim-02": _decision(
        "PARTIALLY_SUPPORTED",
        "The answer mentions cross-trace association and lack of parent-child structure but omits that links are optional associations rather than required structure.",
    ),
    "rw-gold-v1-long-precision-nonllm-claim-01": _decision(
        "SUPPORTED",
        "The answer describes a non-LLM similarity scorer for the response/reference comparison; the Levenshtein example is compatible with, and not narrower than, the claim.",
    ),
    "rw-gold-v1-multi-agent-memory-hitl-claim-01": _decision(
        "SUPPORTED",
        "The answer assigns thread-level durable state and execution continuity to the checkpointer, matching the first required source.",
    ),
    "rw-gold-v1-multi-agent-memory-hitl-claim-02": _decision(
        "SUPPORTED",
        "The answer assigns cross-thread user memories and preferences to the Store, satisfying the second source-specific claim.",
    ),
    "rw-gold-v1-multi-agent-memory-hitl-claim-03": _decision(
        "SUPPORTED",
        "The answer explains that interrupt pauses execution and returns payload, then Command(resume=...) resumes the same thread, covering the human-in-the-loop mechanism.",
    ),
    "rw-gold-v1-multi-agent-resume-claim-01": _decision(
        "SUPPORTED",
        "The answer states that the same thread_id must be reused to resume the interrupted execution, matching the claim.",
    ),
    "rw-gold-v1-multi-agent-resume-claim-02": _decision(
        "SUPPORTED",
        "The answer describes passing the human response through Command(resume=...), satisfying the resume-input claim.",
    ),
    "rw-gold-v1-multi-async-dependency-claim-01": _decision(
        "SUPPORTED",
        "The answer correctly recommends async def when the third-party operation is awaitable, matching the first selected document.",
    ),
    "rw-gold-v1-multi-async-dependency-claim-02": _decision(
        "SUPPORTED",
        "The answer explains that FastAPI resolves declared dependencies and injects their results, covering the dependency-injection source.",
    ),
    "rw-gold-v1-multi-backend-control-claim-01": _decision(
        "SUPPORTED",
        "The answer correctly states that a blocking library with no await support belongs in a normal def path operation so FastAPI can run it in a thread pool.",
    ),
    "rw-gold-v1-multi-backend-control-claim-02": _decision(
        "PARTIALLY_SUPPORTED",
        "The answer mentions shared dependencies and automatic invocation but omits their use for authentication/authorization and subdependency modeling.",
    ),
    "rw-gold-v1-multi-backend-control-claim-03": _decision(
        "UNSUPPORTED",
        "The answer discusses customizing RequestValidationError handling rather than raising HTTPException to immediately terminate and return a client error.",
    ),
    "rw-gold-v1-multi-error-observability-claim-01": _decision(
        "PARTIALLY_SUPPORTED",
        "The answer describes a client-visible error response and status but does not explicitly connect it to raising HTTPException and immediate path termination.",
    ),
    "rw-gold-v1-multi-error-observability-claim-02": _decision(
        "PARTIALLY_SUPPORTED",
        "The answer says successful spans need no explicit success status and failures should reflect outcomes, but it omits the documented Error versus Unset status distinction.",
    ),
    "rw-gold-v1-multi-eval-stack-claim-01": _decision(
        "UNSUPPORTED",
        "The answer refuses and therefore does not state the required Ragas EvaluationDataset construction step.",
    ),
    "rw-gold-v1-multi-eval-stack-claim-02": _decision(
        "UNSUPPORTED",
        "The answer refuses and provides no span-link mechanism for connecting independent traces.",
    ),
    "rw-gold-v1-multi-eval-stack-claim-03": _decision(
        "UNSUPPORTED",
        "The answer refuses and never identifies the non-LLM string-similarity metric required by the third source.",
    ),
    "rw-gold-v1-multi-faiss-context-precision-claim-01": _decision(
        "SUPPORTED",
        "The answer describes Faiss as an efficient dense-vector similarity search/indexing component, satisfying the retrieval-infrastructure claim.",
    ),
    "rw-gold-v1-multi-faiss-context-precision-claim-02": _decision(
        "SUPPORTED",
        "The answer states that context precision measures whether relevant retrieved chunks are ranked ahead of irrelevant ones, matching the metric definition.",
    ),
    "rw-gold-v1-multi-faiss-context-precision-claim-03": _decision(
        "SUPPORTED",
        "The answer explains that earlier irrelevant context reduces context precision, completing the multi-document synthesis.",
    ),
    "rw-gold-v1-multi-hybrid-index-claim-01": _decision(
        "PARTIALLY_SUPPORTED",
        "The answer lists BGE-M3's dense, sparse, and multi-vector outputs but omits the source's explicit hybrid-retrieval and reranking recommendation.",
    ),
    "rw-gold-v1-multi-hybrid-index-claim-02": _decision(
        "SUPPORTED",
        "The answer describes Faiss as the dense-vector index/search component, correctly assigning its role in the combined architecture.",
    ),
    "rw-gold-v1-multi-rag-tracing-claim-01": _decision(
        "UNSUPPORTED",
        "The answer refuses and does not describe building the Ragas EvaluationDataset from query, response, contexts, and reference data.",
    ),
    "rw-gold-v1-multi-rag-tracing-claim-02": _decision(
        "UNSUPPORTED",
        "The answer refuses and therefore omits span links for associating independent traces.",
    ),
    "rw-gold-v1-multi-retrieval-eval-claim-01": _decision(
        "UNSUPPORTED",
        "The answer refuses and gives no BGE-M3 multi-functionality or hybrid retrieval role.",
    ),
    "rw-gold-v1-multi-retrieval-eval-claim-02": _decision(
        "UNSUPPORTED",
        "The answer refuses and never states Faiss's dense-vector similarity-search role.",
    ),
    "rw-gold-v1-multi-retrieval-eval-claim-03": _decision(
        "UNSUPPORTED",
        "The answer refuses and does not describe Ragas context precision as evaluating the ordering of relevant retrieved chunks.",
    ),
    "rw-gold-v1-disambig-agent-memory-claim-01": _decision(
        "SUPPORTED",
        "The answer correctly identifies the checkpointer as thread-scoped persistence for agent execution state.",
    ),
    "rw-gold-v1-disambig-agent-memory-claim-02": _decision(
        "SUPPORTED",
        "The answer correctly identifies the Store as cross-thread memory for user-level data and preferences.",
    ),
    "rw-gold-v1-disambig-agent-persist-interrupt-claim-01": _decision(
        "UNSUPPORTED",
        "The answer refuses and gives no explanation of checkpointer-based durable thread state.",
    ),
    "rw-gold-v1-disambig-agent-persist-interrupt-claim-02": _decision(
        "UNSUPPORTED",
        "The answer refuses and omits interrupt/Command(resume=...) human-in-the-loop behavior.",
    ),
    "rw-gold-v1-disambig-bge-faiss-claim-01": _decision(
        "SUPPORTED",
        "The answer assigns embedding representations for dense/sparse/multi-vector retrieval to BGE-M3, matching the claim.",
    ),
    "rw-gold-v1-disambig-bge-faiss-claim-02": _decision(
        "SUPPORTED",
        "The answer assigns dense-vector indexing and similarity search to Faiss, correctly distinguishing the second source.",
    ),
    "rw-gold-v1-disambig-bge-long-claim-01": _decision(
        "SUPPORTED",
        "The answer identifies 8192-token long-input support as the relevant BGE-M3 capability, directly matching the claim.",
    ),
    "rw-gold-v1-disambig-fastapi-async-deps-claim-01": _decision(
        "PARTIALLY_SUPPORTED",
        "The answer distinguishes async def for awaitable work from normal def for blocking work, but does not explain the associated thread-pool execution behavior.",
    ),
    "rw-gold-v1-disambig-fastapi-async-deps-claim-02": _decision(
        "SUPPORTED",
        "The answer explains that FastAPI automatically executes declared dependencies and injects their results, satisfying the second claim.",
    ),
    "rw-gold-v1-disambig-fastapi-errors-claim-01": _decision(
        "UNSUPPORTED",
        "The answer refuses and does not distinguish HTTPException from RequestValidationError handling.",
    ),
    "rw-gold-v1-disambig-fastapi-exceptions-claim-01": _decision(
        "SUPPORTED",
        "The answer describes HTTPException as an application-raised path-operation error that terminates normal execution and returns an HTTP response.",
    ),
    "rw-gold-v1-disambig-fastapi-exceptions-claim-02": _decision(
        "SUPPORTED",
        "The answer describes RequestValidationError as FastAPI's request-validation exception and notes that its handler can be overridden, matching the claim.",
    ),
    "rw-gold-v1-disambig-interrupt-static-claim-01": _decision(
        "UNSUPPORTED",
        "The answer refuses and provides no distinction between dynamic interrupt-based human-in-the-loop flow and static debugging breakpoints.",
    ),
    "rw-gold-v1-disambig-ragas-metrics-claim-01": _decision(
        "PARTIALLY_SUPPORTED",
        "The answer lists the needed query/response/context/reference fields but does not explicitly describe constructing an EvaluationDataset from them.",
    ),
    "rw-gold-v1-disambig-ragas-metrics-claim-02": _decision(
        "SUPPORTED",
        "The answer correctly defines context precision as rewarding relevant chunks that appear before irrelevant ones.",
    ),
    "rw-gold-v1-disambig-ragas-otel-claim-01": _decision(
        "SUPPORTED",
        "The answer assigns offline RAG-quality evaluation to Ragas, accurately distinguishing the evaluation system.",
    ),
    "rw-gold-v1-disambig-ragas-otel-claim-02": _decision(
        "SUPPORTED",
        "The answer assigns runtime trace association without parent-child hierarchy to OpenTelemetry span links, matching the observability source.",
    ),
    "rw-gold-v1-stress-deep-async-call-kinds-claim-01": _decision(
        "SUPPORTED",
        "The answer correctly states that FastAPI directly awaits async def path operations and dependencies.",
    ),
    "rw-gold-v1-stress-deep-async-call-kinds-claim-02": _decision(
        "SUPPORTED",
        "The answer correctly states that FastAPI runs normal def path operations and dependencies in an external thread pool.",
    ),
    "rw-gold-v1-stress-deep-async-call-kinds-claim-03": _decision(
        "SUPPORTED",
        "The answer correctly distinguishes directly called helper functions as application-managed calls with no automatic FastAPI thread-pool offload.",
    ),
    "rw-gold-v1-stress-deep-bge-mldr-comparison-claim-02": _decision(
        "SUPPORTED",
        "The answer reports the specified BGE-M3 versus BM25 average nDCG@10 comparison from the selected MLDR evidence.",
    ),
    "rw-gold-v1-stress-deep-interrupt-side-effects-claim-01": _decision(
        "SUPPORTED",
        "The answer explains that resume restarts the interrupted node from the beginning, matching the replay claim.",
    ),
    "rw-gold-v1-stress-deep-interrupt-side-effects-claim-02": _decision(
        "SUPPORTED",
        "The answer recommends moving non-idempotent side effects after interrupt or into a separate node, satisfying the safety guidance.",
    ),
    "rw-gold-v1-stress-deep-precision-id-versus-content-claim-01": _decision(
        "SUPPORTED",
        "The answer identifies the ID-based context-precision variant as comparing retrieved and reference context identifiers.",
    ),
    "rw-gold-v1-stress-deep-precision-id-versus-content-claim-02": _decision(
        "SUPPORTED",
        "The answer identifies the content-based non-LLM variant as comparing retrieved and reference context text with a distance measure.",
    ),
    "rw-gold-v1-stress-cross-agent-api-replay-claim-01": _decision(
        "UNSUPPORTED",
        "The answer refuses and provides no checkpointer/thread_id durability requirement.",
    ),
    "rw-gold-v1-stress-cross-agent-api-replay-claim-02": _decision(
        "UNSUPPORTED",
        "The answer refuses and omits the node-replay and non-idempotent side-effect constraint.",
    ),
    "rw-gold-v1-stress-cross-agent-api-replay-claim-03": _decision(
        "UNSUPPORTED",
        "The answer refuses and does not state the normal def/thread-pool rule for a blocking synchronous API call.",
    ),
    "rw-gold-v1-stress-cross-embedding-api-concurrency-claim-01": _decision(
        "SUPPORTED",
        "The answer assigns dense/sparse/multi-vector representations and long-input support to BGE-M3, covering the embedding-side claim.",
    ),
    "rw-gold-v1-stress-cross-embedding-api-concurrency-claim-02": _decision(
        "PARTIALLY_SUPPORTED",
        "The answer covers normal def for blocking operations but omits, and does not clearly contrast, async def for awaitable third-party calls.",
    ),
    "rw-gold-v1-stress-cross-persistence-tracing-claim-01": _decision(
        "PARTIALLY_SUPPORTED",
        "The answer says a checkpointer can preserve state across restarts but fails to distinguish a persistent checkpointer from an in-memory implementation.",
    ),
    "rw-gold-v1-stress-cross-persistence-tracing-claim-02": _decision(
        "SUPPORTED",
        "The answer accurately describes span links as associating spans across traces without imposing a parent-child hierarchy.",
    ),
    "rw-gold-v1-stress-cross-retrieval-evaluation-claim-01": _decision(
        "UNSUPPORTED",
        "The answer refuses and gives no BGE-M3 hybrid-retrieval role.",
    ),
    "rw-gold-v1-stress-cross-retrieval-evaluation-claim-02": _decision(
        "UNSUPPORTED",
        "The answer refuses and does not identify Faiss as the dense-vector index/search component.",
    ),
    "rw-gold-v1-stress-cross-retrieval-evaluation-claim-03": _decision(
        "UNSUPPORTED",
        "The answer refuses and provides no Ragas context-precision evaluation definition.",
    ),
    "rw-gold-v1-stress-conflict-bge-faiss-compression-claim-01": _decision(
        "SUPPORTED",
        "The answer correctly rejects the premise that BGE-M3 determines whether a Faiss index retains original vectors and assigns that property to the Faiss index type.",
    ),
    "rw-gold-v1-stress-conflict-fastapi-handler-type-claim-01": _decision(
        "SUPPORTED",
        "The answer states that a blocking non-awaitable library belongs in normal def, matching the controlling FastAPI guidance.",
    ),
    "rw-gold-v1-stress-conflict-fastapi-handler-type-claim-02": _decision(
        "SUPPORTED",
        "The answer explains that FastAPI moves normal def path operations to a thread pool, satisfying the concurrency rationale.",
    ),
    "rw-gold-v1-stress-conflict-interrupt-persistence-resume-claim-01": _decision(
        "SUPPORTED",
        "The answer correctly combines a durable checkpointer, reuse of the same thread_id, and Command(resume=...) as the safe resume contract.",
    ),
    "rw-gold-v1-stress-conflict-ragas-reference-mode-claim-01": _decision(
        "PARTIALLY_SUPPORTED",
        "The answer distinguishes ID-based and content-based variants, but it does not explicitly state that they compare against reference contexts rather than the generated response.",
    ),
}


ALLOWED_VERDICTS = {
    "SUPPORTED",
    "PARTIALLY_SUPPORTED",
    "UNSUPPORTED",
    "AMBIGUOUS",
}

