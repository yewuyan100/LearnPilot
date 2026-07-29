# PersonalLearning

PersonalLearning 是一个本地优先、单用户使用的个人学习工作台。当前版本为 **V2：本地学习资料知识库底座**，在完整保留 V1 学习目标、课程、任务、会话和进度功能的基础上，将上传文件转换为可持久化、可重建、可定位来源的本地语义索引。

## V2 能做什么

```text
上传 PDF / Markdown / TXT
→ 手动启动资料处理
→ 正文解析、清洗和确定性切片
→ Chunk 保存到 SQLite
→ 本地 BAAI/bge-m3 生成归一化 Embedding
→ FAISS IndexFlatIP + Manifest 原子保存
→ 自然语言语义检索
→ 返回文件名、页码、章节、Chunk 和相似度
```

资料页支持查看解析/索引状态与失败原因、分页查看 Chunk、重新处理、手动全量重建索引、限定资料范围检索和删除资料。重启应用后可以继续加载已有索引。

V1 原有能力继续可用：

- 学习目标、课程、知识点和今日任务 CRUD；
- 学习会话创建/恢复、暂停/继续、笔记和完成；
- 今日页、复习基础页、进度页和设置页；
- Demo 数据导入与清理。

## V2 不能做什么

当前版本不生成 AI 答案，不总结全文，不自动创建课程或知识点，不自动出题或批改，也不包含 RAG 最终回答、LLM、LangGraph、Agent、Prompt、SSE、OCR、图片/音视频理解、自动学习规划、掌握度算法、多用户或云部署。扫描版 PDF 会明确提示 V2 暂不支持 OCR。

## 技术栈

- 前端：React 19、TypeScript、Vite、React Router、TanStack Query、Lucide React、Recharts；
- 后端：Python、FastAPI、Pydantic 2、SQLAlchemy 2、Alembic、SQLite；
- 知识库：pypdf、sentence-transformers、`BAAI/bge-m3`、NumPy、FAISS `IndexFlatIP`；
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
│  │     ├─ material_processing/
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
├─ scripts/
│  ├─ acceptance_v1.py
│  └─ acceptance_v2.py
├─ .env.example
├─ V1_*.md
├─ V2_TASK.md
├─ V2_PROGRESS.md
└─ V2_COMPLETION_REPORT.md
```

## 环境要求

- Windows 10/11 与 PowerShell 5.1+；
- Python 3.11+；
- Node.js 20+ 与 npm 10+；
- 本机已有 `BAAI/bge-m3` Hugging Face 缓存。无需重新下载已有模型。

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

## 数据库迁移

```powershell
Set-Location .\backend
..\.venv\Scripts\alembic.exe upgrade head
..\.venv\Scripts\alembic.exe current
..\.venv\Scripts\alembic.exe heads
..\.venv\Scripts\alembic.exe check
Set-Location ..
```

当前 head 为 `20260730_0002`。重置本地开发数据库会删除本地数据：

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

### 语义检索是不是 AI 回答？

不是。结果是 BGE-M3 + FAISS 召回的原始资料片段，包含来源信息；V2 不调用 LLM。

更多说明见 [架构](docs/architecture.md)、[数据模型](docs/data-model.md) 与 [API](docs/api.md)。
