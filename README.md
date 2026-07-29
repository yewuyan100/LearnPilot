# PersonalLearning

PersonalLearning 是一个本地优先、单用户使用的个人学习工作台。当前版本为 **V3：可信引用式 RAG 学习问答层**。它完整保留 V1 学习管理和 V2 本地知识库，并在其上提供有资料依据、有来源引用、资料不足会拒答的多轮问答。

## V3 能做什么

```text
创建资料问答会话
→ 有限历史查询改写
→ 复用 V2 BGE-M3 + FAISS 检索
→ 来源筛选、去重和上下文预算
→ 资料充分性门控
→ OpenAI-compatible LLM Structured Output
→ 引用合法性校验或一次修复
→ 回答并显示来源，或稳定拒答
→ 消息与引用快照持久化
→ 校验后 SSE 分段输出
```

`/rag` 页面支持会话列表、刷新恢复、限定资料范围、停止生成和来源详情。回答只引用本次实际送入模型的 `S1`、`S2` 等来源。删除原资料后，历史消息仍保留文件名、位置和正文摘录快照，但新检索不会命中已删除资料。

V1/V2 原有能力继续可用：

- 学习目标、课程、知识点和今日任务 CRUD；
- 学习会话创建/恢复、暂停/继续、笔记和完成；
- 今日页、复习基础页、进度页和设置页；
- Demo 数据导入与清理。
- PDF / Markdown / TXT 解析、切片、本地 BGE-M3 Embedding、FAISS 索引和语义检索。

## 当前不能做什么

当前版本不包含 LangGraph、Agent Planner、工具调用、联网搜索、MCP 连接器、自动课程、自动出题/批改、掌握度算法、OCR、图片/音视频理解、多用户、登录、云部署或微服务。扫描版 PDF 仍不支持 OCR。

## 技术栈

- 前端：React 19、TypeScript、Vite、React Router、TanStack Query、Lucide React、Recharts；
- 后端：Python、FastAPI、Pydantic 2、SQLAlchemy 2、Alembic、SQLite；
- 知识库：pypdf、sentence-transformers、`BAAI/bge-m3`、NumPy、FAISS `IndexFlatIP`；
- 问答：OpenAI-compatible Chat Completions、Pydantic Structured Output、FastAPI `StreamingResponse`；
- 测试：pytest、FastAPI TestClient、Vitest、Testing Library、ESLint。

## 目录结构

```text
PersonalLearning/
├─ backend/
│  ├─ alembic/versions/
│  ├─ app/
│  │  ├─ api/
│  │  ├─ core/
│  │  ├─ db/
│  │  ├─ models/
│  │  ├─ repositories/
│  │  ├─ schemas/
│  │  └─ services/
│  │     ├─ embedding/
│  │     ├─ llm/
│  │     ├─ material_processing/
│  │     ├─ rag/
│  │     └─ vector_store/
│  └─ tests/
├─ frontend/src/
│  ├─ api/
│  ├─ components/
│  ├─ layouts/
│  ├─ pages/
│  ├─ test/
│  ├─ types/
│  └─ utils/
├─ docs/
├─ evals/
├─ scripts/
│  ├─ acceptance_v1.py
│  ├─ acceptance_v2.py
│  ├─ acceptance_v3.py
│  └─ evaluate_v3.py
├─ .env.example
├─ V1_*.md
├─ V2_TASK.md
├─ V2_PROGRESS.md
├─ V2_COMPLETION_REPORT.md
├─ V3_TASK.md
└─ V3_PROGRESS.md
```

## 环境要求

- Windows 10/11 与 PowerShell 5.1+；
- Python 3.11+；
- Node.js 20+ 与 npm 10+；
- 本机已有 `BAAI/bge-m3` Hugging Face 缓存。无需重新下载已有模型。
- 一个可用的 OpenAI-compatible Chat Completions 服务（仅真实问答、评测和 V3 验收需要）。

## Windows PowerShell 安装

在项目根目录执行：

```powershell
Copy-Item .env.example .env

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt

Set-Location .\frontend
npm install
Set-Location ..
```

## 本地模型配置

在 `.env` 中设置本机缓存根目录。`HF_HOME` 可以指向标准 Hugging Face 根目录，程序会兼容其下的 `hub` 目录：

```env
HF_HOME=D:/AIModels/HuggingFace
EMBEDDING_MODEL_NAME=BAAI/bge-m3
EMBEDDING_MODEL_REVISION=local-cache
EMBEDDING_LOCAL_FILES_ONLY=true
EMBEDDING_DEVICE=cpu
EMBEDDING_BATCH_SIZE=8
EMBEDDING_NORMALIZE=true
```

默认 `local_files_only=true`，不会偷偷联网下载模型。模型缺失时，处理 API 会保留原文件与 Material 记录，并返回可理解的配置错误。

## 回答模型配置

`.env` 只保存本地配置，已被 Git 忽略。不要把真实 Key 写入 `.env.example`：

```env
LLM_PROVIDER=openai_compatible
LLM_API_KEY=
LLM_BASE_URL=
LLM_MODEL=
LLM_TIMEOUT_SECONDS=60
LLM_MAX_RETRIES=2
LLM_TEMPERATURE=0.1
LLM_MAX_OUTPUT_TOKENS=1200
```

未配置 LLM 时，上传、解析、索引、检索和全部隔离测试仍可运行；`GET /api/rag/status` 会诚实返回 `llm_configured=false`。找到相关资料后发起生成会返回清晰的 `503 llm_not_configured`。

## 数据库迁移

```powershell
Set-Location .\backend
..\.venv\Scripts\alembic.exe upgrade head
..\.venv\Scripts\alembic.exe current
..\.venv\Scripts\alembic.exe heads
..\.venv\Scripts\alembic.exe check
Set-Location ..
```

当前 head 为 `20260730_0003`。重置本地开发数据库会删除本地数据：

```powershell
.\scripts\reset_database.ps1
```

## 启动后端

```powershell
Set-Location .\backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- 健康检查：`http://127.0.0.1:8000/api/health`
- OpenAPI：`http://127.0.0.1:8000/docs`

## 启动前端

```powershell
Set-Location .\frontend
npm run dev
```

浏览器打开 `http://localhost:5173`。

## Demo 数据

```powershell
.\.venv\Scripts\python.exe .\scripts\seed_demo.py
.\.venv\Scripts\python.exe .\scripts\clear_demo.py
```

Demo 脚本只管理带 `is_demo` 标记的 V1 学习数据，不伪造资料 Chunk 或向量索引。

## 测试与构建

后端默认测试使用临时 SQLite、上传目录、FAISS 目录与 FakeEmbedder，不加载 2GB 模型：

```powershell
Set-Location .\backend
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe -m compileall app ..\scripts
..\.venv\Scripts\alembic.exe check
Set-Location ..
```

前端：

```powershell
Set-Location .\frontend
npm run test
npm run lint
npm run build
Set-Location ..
```

V1 API 回归需要先启动 8000 端口后端：

```powershell
.\.venv\Scripts\python.exe .\scripts\acceptance_v1.py
```

V2 真实模型验收会在 8011 端口自行启动两次隔离后端，使用临时数据库、上传目录和索引，并验证重启恢复：

```powershell
$env:HF_HOME = "D:\AIModels\HuggingFace"
$env:HF_HUB_OFFLINE = "1"
.\.venv\Scripts\python.exe .\scripts\acceptance_v2.py
Remove-Item Env:HF_HUB_OFFLINE -ErrorAction SilentlyContinue
```

V3 真实验收使用真实 BGE-M3 和 `.env` 中的真实 LLM 配置，在 8012 端口自行启动两次隔离后端：

```powershell
$env:HF_HOME = "D:\AIModels\HuggingFace"
$env:HF_HUB_OFFLINE = "1"
.\.venv\Scripts\python.exe .\scripts\acceptance_v3.py
Remove-Item Env:HF_HUB_OFFLINE -ErrorAction SilentlyContinue
```

准备好 `evals/fixtures` 三份资料并建立索引后，可对运行中的 API 执行评测：

```powershell
.\.venv\Scripts\python.exe .\scripts\evaluate_v3.py --isolated
```

## 关键配置

| 配置 | 默认值 | 说明 |
|---|---:|---|
| `MATERIAL_CHUNK_SIZE` | `800` | Chunk 最大字符窗口 |
| `MATERIAL_CHUNK_OVERLAP` | `120` | 相邻 Chunk 重叠 |
| `MATERIAL_MIN_CHUNK_SIZE` | `80` | 尾部小片段合并阈值 |
| `FAISS_INDEX_PATH` | `./data/materials.faiss` | 本地索引 |
| `FAISS_MANIFEST_PATH` | `./data/materials.faiss.manifest.json` | ID 映射与索引元数据 |
| `SEARCH_TOP_K_DEFAULT` | `5` | 默认返回数 |
| `SEARCH_TOP_K_MAX` | `20` | API 上限 |
| `RAG_TOP_K_DEFAULT` / `RAG_TOP_K_MAX` | `6` / `12` | RAG 初始召回数与请求上限 |
| `RAG_MIN_SCORE` | `0.35` | 初始相关度阈值，需通过评测调整，不是普适最佳值 |
| `RAG_MAX_SOURCES` | `6` | 最多送入模型的来源数 |
| `RAG_MAX_CONTEXT_CHARS` | `12000` | 资料上下文总字符预算 |
| `RAG_HISTORY_MESSAGES` | `6` | 查询改写最多读取的最近消息数 |

上传内容、SQLite、FAISS、Manifest、模型缓存、虚拟环境、`node_modules` 和构建产物均不会提交到 Git。

## 常见问题

### 上传后为什么仍是“待解析”？

上传的 `201 Created` 只表示原始文件保存成功。请在资料页点击“处理资料”，系统才会执行解析、切片、Embedding 和索引重建。

### 为什么模型明明存在仍提示找不到？

确认 `HF_HOME` 指向包含 `hub/models--BAAI--bge-m3` 的根目录，并保持 `EMBEDDING_MODEL_NAME=BAAI/bge-m3`。程序不会在离线模式下补下载缺失文件。

### 为什么 PDF 解析失败？

加密、损坏或没有可提取文本的扫描版 PDF 会失败。V2 不做 OCR；原文件和失败状态会保留，可修复文件后重新处理。

### 索引状态为什么显示需要重建？

Manifest 与 SQLite Chunk 校验不一致、模型配置变化、索引文件缺失或损坏时，旧索引会拒绝使用。请在资料页执行“重新构建索引”。

### 为什么资料问答会拒答？

没有可用索引、索引过期、检索无结果、分数低于当前阈值或上下文为空时，确定性门控会在调用 LLM 前拒答。模型即使被调用，也必须返回受 Pydantic 校验的结构，并通过引用校验。

更多说明见 [架构](docs/architecture.md)、[RAG 设计](docs/rag.md)、[评测](docs/evaluation.md)、[数据模型](docs/data-model.md) 与 [API](docs/api.md)。
