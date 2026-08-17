# LearnPilot Real-world Gold Dataset V1 — Baseline Binding Contract

Status: `FROZEN`  
Benchmark identity: `learnpilot-rag-real-world-gold-v1`

## Frozen identities

Every Real-world baseline or ablation that claims comparability with frozen V1 must bind these exact identities:

```text
CORPUS_ID = learnpilot-rag-real-world-corpus@v1
CORPUS_MANIFEST_SHA256 = 6f67d510cd35197f107400d33033972c0c3c84478174e4991e491f6c8e4ab563

GOLD_ID = learnpilot-rag-real-world-gold-v1
CANONICAL_GOLD_SHA256 = 33a0b69901fa47e3fe45be0277228cd4a5519fe780fe5b9d2c52b1bfe614927a

FREEZE_MANIFEST_SHA256 = d979079be4eb901a825ab29414dd7b5124d030182e09b55eea1e93749c12a5c2
```

The authoritative freeze artifact is `gold_dataset_v1_freeze_manifest.json`; its detached hash is `gold_dataset_v1_freeze_manifest.sha256`.

## Required run binding

Before execution, every future Real-world baseline/ablation run artifact must record:

Canonical required-field labels:

```text
corpus identity/hash
Gold identity/hash
freeze manifest hash
production RAG code/config identity
embedding model
retrieval configuration
generation model
evaluation timestamp
```

1. Corpus ID, corpus manifest path, and corpus manifest SHA-256.
2. Gold ID, Gold path, and canonical Gold SHA-256.
3. Freeze manifest path and freeze manifest SHA-256.
4. Production RAG code/config identity, including the exact evaluated revision or a path-to-SHA-256 snapshot.
5. Embedding model identity and version.
6. Retrieval configuration, including retrieval mode, top-k, index/config identity, and any reranking settings.
7. Generation model identity and inference configuration.
8. Evaluation timestamp and run ID.

The run must fail closed before model, embedding, or retrieval execution if any frozen corpus, Gold, or freeze-manifest identity does not match.

## Comparison rule

If either the Gold SHA-256 or corpus manifest SHA-256 changes, the result is not a same-benchmark comparison with frozen V1. It must use a new benchmark version and must not be merged into the V1 baseline series.

## Freeze rule

`RAG_REAL_WORLD_GOLD_DATASET_V1 = FROZEN`

Any semantic modification after this point requires a new benchmark version. The next version may be `v2`; silent mutation of V1 is forbidden. Baseline failures must first be treated as system findings; they do not authorize changing frozen Gold V1.

At freeze time:

```text
BASELINE_EXECUTED = NO
READY_FOR_DENSE_ONLY_BASELINE = YES
```
