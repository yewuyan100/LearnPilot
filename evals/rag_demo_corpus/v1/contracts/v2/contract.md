# LearnPilot RAG Eval & Gold Contract V2

This contract evaluates the unchanged `Controlled Corpus V1`. It does not
replace or reinterpret the canonical V1 artifact in place.

## Ubiquitous language

- **Raw First K**: the first `top_k` rows returned by diagnostic vector search,
  before the RAG module's deterministic selection.
- **Candidate Expansion**: the threshold-eligible portion of the expanded search
  candidates (`candidate_expansion=18` in the frozen run).
- **Final Context**: the de-duplicated, diversified, budgeted sources actually
  available to answer generation.
- **Required Evidence Group**: one or more equivalent documents. At least one
  document in every required group is needed. Groups compose with `AND`; documents
  inside a group compose with `OR`.
- **Acceptable Supporting Evidence**: a corpus document that genuinely supports a
  claim but is not necessary to satisfy a required group.
- **Irrelevant or Disallowed Evidence**: a document that does not support the
  answer; all corpus citations are disallowed for genuinely unanswerable cases.
- **Lexical Proxy**: reproducible term overlap. It is diagnostic evidence, never
  semantic ground truth for `SEMANTIC_REVIEW` claims.
- **Reviewed Semantic Verdict**: an explicit, versioned reviewer judgment with an
  answer span, document IDs, and reason.

## Claim contract

Every expected claim has a stable `claim_id`, a `canonical_claim`, `required`,
`evidence_group_ids`, `evaluation_mode`, and notes. Evaluation modes are:

- `STRUCTURED_EXACT`: exact required fields or an exact order.
- `NUMERIC_EXACT`: exact configured number(s).
- `IDENTIFIER_EXACT`: exact stable identifiers when a case needs them.
- `SEMANTIC_REVIEW`: explicit reviewed meaning; lexical overlap is only reported.
- `ANSWERABILITY_ONLY`: refusal behavior for genuinely absent knowledge.

Optional claims remain observable but cannot fail a case. This prevents an
explanatory detail beyond the question from becoming an accidental hard
requirement.

## Evidence and citation contract

A cited document is reviewed as `REQUIRED`, `ACCEPTABLE_SUPPORT`, or
`UNSUPPORTED`. Structural citation validity and semantic support are separate.
A V2 reviewed pass requires:

1. correct answerability;
2. every required claim is `SUPPORTED`;
3. no required claim is contradicted;
4. the required citation groups are satisfied for an answerable response;
5. no `UNSUPPORTED` citation materially supports the answer;
6. unanswerable responses contain no citation.

`PARTIALLY_SUPPORTED`, `NOT_SUPPORTED`, `CONTRADICTED`, and `AMBIGUOUS_GOLD`
do not satisfy a required claim. A deterministic pass is intentionally reported
separately and cannot decide a semantic claim.

## Unanswerable contract

An unanswerable case requires `answerable=false`, no unsupported factual answer,
and no citation pretending the corpus has the answer. A genuinely absent answer
is distinct from a failure to retrieve knowledge that is present in the corpus.
The current production contract does not require extra refusal wording, so V2
does not invent it.

## Anti-overfitting rule

Gold claims and evidence roles are derived from the frozen corpus before the
frozen answer is compared. Every semantic mutation from V1 records one or more
approved audit reasons. `CHANGED_TO_MAKE_CASE_PASS` is not a valid reason.

## Version seam

The external V2 interface is `validate_contract()` and `score_frozen_baseline()`
in `eval_v2.py`. V1 files remain where they are. V2 owns only the assets in this
directory and results under `results/contract_v2_review/`.
