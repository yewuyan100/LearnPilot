# LearnPilot RAG — Real-world Dense-only Baseline V1

## 1. Baseline identity

`RAG_REAL_WORLD_DENSE_ONLY_BASELINE_V1 = COMPLETE`

- Baseline: `learnpilot-rag-real-world-dense-only-baseline-v1`
- Run: `20260814T052007Z-593cd2ac`
- Started: `2026-08-14T05:20:07Z`
- Completed: `2026-08-14T05:38:59Z`
- Raw SHA-256: `bf718aed08e226149c9310cbf20bf25c403708217e2908789120178ac5574e28`
- Git HEAD: `5d9979728b1e7d44caf3b5ee19077d0497610991` (`main`)

## 2. Dataset binding

| Binding | Identity | SHA-256 | Post-run |
| --- | --- | --- | --- |
| Corpus | `learnpilot-rag-real-world-corpus@v1` | `6f67d510cd35197f107400d33033972c0c3c84478174e4991e491f6c8e4ab563` | unchanged |
| Gold | `learnpilot-rag-real-world-gold-v1` | `33a0b69901fa47e3fe45be0277228cd4a5519fe780fe5b9d2c52b1bfe614927a` | unchanged |
| Freeze manifest | `gold-dataset-v1-final-freeze` | `d979079be4eb901a825ab29414dd7b5124d030182e09b55eea1e93749c12a5c2` | unchanged |

Pre-run `final_freeze_v1.py verify` returned `PASS / FROZEN`. Gold V1 contains 72 cases,
132 claims, and 89 anchors. CORE=60; STRESS=12.

## 3. Production RAG identity

The evaluated path was the current production-equivalent dense-only chain:

`production ingestion → BGE-M3 → FAISS IndexFlatIP → threshold → overlap dedup → document diversity → context budget → DeepSeek grounded generation → deterministic citations`

Per-file SHA-256 values for 15 production files are frozen in `raw_results.json`.
Pre/post monitored production-code mismatch count was zero. No BM25, sparse retrieval,
independent reranker, cross-encoder, LLM reranker, or hybrid retrieval was present.

## 4. Exact system configuration

| Setting | Value |
| --- | --- |
| Embedding | `BAAI/bge-m3`, revision `local-cache`, CPU, normalized, local-only |
| Embedding dimension | 1024 |
| Vector index | FAISS `IndexFlatIP`, 442 chunks |
| Index version | `a403f44e800a4941a9229ef439b8999a` |
| Diagnostic candidate limit | 18, derived from production `top_k * 3` rule |
| Production answer Top-K | 6 |
| Minimum score | 0.35 |
| Maximum sources | 6 |
| Maximum chunk/context chars | 2200 / 12000 |
| Query rewrite | enabled; fresh conversation per case produced no rewrite |
| Provider/model | `openai_compatible` / `deepseek-v4-flash` at `api.deepseek.com` |
| Temperature/reasoning | 0.1 / disabled |
| Structured output limit | 2400 tokens |
| Timeout/retries | 60 seconds / canonical maximum 2 retries |
| Answer/rewrite prompts | `rag-answer-v2-evidence-binding` / `rag-rewrite-v1` |

## 5. Execution completeness

- Corpus ingestion: 11/11 documents through public production APIs.
- Installed index: 442/442 chunks, verified `IndexFlatIP`.
- Cases: 72/72 completed.
- Unique `case_id`: 72; unique `case_run_id`: 72.
- Each case used one fresh conversation and one answer request.
- Production selection telemetry matched deterministic stage reconstruction: 72/72.
- Request failures, timeouts, parse errors, provider retries, repairs, and fallbacks: all zero.

## 6. Retrieval metrics

Metrics respect Gold V2 semantics: OR within each evidence group, AND across required groups.

| Layer | Document group pass | Diagnostic anchor group pass |
| --- | ---: | ---: |
| Candidate retrieval | 71/72 (98.61%) | 59/72 (81.94%) |
| Selected context | 71/72 (98.61%) | 41/72 (56.94%) |

The only document-group candidate miss was `rw-gold-v1-multi-rag-tracing`. Anchor/chunk
coverage is explicitly diagnostic because it depends on stable-anchor-to-runtime-chunk mapping;
document-group coverage is the primary stable metric.

## 7. Selected-context metrics

All 72 cases retained full production stage evidence: ranked candidates, threshold rejects,
dedup rejects, diversity first pass/deferred items, pre-budget selection, final selected context,
and context character counts. The document-group miss was already absent at the 18-candidate
layer; there was no additional document-group pass lost between candidate and selected context.
Diagnostic anchor pass declined from 59 to 41 cases between candidate and selected context.

## 8. Claim and answer metrics

| Evaluation mode | Claims | Machine result policy |
| --- | ---: | --- |
| `NUMERIC_EXACT` | 7 | deterministic |
| `IDENTIFIER_EXACT` | 5 | deterministic |
| `STRUCTURED_EXACT` | 6 | deterministic |
| `ANSWERABILITY_ONLY` | 10 | deterministic |
| `SEMANTIC_REVIEW` | 104 | `REVIEW_REQUIRED` |

Machine-deterministic claims passed 24/28 (85.71%). The four failed claims occurred in three
cases: two numeric claims in `single-dependency-defaults`, one structured claim in
`long-bge-score-mix`, and one structured claim in `stress-deep-bge-mldr-comparison`.
All 104 semantic claims remain pending review; no lexical proxy was used to manufacture a
semantic pass rate.

## 9. Citation metrics

- Citation structural validity: 72/72 cases, including valid zero-citation refusals.
- Required citation/document-group machine contract: 58/72 (80.56%).
- Known unsupported/distractor-document citation violations: 0.
- Citation semantic support/correctness: `REVIEW_REQUIRED` where deterministic evidence-role
  checks are insufficient.

Validity, required coverage, evidence role, known unsupported sources, and semantic support
status are recorded separately rather than collapsing citation quality into ID existence.

## 10. Answerability

- Overall answerability accuracy: 60/72 (83.33%).
- Frozen unanswerable boundary set: 10/10 correct refusals.
- Answerable cases answered: 50/62.
- Answerable cases incorrectly refused: 12/62.
- Unanswerable citations: zero; known unsupported near-boundary citation violations: zero.

## 11. CORE versus STRESS

| Tier | Cases | Candidate docs | Selected docs | Answerability | Citation contract |
| --- | ---: | ---: | ---: | ---: | ---: |
| CORE | 60 | 98.33% | 98.33% | 83.33% | 80.00% |
| STRESS | 12 | 100.00% | 100.00% | 83.33% | 83.33% |

## 12. Case-type breakdown

| Case type | N | Candidate docs | Selected docs | Answerability | Citation contract |
| --- | ---: | ---: | ---: | ---: | ---: |
| `single_doc_fact` | 10 | 100% | 100% | 90% | 90% |
| `semantic_paraphrase` | 10 | 100% | 100% | 100% | 90% |
| `long_doc_localization` | 10 | 100% | 100% | 70% | 70% |
| `multi_doc_synthesis` | 10 | 90% | 90% | 70% | 60% |
| `source_disambiguation` | 10 | 100% | 100% | 70% | 70% |
| `unanswerable_near_boundary` | 10 | 100% | 100% | 100% | 100% |
| `deep_long_doc_localization` | 4 | 100% | 100% | 100% | 100% |
| `cross_topic_multi_doc` | 4 | 100% | 100% | 50% | 50% |
| `high_overlap_source_conflict` | 4 | 100% | 100% | 100% | 100% |

## 13. Topic breakdown

| Primary topic | N | Candidate docs | Selected docs | Answerability | Citation contract |
| --- | ---: | ---: | ---: | ---: | ---: |
| `agent_engineering` | 18 | 100% | 100% | 83.33% | 72.22% |
| `ai_app_backend` | 18 | 100% | 100% | 83.33% | 83.33% |
| `evaluation_reliability` | 19 | 94.74% | 94.74% | 84.21% | 84.21% |
| `rag_retrieval` | 17 | 100% | 100% | 82.35% | 82.35% |

## 14. Difficulty breakdown

| Difficulty | N | Candidate docs | Selected docs | Answerability | Citation contract |
| --- | ---: | ---: | ---: | ---: | ---: |
| easy | 10 | 100% | 100% | 90.00% | 90.00% |
| medium | 19 | 100% | 100% | 89.47% | 84.21% |
| hard | 31 | 96.77% | 96.77% | 77.42% | 74.19% |
| stress | 12 | 100% | 100% | 83.33% | 83.33% |

## 15. Language breakdown

| Query language | N | Candidate docs | Selected docs | Answerability | Citation contract |
| --- | ---: | ---: | ---: | ---: | ---: |
| English | 18 | 100% | 100% | 94.44% | 94.44% |
| zh-CN | 54 | 98.15% | 98.15% | 79.63% | 75.93% |

## 16. Latency

| Measurement | Mean | P50 | P95 | Max |
| --- | ---: | ---: | ---: | ---: |
| Full answer HTTP | 2632.35 ms | 2493.84 ms | 3728.66 ms | 4373.85 ms |
| Observed generation | 2428.84 ms | 2291.73 ms | 3510.73 ms | 4177.02 ms |

Per-case rewrite, query embedding, retrieval, observed selection overhead, generation, and total
latencies are retained in raw and case artifacts.

## 17. Token usage

- Input: 125,280 total; mean 1,740/case; p50 1,754; p95 1,988.
- Output: 8,981 total; mean 124.74/case; p50 120; p95 239.
- Overall: 134,261 tokens.
- No currency cost is estimated because provider price metadata was not part of the reliable
  production response contract.

## 18. Failure inventory

Failure traces contain signals only, never final root-cause labels.

| Preliminary signal | Cases |
| --- | ---: |
| Semantic review required | 54 |
| Citation machine-contract mismatch | 14 |
| Answerability mismatch | 12 |
| Deterministic claim mismatch | 3 |
| Required document group absent from candidates | 1 |
| Required document group absent from selected context | 1 |

There are 55 trace rows because machine signals and semantic-review obligations overlap. Formal
retrieval/selection/generation classification is deferred to Real-world Baseline Failure Analysis V1.

## 19. Reproducibility

- Deterministic Gold order; sequence numbers 1–72.
- One fresh conversation and unique request ID per case.
- No stochastic seed is exposed by the production path; canonical temperature remained 0.1.
- Canonical provider retry limit 2 and timeout 60 seconds; observed retries were zero.
- Complete prompt messages, raw provider drafts, parsed drafts, token usage, finish reasons,
  selected contexts, citations, and timings are retained.
- Runtime package versions and all production source hashes are stored in `raw_results.json`.

## 20. Benchmark immutability after run

Direct post-run SHA-256 verification passed for Gold, freeze manifest, corpus manifest, frozen
corpus files, and the full protected benchmark scope. `protected_corpus_gold_freeze_unchanged`
and `pre_post_frozen_identity_match` are both true. Raw results were written and detached-hashed
before metric computation, then re-hashed after metrics with an exact match.

## 21. Production code and state

Production RAG was read/executed only. Monitored source hashes, production SQLite, uploads,
FAISS, and checkpoint state matched before and after. The isolated evaluation SQLite/uploads/
FAISS/checkpoint directory was removed after its persistence audit. No personal knowledge base,
production database, unrelated repository data, API credential, secret, authorization header,
or environment dump appears in the artifacts; the post-run secret-pattern scan found no match.

## 22. Tests

`backend/tests/test_rag_real_world_dense_only_baseline_v1.py`: **7 passed**.

Coverage includes frozen bindings, V2 OR/AND group semantics, semantic-review separation,
deterministic claim modes, unanswerable/citation contracts, metrics recomputation, 72 unique raw
records, detached raw hash, protected benchmark hashes, and production code/state invariants.

## 23. Files created or restored

Created:

- `evals/rag_real_world_corpus/v1/dense_only_baseline_v1/instrumented_app.py`
- `evals/rag_real_world_corpus/v1/dense_only_baseline_v1/dense_baseline_metrics.py`
- `evals/rag_real_world_corpus/v1/dense_only_baseline_v1/run_dense_only_baseline_v1.py`
- `backend/tests/test_rag_real_world_dense_only_baseline_v1.py`
- `evals/rag_real_world_corpus/v1/results/dense_only_baseline_v1/latest_run.json`
- `evals/rag_real_world_corpus/v1/results/dense_only_baseline_v1/20260814T052007Z-593cd2ac/` and its 21 run artifacts
- `evals/rag_real_world_corpus/v1/RAG_REAL_WORLD_DENSE_ONLY_BASELINE_V1_REPORT.md`

Restored byte-for-byte before the run:

- `evals/rag_real_world_corpus/v1/validation_report.json` — final SHA-256
  `0e539331410bdab0a91c6e81acc199cdb6bf751926ddd67a52f2c454a570c0e6`, exactly matching the
  frozen immutability baseline. No semantic benchmark content changed.

## 24. Measurement boundary and next stage

No optimization was performed. Top-K, threshold, chunking, embedding, context budget, query
rewrite, generation prompt, citations, model, Gold, Corpus, Controlled V2, and production RAG
were not tuned or repaired. This report establishes the current AS-IS baseline only.

The next stage is **Real-world Baseline Failure Analysis V1**. `RAG_OPTIMIZATION` is not complete
and has not started.
