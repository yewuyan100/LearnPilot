# LearnPilot

面向个人持续学习与知识管理的本地优先 AI 学习工作台：把学习规划、资料知识库、基于证据的问答、AI 协作、笔记和学习记录放进同一条可追溯流程。

> 对外产品名是 **LearnPilot**；`PersonalLearning` 仅作为仓库目录、数据库文件和部分内部符号的历史名称保留。

## Why LearnPilot

个人学习常被切散在资料文件、临时对话、待办和笔记里：计划看不到资料依据，聊天模型不了解个人知识库，学过的内容也难以进入下一次学习。LearnPilot 把这条链路连起来：

```text
资料 → 本地知识库 → 学习规划 / 工作台 → 基于资料的 AI 问答 → 引用、笔记与学习记录
```

## 核心能力

- **Workbench**：聚合当前事项、下一步学习动作、进行中的会话和成长概览。
- **Planning**：管理目标、课程、知识点、学习计划、任务与课节，并以提案/确认保护重要变更。
- **Knowledge Base**：导入 PDF、Markdown、TXT，完成本地解析、切片、BGE-M3 embedding 与 FAISS 索引。
- **RAG Q&A**：在指定资料范围内检索、重排、生成带来源引用的回答；资料不足时明确拒答。
- **AI Collaboration**：Learning Runtime 按上下文把请求路由到 curriculum、tutor 或受控 operations 能力；写操作需要确认。
- **Notes & Review**：连接笔记、练习、错题、掌握度、复习建议与实际学习记录。
- **Discover / Settings**：提供轻量探索入口与本地运行配置；Discover 当前有意保持轻量，不包装为成熟推荐系统。

## 架构概览

LearnPilot 是单用户、本地优先的模块化单体。React 前端通过 JSON / SSE 使用 FastAPI HTTP Interface；业务事实留在 SQLite，资料向量留在本地 FAISS，生成能力通过 OpenAI-compatible Interface 接入当前配置的 DeepSeek。

```mermaid
flowchart TB
    UI["React / TypeScript\nWorkbench · Planning · Knowledge · AI · Notes"]
    HTTP["FastAPI HTTP Interface\nPydantic contracts"]
    DOMAIN["Learning modules\nPlans · Knowledge · Activities · Notes · Mastery"]
    HARNESS["Learning Runtime\nContext · Policy · Routing · Runs · Events"]
    RAG["RAG pipeline\nDense retrieval · Cross-Encoder · Governance · Citation"]
    DATA["Local state\nSQLite · uploads · FAISS · checkpoints"]
    LLM["External OpenAI-compatible LLM\ncurrent production: DeepSeek"]

    UI --> HTTP
    HTTP --> DOMAIN
    HTTP --> HARNESS
    DOMAIN --> RAG
    HARNESS --> DOMAIN
    DOMAIN --> DATA
    RAG --> DATA
    RAG --> LLM
    HARNESS --> LLM
```

完整的模块、Interface、Seam、Adapter、状态和取舍见 [Architecture](docs/architecture.md)。

## RAG 设计

生产检索把候选召回深度与最终上下文深度解耦：

```mermaid
flowchart LR
    Q["User query"] --> D["BGE-M3 dense retrieval\nCandidate Top18"]
    D --> E["Eligibility\nscore / scope"]
    E --> C["BAAI/bge-reranker-v2-m3\nPyTorch CUDA FP32"]
    C --> G["Governance\ndedup · diversity · budgets"]
    G --> T["Final Top7 context"]
    T --> L["DeepSeek structured generation"]
    L --> V["Citation validation\nand persistence"]
    C -. "unavailable" .-> F["Dense-only degraded path"]
    F --> G
```

`RAG_CANDIDATE_TOP_K=18` 优先保证 candidate recall；cross-encoder 对整组候选做更精细的相关性排序；`RAG_FINAL_CONTEXT_TOP_K=7` 控制最终 evidence density、噪声和 token cost。Top7 不是行业默认值，而是本项目边界审计的结果：Top6、Top7、Top8 的 full-required coverage 分别为 `57/72`、`59/72`、`59/72`，且 Top7 的 12,000 字符预算违规为 `0/72`。因此 6→7 有真实边际收益，7→8 没有新增 evidence coverage。

### 为什么使用 Cross-Encoder，而没有保留 Hybrid

在冻结的 72-case / 132-claim 评测中，A（Dense）到 C（Dense + Cross-Encoder）的 fully correct cases 从 `50/72` 到 `53/72`，`SUPPORTED_CORRECT` 从 `92/132` 到 `105/132`，answerability 从 `60/72` 到 `67/72`，说明 reranker 带来可测增量。

候选 D（Dense + BM25 + RRF + Reranker）在主 benchmark 的目标集合没有相对 C 的 unique fixes；额外 lexical/domain-shift stress test 中，C 与 D 的 Hit@18 都是 `9/10`，D unique fixes 为 `0`。所以 V1 不保留尚未证明增量价值的 BM25/RRF 层；这不是“Hybrid 对所有场景无效”的普遍结论。

## 评测摘要

| 关注点 | 结果 | Canonical evidence |
| --- | --- | --- |
| 真实世界语料 | 11 documents / 442 chunks；72 cases / 132 gold claims | [corpus](evals/rag_real_world_corpus/v1/results/ingestion_v1/20260813T131304Z-ac0a8cee/result.json) · [gold audit](evals/rag_real_world_corpus/v1/gold/v1/distribution_audit.json) |
| Dense → Cross-Encoder | fully correct `50→53/72`；supported correct claims `92→105/132`；answerability `60→67/72` | [blinded review metrics](evals/rag_real_world_corpus/v1/results/hybrid_rerank_phase4_v1_1/20260814T131417Z-04dfc031/unblinded_metrics.json) |
| CUDA FP32 latency | CPU warm P50 `7797.075 ms` → CUDA P50 `469.872 ms`；P95 `589.381 ms`；mean `483.315 ms`；max `645.509 ms`；P50 speedup `16.594×` | [latency](evals/rag_real_world_corpus/v1/results/c_v1_3b_cuda_fp32_full/20260816T050910Z-fbb5cec1/latency_results.json) |
| CUDA memory / equivalence | peak reserved VRAM `2896 MiB`；reranker order、governed historical Top6、final context、required evidence 均 `72/72` 等价 | [memory](evals/rag_real_world_corpus/v1/results/c_v1_3b_cuda_fp32_full/20260816T050910Z-fbb5cec1/gpu_memory_results.json) · [equivalence](evals/rag_real_world_corpus/v1/results/c_v1_3b_cuda_fp32_full/20260816T050910Z-fbb5cec1/equivalence_results.json) |
| Lexical stress | C Hit@18 `9/10`；D Hit@18 `9/10`；D unique fixes `0` | [stress metrics](evals/rag_real_world_corpus/v1/results/c_v1_4_lexical_domain_shift/20260816T061649Z-3dc82771/summary_metrics.json) |
| Final context boundary | Top6 `57/72`；Top7 `59/72`；Top8 `59/72`；Top7 budget violations `0/72` | [boundary](evals/rag_real_world_corpus/v1/results/rag_context_selection_boundary_audit/20260816T094403Z-boundaryaudit/selection_boundary_decision.json) · [budget](evals/rag_real_world_corpus/v1/results/rag_candidate_final_depth_decoupling/20260816T101548Z-depthdecouple/context_budget_validation.json) |

CUDA 的 `72/72` 等价性来自当时冻结的 historical Top6 contract；后续 Top7 由独立、确定性的 production replay 验证。两组证据没有混用。

### Engineering decisions

- 用 claim-level、case-level 与 answerability 指标共同判断检索质量，不声称“100% RAG accuracy”。
- Cross-Encoder 在 CPU 上质量有增量但延迟不合格；ONNX Runtime FP32 CPU 保持语义等价，却把 P50 从约 `7.8s` 提高到约 `10.4s`，因此拒绝。
- PyTorch CUDA FP32 在保持冻结排序契约的同时把 reranker P50 降到约 `470ms`，成为 primary runtime。
- 候选 Top18 与最终 Top7 分离，让 recall 和 context precision 成为可独立治理的目标。
- CUDA / reranker 不可用时进入带 degraded metadata 的 Dense-only path，而不是让问答整体失效。
- 引用 ID 有效性与引用语义支持分开评估；结构正确不自动等于内容被证据完整支持。

## 技术栈

| 层 | 当前实现 |
| --- | --- |
| Frontend | React 19、TypeScript 5.8、Vite 7、React Router 7、TanStack Query 5、Recharts 3 |
| Backend | Python 3.11、FastAPI、Pydantic 2、SQLAlchemy 2、Alembic、Uvicorn |
| Knowledge | pypdf、sentence-transformers、`BAAI/bge-m3`、FAISS `IndexFlatIP` |
| AI / orchestration | OpenAI-compatible LLM（当前 DeepSeek）、Learning Runtime harness、LangGraph constrained operations workflow |
| Reranking | `BAAI/bge-reranker-v2-m3` revision `953dc6…d41e`、PyTorch CUDA FP32 |
| State | SQLite business DB、SQLite LangGraph checkpoint、local uploads、FAISS index + manifest |

## Quick Start（Windows / PowerShell）

### Prerequisites

- Python 3.11；Node.js 与 npm。
- Primary reranker path 需要 NVIDIA GPU 和兼容的驱动，以及安装在 `.venv-cuda` 中的 CUDA-enabled PyTorch wheel。已验证环境为 Python 3.11.9、`torch 2.12.1+cu126`；wheel 自带所需 CUDA runtime，**不要求单独安装完整 CUDA Toolkit 12.6**。
- 本地 `BAAI/bge-m3` embedding cache，以及 `BAAI/bge-reranker-v2-m3` revision `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e` snapshot。
- DeepSeek API credential；不要把真实 key 提交到仓库。

### 1. Environment

```powershell
Copy-Item .env.example .env
py -3.11 -m venv .venv-cuda
.\.venv-cuda\Scripts\python.exe -m pip install -r .\backend\requirements.txt
```

`backend/requirements.txt` 当前没有固定 CUDA PyTorch wheel；请按本机 GPU/driver 为 `.venv-cuda` 安装兼容 wheel，并先确认：

```powershell
.\.venv-cuda\Scripts\python.exe -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

编辑根目录 `.env`。至少设置以下启动契约（路径只是占位，不要复制作者机器路径）：

```dotenv
APP_NAME=LearnPilot
LLM_API_KEY=<your-deepseek-api-key>
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
HF_HOME=D:/path/to/huggingface-cache
EMBEDDING_MODEL_NAME=BAAI/bge-m3
EMBEDDING_LOCAL_FILES_ONLY=true
RAG_CANDIDATE_TOP_K=18
RAG_FINAL_CONTEXT_TOP_K=7
RAG_MAX_SOURCES_PER_MATERIAL=3
RAG_RERANKER_ENABLED=true
RAG_RERANKER_MODEL_PATH=D:/path/to/bge-reranker-v2-m3/953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e
RAG_RERANKER_DEVICE=cuda
VITE_API_BASE_URL=http://127.0.0.1:8000/api
```

### 2. Database and backend

首次启动或 migration 更新后：

```powershell
Set-Location backend
..\.venv-cuda\Scripts\python.exe -m alembic upgrade head
Set-Location ..
```

从仓库根目录使用已验证的 production launcher：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\backend\scripts\start_rag_cuda_backend.ps1
```

Backend：`http://127.0.0.1:8000`；OpenAPI：`http://127.0.0.1:8000/docs`。

### 3. Frontend

另开一个 PowerShell：

```powershell
Set-Location frontend
npm ci
npm run dev
```

Frontend：`http://127.0.0.1:5173`。若 reranker 初始化或推理失败，backend 会稳定降级到 Dense-only retrieval 并返回 `dense_fallback` / degraded metadata；若索引或证据不可用，则在调用生成模型前拒答。

## 项目结构

```text
backend/
  app/                  # FastAPI、领域模块、Learning Runtime、RAG 与持久化
  alembic/              # SQLite schema migrations
  scripts/              # production CUDA launcher
frontend/
  src/                  # React routes、UI modules、API clients、co-located tests
docs/                    # canonical architecture 与专题文档
evals/
  rag_real_world_corpus/v1/  # frozen gold、benchmark 与 RAG decision evidence
  final_product_audit/       # product-level release evidence
  repository_cleanup/       # canonical repository map
```

Reranker snapshot 位于仓库外部，通过 `RAG_RERANKER_MODEL_PATH` 配置；`.venv-cuda`、本地数据、模型缓存和 secrets 都不是源码。

## 已知限制

- 产品当前是本地单用户部署，不包含多租户、权限系统、云部署、联网搜索、OCR 或图片/音视频理解。
- Learning Runtime 是受控的能力路由与执行 harness，不是自主多 Agent 平台；没有 Supervisor 或 MCP 外部数据源。
- Discover 当前是轻量入口，不代表成熟的个性化推荐系统。
- **Generation nondeterminism**：最终固定 5-case production closure 中有 1 个复杂 multi-branch 技术问题出现 partially-correct omission。检索与 Top7 evidence 完整、citation validity 正常，但生成模型遗漏一个已有证据支持的分支。Final Product Audit 将其判定为 documented limitation，而非稳定 P0/P1；`1/5` 是小型 closure sample，不能解释为总体 `20%` 失败率。

当前 product-level 状态见 [LearnPilot Final Product Audit](evals/final_product_audit/20260816T140758Z-finalproductaudit/LEARNPILOT_FINAL_PRODUCT_AUDIT.md)，证据位置以 [Repository Cleanup canonical map](evals/repository_cleanup/20260816T151918Z-repositorycleanupclosure/canonical_repository_map.json) 为准。
