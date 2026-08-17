<!-- Hallmark · pre-emit critique: P5 H5 E5 S5 R5 V4 -->
# LearnPilot Final Product Audit

Run ID: `20260816T140758Z-finalproductaudit`

Audit mode: `AUDIT_ONLY=true`  
Production fixes allowed: `false`  
Production code changed: `false`

## Decision

```text
LEARNPILOT_FINAL_PRODUCT_AUDIT = PASS_WITH_P2

CORE_USER_WORKFLOWS = PASS
RUNTIME_REPRODUCIBILITY = PASS
FRONTEND_BACKEND_CONTRACT = PASS
CUDA_RAG_RUNTIME = PASS
DENSE_FALLBACK = PASS
DATA_STATE_INTEGRITY = PASS
GENERATION_NONDETERMINISM_SEVERITY = DOCUMENTED_LIMITATION

P0_COUNT = 0
P1_COUNT = 0
P2_COUNT = 3

NEW_DEEPSEEK_CALLS = 0
NEW_RAG_BENCHMARKS = 0
NEW_FEATURES = 0
PRODUCTION_CODE_CHANGED = false
PRODUCTION_DEPENDENCY_CHANGED = false
REPOSITORY_CLEANUP_EXECUTED = false
READY_FOR_REPOSITORY_CLEANUP = YES
```

## Authoritative evidence reused

- `rag_one_final_closure/20260816T130718Z-onefinalclosure`: 428/428 backend regression, 34/34 focused production-RAG tests, OpenAPI/RAG contract PASS, CUDA FP32 Top18 → Top7 runtime PASS, singleton PASS, and Dense fallback PASS.
- Freshness proof: the prior closure's `git status --short` count/hash and `git diff --name-only` count/hash exactly match this audit's preflight snapshot (`386` / `a896...b2d5`, `117` / `d180...1d5`). No corresponding production change occurred after that evidence.
- `FINAL_USABILITY_CLOSURE_REPORT.md` plus `artifacts/final-usability-closure/browser-acceptance.json`: Planning and Notes lifecycle acceptance, no console errors, no failed requests, full backend/frontend suites green at that closure.
- `frontend/artifacts/learnpilot-polish-1b/browser-acceptance.json` and `FINAL_VISUAL_CLOSURE_REPORT.md`: Workbench and primary-route browser evidence, Knowledge and AI route acceptance, frontend test/lint/build gates.

## Core workflows

| Workflow | Result | Basis |
| --- | --- | --- |
| Workbench | PASS | Existing browser acceptance opens `/workspace`, verifies LearnPilot identity and primary cards/sections; current Vite shell smoke returned 200. |
| Learning Planning | PASS | Create/Rename/Delete and detail navigation covered by final usability tests and real browser lifecycle. |
| Knowledge Base | PASS | Material list/access and RAG participation covered by current backend regression and browser route evidence; failure states are rendered rather than crashing. |
| RAG Q&A | PASS | Real production E2E returned HTTP 200 for 5/5; Top18 → CUDA rerank → Top7 was exact; all 13 citation IDs resolved. One answer omitted one supported branch and is documented below. |
| AI Collaboration | PASS | Route and API contract intact; frontend safe-error and context-isolation tests are green within the authoritative frontend/backend evidence. |
| Notes | PASS | Create/Rename/Archive/Delete covered by canonical tests and browser lifecycle acceptance. |
| Discover | PASS | Lightweight `/explore` route opens without browser errors and does not claim unavailable capabilities. |
| Settings | PASS | `/settings` opens; no functional blocker found. Visual redesign was out of scope. |

## Runtime and startup

- Backend production entry: from repository root, run `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\backend\scripts\start_rag_cuda_backend.ps1`.
- Frontend entry: `Set-Location frontend` then `npm run dev` (optional explicit host used in this audit: `npm run dev -- --host 127.0.0.1`).
- Backend environment: `.venv-cuda\Scripts\python.exe`, Python 3.11.9, `torch 2.12.1+cu126`, CUDA 12.6, RTX 4060 detected.
- Current root `.env` has the required production RAG and DeepSeek keys configured; the API key was not printed. The local reranker snapshot path exists with all required model files.
- The CUDA launcher started Uvicorn on `127.0.0.1:8000`; `/api/health` returned `{"status":"ok"}` and OpenAPI exposed 143 paths including the production RAG ask endpoint.
- Vite started on `127.0.0.1:5173`; `/workspace`, `/items`, `/knowledge`, `/ai`, `/notes`, `/explore`, and `/settings` each returned the LearnPilot application shell with HTTP 200.
- Both temporary processes were stopped; ports 8000 and 5173 were free at audit end.
- Same-machine restart reproducibility is PASS. New-machine setup documentation is incomplete and is recorded as P2-001, not a current runtime failure.

## Contract, failure modes, and state

- Frontend/backend contract: PASS. Current OpenAPI retains the RAG request/response required fields, with reranker observability added only as optional metadata.
- GPU/reranker unavailable: PASS via deterministic `dense_fallback`, final context ≤7, degraded metadata, and no reload loop.
- DeepSeek failures: mapped to public retryable messages; raw stack traces are not returned.
- Empty retrieval/no evidence: explicit refusal path; LLM is not called when the index/evidence is unavailable.
- Invalid requests: global 422 error envelope strips non-serializable internal context.
- Database: read-only `PRAGMA integrity_check=ok`, `foreign_key_check=0`; Alembic current and head are both `20260809_0020`, and `alembic check` found no pending schema operations.

## Generation nondeterminism

Final severity: `DOCUMENTED_LIMITATION`.

The fixed five-case production closure passed 4/5. The failed FastAPI case still returned HTTP 200, selected all 3/3 required evidence groups in Top7, resolved every emitted citation, answered 2/3 supported branches correctly, and contained no unsupported fabrication. The omitted external-threadpool branch is an occasional completeness defect, but the evidence does not show a stable, severe, normal-use failure. Under the product-level severity gate it is non-blocking and does not remain P1.

## P2 findings

1. `P2-001 RUNTIME_DOCUMENTATION_DRIFT`: the real launcher uses `.venv-cuda`, while README still presents `.venv`; `.env.example` defaults the reranker off and omits the absolute model snapshot. Current-machine restart works, but setup/recovery instructions need consolidation in the next documentation phase.
2. `P2-002 RELEASE_METADATA_DRIFT`: the visible product is LearnPilot, while README, backend/OpenAPI defaults, and the frontend package name still use PersonalLearning. This is a demo/release polish issue, not a core functional failure.
3. `P2-003 REPOSITORY_HYGIENE_DEBT`: the worktree has 386 status entries and large local/evaluation debris. Inspected cleanup surfaces total about 9.87 GB, dominated by `.tmp` model copies/incomplete downloads and an old ONNX export. No files were deleted or moved.

## Repository cleanup readiness

`READY_FOR_REPOSITORY_CLEANUP = YES`.

Keep production source, migrations, the CUDA launcher, the gold/frozen RAG corpus and contracts, the latest RAG closure, and final usability/release evidence. Archive historical V1–V12 and superseded RAG experiment reports/runs. Review for deletion `.tmp` model copies, incomplete downloads, ONNX scratch environments/exports, browser profiles, caches, bytecode, and empty temporary directories. Execute no cleanup without a separate scoped cleanup run.

Next phase:

```text
Repository Cleanup
→ README / Architecture
→ Resume
→ Interview Preparation
```
