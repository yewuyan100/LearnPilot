# LearnPilot RAG Real-world Baseline Failure Analysis V1

## 1. Analysis identity

Analysis ID: `learnpilot-rag-real-world-baseline-failure-analysis-v1`; frozen baseline run: `20260814T052007Z-593cd2ac`.

## 2. Frozen baseline binding

- Gold: `33a0b69901fa47e3fe45be0277228cd4a5519fe780fe5b9d2c52b1bfe614927a`
- Freeze manifest: `d979079be4eb901a825ab29414dd7b5124d030182e09b55eea1e93749c12a5c2`
- Corpus manifest: `6f67d510cd35197f107400d33033972c0c3c84478174e4991e491f6c8e4ab563`
- Raw baseline: `bf718aed08e226149c9310cbf20bf25c403708217e2908789120178ac5574e28`
- Frozen semantic review: `671fe1a484dd6ff8986b34c0ebf0826f274bbb9ed6dda404f18ad0a2bd60a176`
- Protected identities and all 15 production-code files match the baseline binding.

## 3. Semantic review methodology

All 104 `SEMANTIC_REVIEW` claims were judged against the frozen Gold claim, frozen answer, actual selected context, citations, and project-owned frozen corpus only. Verdicts were frozen and detached-hashed before root cause or addressability was computed. No lexical proxy or model call was used.

## 4. 104 semantic claim verdicts summary

- Supported: 63
- Partially supported: 15
- Unsupported: 26
- Ambiguous: 0

## 5. Combined 132-claim result

Final reviewed claims: **88 pass / 15 partial / 29 fail** out of 132. Machine deterministic result remains 24/28; manual review changes only the MLDR structured-exact false negative, producing 25/28 reviewed deterministic pass.

| Evaluation mode | Claims | Pass | Partial | Fail |
|---|---:|---:|---:|---:|
| `ANSWERABILITY_ONLY` | 10 | 10 | 0 | 0 |
| `IDENTIFIER_EXACT` | 5 | 5 | 0 | 0 |
| `NUMERIC_EXACT` | 7 | 5 | 0 | 2 |
| `SEMANTIC_REVIEW` | 104 | 63 | 15 | 26 |
| `STRUCTURED_EXACT` | 6 | 5 | 0 | 1 |

## 6. 72-case reviewed result

- FULL_PASS: 37
- PARTIAL_PASS: 13
- FAIL: 0
- CORRECT_REFUSAL: 10
- INCORRECT_REFUSAL: 12

## 7. Citation semantic result

All 97 returned citations were reviewed: 91 support, 2 partial, 0 unsupported, and 4 unnecessary. There are 26 missing required evidence-group citation obligations. Structural validity remains 97/97 and is reported separately from semantic support.

## 8. Root-cause taxonomy

Attribution is upstream-first: retrieval → selection → answerability → generation → multi-document synthesis → citation → eval/mapping. Every case has exactly one primary root cause; secondary signals do not add to totals.

## 9. Exact root-cause distribution

| Primary root cause | Cases |
|---|---:|
| `ANSWERABILITY_FALSE_NEGATIVE` | 3 |
| `CITATION_ONLY_FAILURE` | 2 |
| `EVAL_MAPPING_DIAGNOSTIC` | 12 |
| `GENERATION_OMISSION` | 3 |
| `NO_FAILURE` | 33 |
| `RETRIEVAL_MISS` | 9 |
| `SELECTION_DIVERSITY_MISS` | 8 |
| `SELECTION_RANKING_MISS` | 2 |

## 10. Retrieval failures

- `rw-gold-v1-single-dependency-defaults` — The candidate pool contains a boundary fragment stating limit=100 but no candidate contains the required skip=0 fact; the selected context is therefore insufficient before the model refuses.
- `rw-gold-v1-multi-backend-control` — The selected/candidate pool covers async handling and generic dependencies, but no candidate contains the required authentication/authorization subdependency semantics or the HTTPException immediate-client-error passage.
- `rw-gold-v1-multi-error-observability` — The OpenTelemetry status passage is selected, but the candidate pool lacks the HTTPException raise/terminate passage and supplies only generic error-handler/client-range fragments, leaving the first claim under-supported.
- `rw-gold-v1-multi-rag-tracing` — This is the sole document-group candidate miss: required Ragas workflow groups are absent from all 18 candidates, while only OpenTelemetry trace material is selected, so the refusal is upstream of answerability.
- `rw-gold-v1-multi-retrieval-eval` — Faiss and context-precision roles are present, but no candidate contains the required Ragas data-collection record that supplies retrieved_contexts for each user_input; selected evaluation context is therefore incomplete.
- `rw-gold-v1-stress-cross-agent-api-replay` — Node-restart evidence is selected, but no candidate contains the non-idempotent side-effect mitigation or HTTPException client-boundary passage required to complete the cross-topic answer.
- `rw-gold-v1-stress-cross-embedding-api-concurrency` — BGE use_fp16 and the blocking-library half of FastAPI guidance are selected, but the runtime async chunk begins after the await-capable branch; no candidate contains the missing await-call obligation.
- `rw-gold-v1-stress-cross-persistence-tracing` — Generic persistence and span-link context are selected, but no candidate distinguishes a persistent checkpointer from an in-memory saver across process restart, leaving the first claim only partially supported.
- `rw-gold-v1-stress-cross-retrieval-evaluation` — Selected context contains partial hybrid, Faiss trade-off, and score-example fragments, but candidates omit the full BGE hybrid-plus-reranking and context-precision definition obligations; refusal is upstream.

`rw-gold-v1-multi-rag-tracing` is the sole document-group candidate miss; the other retrieval misses are claim-required evidence/chunk misses inside otherwise retrieved document groups.

## 11. Selection/ranking failures

- `rw-gold-v1-semantic-deps-automatic` — The exact dependency-call chunk (candidate rank 7) is present but diversity-deferred; selected chunks explain injection generally but omit the explicit pass-the-callable-to-Depends obligation.
- `rw-gold-v1-long-bge-training` — The required BGE-M3 training passage is candidate rank 15 but diversity-deferred; the six selected chunks cover capabilities and usage rather than the training obligations, so the refusal has an upstream selection cause.
- `rw-gold-v1-long-deps-hierarchy` — Hierarchy/OpenAPI evidence exists in candidates, but the semantically complete hierarchy and OpenAPI chunks at ranks 7, 12, and 14 are diversity-deferred; the selected boundary-mapped chunk covers only the OpenAPI half.
- `rw-gold-v1-long-interrupt-static` — The static-interrupt and runtime-configuration anchors are candidates at ranks 10, 13, and 17 but are diversity-deferred; the selected boundary fragment only exposes debugging use, causing two obligations to be omitted.
- `rw-gold-v1-long-otel-links` — The complete span-link/status passage is present at candidate ranks 4 and 5 but diversity-deferred; selected S1 supports causal non-hierarchical association but not the optional-link qualification.
- `rw-gold-v1-multi-eval-stack` — Workflow fields are available through a selected boundary fragment, but the reference-based and without-reference context-precision examples are candidates at ranks 10-13 and diversity-deferred; selected context is incomplete before refusal.
- `rw-gold-v1-multi-hybrid-index` — The BGE pipeline recommendation is candidate rank 4 but diversity-deferred after three BGE chunks are chosen; selected context supports retrieval modes and Faiss but omits hybrid-plus-reranking guidance.
- `rw-gold-v1-disambig-interrupt-static` — The static-breakpoint and runtime-static chunks are candidates at ranks 13 and 14 but diversity-deferred; final context contains dynamic interrupt material instead, so refusal is selection-driven.

- `rw-gold-v1-disambig-fastapi-async-deps` — The dependency mixing rule is selected, but the endpoint-selection TLDR passage is candidate rank 12 and does not enter final context; the answer consequently omits thread-pool behavior.
- `rw-gold-v1-disambig-ragas-metrics` — The context-precision definition is selected, but the workflow construction passage is candidate rank 15 and excluded; selected S6 only describes collecting fields, so EvaluationDataset construction is omitted.

No threshold, dedup, or context-budget primary miss is verified.

## 12. Answerability failures

| Original false-refusal case | Final primary attribution |
|---|---|
| `rw-gold-v1-single-dependency-defaults` | `RETRIEVAL_MISS` |
| `rw-gold-v1-long-bge-score-mix` | `ANSWERABILITY_FALSE_NEGATIVE` |
| `rw-gold-v1-long-bge-training` | `SELECTION_DIVERSITY_MISS` |
| `rw-gold-v1-long-deps-hierarchy` | `SELECTION_DIVERSITY_MISS` |
| `rw-gold-v1-multi-eval-stack` | `SELECTION_DIVERSITY_MISS` |
| `rw-gold-v1-multi-rag-tracing` | `RETRIEVAL_MISS` |
| `rw-gold-v1-multi-retrieval-eval` | `RETRIEVAL_MISS` |
| `rw-gold-v1-disambig-agent-persist-interrupt` | `ANSWERABILITY_FALSE_NEGATIVE` |
| `rw-gold-v1-disambig-fastapi-errors` | `ANSWERABILITY_FALSE_NEGATIVE` |
| `rw-gold-v1-disambig-interrupt-static` | `SELECTION_DIVERSITY_MISS` |
| `rw-gold-v1-stress-cross-agent-api-replay` | `RETRIEVAL_MISS` |
| `rw-gold-v1-stress-cross-retrieval-evaluation` | `RETRIEVAL_MISS` |

Only 3 of the 12 false-refusal signals remain true answerability false negatives after upstream evidence sufficiency is checked.

## 13. Generation failures

- `rw-gold-v1-long-interrupt-validation` — Selected S1 and S6 provide the once-per-node/state/conditional-edge pattern and unstable interrupt-order warning; the answer uses the loop guidance but omits question-in-state and nondeterministic-order details.
- `rw-gold-v1-long-langgraph-positioning` — Both positioning anchors are selected at ranks 1 and 2, but the answer stops at low-level infrastructure and does not explicitly state fine-grained control over workflow and state.
- `rw-gold-v1-stress-conflict-ragas-reference-mode` — ID-based, with-reference, and without-reference examples are all selected, but the answer names the variants without explicitly stating their comparison targets: reference contexts versus generated response.

No fact error, overclaim, or extraction-error primary cause is verified. The apparent MLDR structured-exact failure is an evaluator language-mapping false negative, not a generation error.

## 14. Multi-doc synthesis failures

None verified. The low aggregate performance for multi-document groups resolves upstream: missing evidence, selection loss, or false refusal occurs before a complete selected-evidence set can be synthesized. Dense candidate document coverage alone therefore overstates synthesis readiness.

## 15. Citation-only failures

- `rw-gold-v1-semantic-checkpointer-store` — The answer fulfills both semantic claims, but it cites only rw-agent-persistence and omits the required rw-agent-langgraph-overview source group and the two-document citation obligation.
- `rw-gold-v1-multi-agent-resume` — The answer correctly explains checkpointer persistence and thread_id resumption, but both citations resolve to rw-agent-interrupts; the required rw-agent-persistence source and two-document coverage are missing.

These answers are semantically correct; the missing required source is not double-counted as generation failure.

## 16. Eval/mapping diagnostic findings

- `rw-gold-v1-single-bge-shape` — The answer and citation recover both numeric facts from a selected same-document boundary chunk, while the diagnostic stable-anchor mapper reports no anchor; this is a mapping false negative.
- `rw-gold-v1-single-langgraph-js` — The selected LangGraph overview boundary fragment directly contains LangGraph.js and the answer is exact, but the stable anchor is not attached to that runtime chunk.
- `rw-gold-v1-semantic-context-order` — The selected context semantically contains the order-swap example and both claims pass, although one required stable anchor is not mapped to the runtime chunk.
- `rw-gold-v1-semantic-faiss-compression` — The cited selected Faiss passage contains compression and precision trade-off semantics, so the selected-anchor miss is a runtime-boundary mapping diagnostic.
- `rw-gold-v1-long-precision-nonllm` — The selected context and citation support the non-LLM context-precision claim despite the runtime chunk lacking the stable evidence ID.
- `rw-gold-v1-multi-agent-memory-hitl` — All three cross-source claims and citations are supported; the selected anchor deficit reflects boundary IDs rather than missing answer evidence.
- `rw-gold-v1-multi-async-dependency` — The answer correctly integrates async endpoint and dependency execution rules from selected boundary chunks even though diagnostic anchors do not map.
- `rw-gold-v1-disambig-agent-memory` — The answer correctly separates checkpointer, Store, and interrupts from selected text; absent anchor IDs are diagnostic only.
- `rw-gold-v1-disambig-bge-faiss` — The answer correctly distinguishes BGE-M3 and Faiss using selected semantic equivalents, while one stable anchor is not mapped to its runtime chunk.
- `rw-gold-v1-stress-deep-bge-mldr-comparison` — The Chinese answer explicitly states 13 languages plus test, validation, and training sets; the STRUCTURED_EXACT matcher fails only because it requires the English tokens.
- `rw-gold-v1-stress-deep-interrupt-side-effects` — The answer and citations fully cover replay and idempotent side-effect placement; the selected-anchor miss is boundary mapping.
- `rw-gold-v1-stress-conflict-fastapi-handler-type` — The answer correctly resolves the handler-type conflict and cites supporting text; the remaining selected-anchor deficit is diagnostic mapping.

Candidate anchor coverage is 59/72 and selected anchor coverage is 41/72. Of 31 selected-anchor misses, 18 correspond to verified upstream evidence/selection deficits; 13 are semantic-equivalent or boundary-mapping diagnostics. Conversely, one selected anchor pass (`stress-cross-embedding-api-concurrency`) masks a runtime boundary fragment that omits the first half of the anchored guidance. Anchor IDs are therefore diagnostics, not truth labels.

## 17. CORE/STRESS breakdown

CORE and STRESS counts, verdicts, and primary causes are recorded under `breakdowns.tier` in `root_cause_summary.json`; the same artifact contains all required topic, difficulty, and language breakdowns.

## 18. Case-type/topic/difficulty/language breakdown

| Case type | Cases | Full pass | Full-pass rate |
|---|---:|---:|---:|
| `cross_topic_multi_doc` | 4 | 0 | 0.00% |
| `deep_long_doc_localization` | 4 | 4 | 100.00% |
| `high_overlap_source_conflict` | 4 | 3 | 75.00% |
| `long_doc_localization` | 10 | 3 | 30.00% |
| `multi_doc_synthesis` | 10 | 4 | 40.00% |
| `semantic_paraphrase` | 10 | 9 | 90.00% |
| `single_doc_fact` | 10 | 9 | 90.00% |
| `source_disambiguation` | 10 | 5 | 50.00% |
| `unanswerable_near_boundary` | 10 | 0 | 0.00% |

Detailed topic, difficulty, and query-language tables are machine-readable in `root_cause_summary.json`.

## 19. Optimization Addressability Matrix

- Hybrid-addressable cases: 9
- Reranker-addressable cases: 10
- Generation-addressable cases: 3
- Answerability-addressable cases: 3
- Citation-addressable cases: 2
- Not-architecture-addressable / no-failure cases: 45

These are theoretical targets, not promises of improvement.

## 20. Ablation hypotheses

- `dense_only`: frozen control; no expected mutation.
- `hybrid`: targets the 9 candidate-evidence misses and should be judged on required evidence candidate coverage.
- `dense_rerank`: targets the 10 candidate-hit/selection-miss cases and should be judged on selected required-evidence coverage.
- `hybrid_rerank`: tests complementary recall plus ranking effects; no case is pre-labeled as requiring both, and the combined arm is not presumed best.

The exact frozen case lists and null hypothesis are in `ablation_hypotheses.json`.

## 21. Benchmark / raw result immutability

All protected hashes and production code hashes were revalidated before artifact construction and again by the test suite. Raw results, Gold, corpus, freeze manifest, and production RAG were not modified.

## 22. Tests

Focused joint regression passed **19/19** tests:

```text
python -m pytest backend/tests/test_rag_real_world_failure_analysis_v1.py backend/tests/test_rag_real_world_dense_only_baseline_v1.py -q
19 passed
```

The suite verifies 72/72 case coverage, 104/104 semantic reviews, 97/97 returned citations, 132 final claim statuses, exactly one root per case, root/addressability invariants, all protected hashes, artifact/code identities, and production-code identity.

## 23. Files created/modified

- `evals/rag_real_world_corpus/v1/failure_analysis_v1/semantic_review_decisions.py`
- `evals/rag_real_world_corpus/v1/failure_analysis_v1/freeze_semantic_reviews.py`
- `evals/rag_real_world_corpus/v1/failure_analysis_v1/analysis_decisions.py`
- `evals/rag_real_world_corpus/v1/failure_analysis_v1/build_failure_analysis_v1.py`
- `evals/rag_real_world_corpus/v1/failure_analysis_v1/semantic_claim_reviews.json`
- `evals/rag_real_world_corpus/v1/failure_analysis_v1/semantic_claim_reviews.schema.json`
- `evals/rag_real_world_corpus/v1/failure_analysis_v1/semantic_claim_reviews.sha256`
- `evals/rag_real_world_corpus/v1/failure_analysis_v1/citation_semantic_reviews.json`
- `evals/rag_real_world_corpus/v1/failure_analysis_v1/citation_semantic_reviews.schema.json`
- `evals/rag_real_world_corpus/v1/failure_analysis_v1/case_failure_analysis.json`
- `evals/rag_real_world_corpus/v1/failure_analysis_v1/case_failure_analysis.schema.json`
- `evals/rag_real_world_corpus/v1/failure_analysis_v1/root_cause_summary.json`
- `evals/rag_real_world_corpus/v1/failure_analysis_v1/optimization_addressability_matrix.json`
- `evals/rag_real_world_corpus/v1/failure_analysis_v1/ablation_hypotheses.json`
- `evals/rag_real_world_corpus/v1/failure_analysis_v1/failure_analysis_manifest.json`
- `evals/rag_real_world_corpus/v1/RAG_REAL_WORLD_BASELINE_FAILURE_ANALYSIS_V1_REPORT.md`
- `backend/tests/test_rag_real_world_failure_analysis_v1.py`

## 24. Explicit confirmation

```text
NO OPTIMIZATION PERFORMED
NO EXTERNAL LLM CALL
NO BASELINE RERUN
NO EMBEDDING EXECUTION
NO FAISS RETRIEVAL EXECUTION
NO PRODUCTION RAG ASK
```

```text
RAG_REAL_WORLD_BASELINE_FAILURE_ANALYSIS_V1 = COMPLETE
READY_FOR_ABLATION_DESIGN = YES
```
