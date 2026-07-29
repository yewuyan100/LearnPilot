# PersonalLearning

PersonalLearning 是一个本地优先、单用户使用的个人学习管理工作台。本仓库当前交付的是 **V1：项目骨架、核心 UI、数据库模型与基础 CRUD**。

V1 已打通这条真实链路：

```text
创建学习目标 → 上传本地资料 → 手动建立课程与知识点
→ 创建今日任务 → 开始学习 → 保存笔记与状态
→ 完成会话 → 首页和进度页读取更新后的数据
```

所有业务数据来自 FastAPI 与 SQLite；前端没有硬编码 Demo 课程。

## V1 功能

- 学习目标 CRUD；
- PDF、Markdown、TXT 文件校验、受控保存、元数据管理与同步删除；
- 课程和知识点 CRUD；
- 今日任务 CRUD 与今日首页聚合；
- 基础学习会话创建、恢复、暂停、继续、笔记和完成；
- 真实数据库聚合的复习基础页与进度页；
- Demo 数据导入和清理；
- 统一加载、空状态、错误、确认、表单校验和 Toast 反馈；
- Alembic 迁移、后端测试、前端测试和六场景验收脚本。

## 当前未实现

V1 不包含 LLM、LangGraph、Agent、Prompt、Structured Output、Embedding、FAISS、RAG、PDF 正文解析、AI 课程生成、自动出题或批改、掌握度算法、自动复习调度、SSE、MCP、外部资料源、多用户、登录、定时任务、云部署、Docker 编排、Redis、Celery 或微服务。

## 技术栈

- 前端：React 19、TypeScript、Vite、React Router、TanStack Query、Lucide React、Recharts；
- 后端：Python 3.11、FastAPI、Pydantic 2、SQLAlchemy 2、Alembic、SQLite；
- 测试：pytest、FastAPI TestClient、Vitest、Testing Library、ESLint。

## 目录结构

```text
PersonalLearning/
├─ backend/
│  ├─ alembic/
│  ├─ app/
│  │  ├─ api/
│  │  ├─ core/
│  │  ├─ db/
│  │  ├─ models/
│  │  ├─ schemas/
│  │  └─ services/
│  └─ tests/
├─ frontend/
│  └─ src/
│     ├─ api/
│     ├─ components/
│     ├─ layouts/
│     ├─ pages/
│     ├─ test/
│     ├─ types/
│     └─ utils/
├─ docs/
├─ scripts/
├─ .env.example
├─ V1_TASK.md
├─ V1_PROGRESS.md
└─ V1_RESUME_AUDIT.md
```

## 环境要求

- Windows 10/11 与 PowerShell 5.1+；
- Python 3.11+；
- Node.js 20+ 与 npm 10+。

## Windows PowerShell 安装

在项目根目录执行：

```powershell
Copy-Item .env.example .env

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r .\backend\requirements.txt

Set-Location .\frontend
npm install
Set-Location ..
```

如果 PowerShell 阻止激活虚拟环境，可以在当前窗口执行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

## 数据库迁移

首次初始化或升级数据库：

```powershell
.\.venv\Scripts\Activate.ps1
Set-Location .\backend
alembic upgrade head
Set-Location ..
```

查看当前迁移：

```powershell
Set-Location .\backend
alembic current
alembic history
Set-Location ..
```

模型变更后生成新迁移：

```powershell
Set-Location .\backend
alembic revision --autogenerate -m "describe change"
alembic upgrade head
Set-Location ..
```

重置本地开发数据库（会删除本地 SQLite 数据）：

```powershell
.\scripts\reset_database.ps1
```

## 启动后端

打开一个 PowerShell 窗口：

```powershell
.\.venv\Scripts\Activate.ps1
Set-Location .\backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- 健康检查：`http://127.0.0.1:8000/api/health`
- OpenAPI：`http://127.0.0.1:8000/docs`

## 启动前端

打开另一个 PowerShell 窗口：

```powershell
Set-Location .\frontend
npm run dev
```

浏览器打开 `http://localhost:5173`。

## Demo 数据

导入 Demo 数据：

```powershell
.\.venv\Scripts\python.exe .\scripts\seed_demo.py
```

重复执行不会创建副本。清理 Demo 数据：

```powershell
.\.venv\Scripts\python.exe .\scripts\clear_demo.py
```

Demo 数据包含“三周入门 MCP”目标、“MCP 基础”课程、六个知识点和一个今日任务，并以 `is_demo` 标记。

## 测试与构建

后端：

```powershell
Set-Location .\backend
..\.venv\Scripts\python.exe -m pytest -q
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

真实 API 验收脚本（需要先启动后端）：

```powershell
.\.venv\Scripts\python.exe .\scripts\acceptance_v1.py
```

## 配置

复制 `.env.example` 为 `.env` 后可修改：

- `DATABASE_URL`：SQLite 连接；
- `UPLOAD_DIR`：上传目录；
- `MAX_UPLOAD_SIZE_MB`：单文件大小限制；
- `ALLOWED_FILE_EXTENSIONS`：允许的扩展名；
- `CORS_ORIGINS`：本地前端来源；
- `DEMO_DATA_ENABLED`：只影响设置页展示，不会自动导入数据；
- `VITE_API_BASE_URL`：前端 API 地址。

用户上传内容位于 `backend/uploads/`，数据库位于 `backend/data/`，二者均已加入 `.gitignore`。

## 常见问题

### 前端显示“无法连接后端”

确认后端正在 `127.0.0.1:8000` 运行，并检查 `.env` 中的 `VITE_API_BASE_URL` 与 `CORS_ORIGINS`。

### 上传被拒绝

V1 只允许 `.pdf`、`.md`、`.markdown`、`.txt`。默认上限为 20 MB。错误响应会说明是类型还是大小问题。

### 数据库表不存在

在 `backend` 目录执行 `alembic upgrade head`，不要依赖应用启动时隐式建表。

### 如何恢复干净 Demo

先执行 `clear_demo.py`，再执行 `seed_demo.py`。脚本只处理带 `is_demo` 标记的数据。

### 为什么资料没有正文预览或 AI 问答

V1 只保存文件和元数据。解析、切片、向量索引与 Agent 教学属于后续版本。

更多设计说明见 [架构](docs/architecture.md)、[数据模型](docs/data-model.md) 与 [API](docs/api.md)。
