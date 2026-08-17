# Real-world Gold Dataset V1 — Eval Contract V2 Adapter

本目录复用 `evals/rag_demo_corpus/v1/contracts/v2/` 的语义，不定义平行的判定体系。

## Reused V2 semantics

- Required evidence groups compose with `AND`.
- `any_of_document_ids` and `any_of_evidence_ids` compose with `OR` inside a group.
- Evidence roles are `REQUIRED`, `ACCEPTABLE_SUPPORT`, and `UNSUPPORTED`.
- Claim modes remain `STRUCTURED_EXACT`, `NUMERIC_EXACT`, `IDENTIFIER_EXACT`, `SEMANTIC_REVIEW`, and `ANSWERABILITY_ONLY`.
- Semantic review verdicts remain `SUPPORTED`, `PARTIALLY_SUPPORTED`, `NOT_SUPPORTED`, `CONTRADICTED`, and `AMBIGUOUS_GOLD`.
- Structural citation validity never implies semantic support.

## Why an adapter is required

Controlled Corpus V2's schema fixes 48 cases, a Controlled Corpus document-ID pattern, V1 trace fields, and Controlled Corpus type names. Its evaluator helpers are reusable, but the serialized dataset schema is not corpus-agnostic.

Real-world Gold therefore adds only:

- stable source anchors over frozen MD/TXT line spans and frozen PDF pages;
- CORE/STRESS case taxonomy;
- multilingual query/answer language fields;
- primary/secondary topic metadata;
- explicit source-disambiguation roles;
- independent evidence-review records;
- an evaluation binding manifest.

No Controlled Corpus V2 artifact is changed in place.

## Stable evidence rule

Gold truth resolves through `document_id` plus a source locator and `anchor_text_hash`. Runtime `Material.id`, `MaterialChunk.id`, source labels, FAISS positions, and projected chunk indices are forbidden in canonical Gold. `diagnostic_anchor_chunk_map.json` is a non-normative bridge only.
