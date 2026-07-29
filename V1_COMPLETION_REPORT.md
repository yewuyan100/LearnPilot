# PersonalLearning V1 完成报告

报告日期：2026-07-29  
版本提交：`1b9de60 feat: complete personal learning agent v1`  
版本标签：`v1.0.0`  
当前 Alembic 版本：`20260729_0001 (head)`

## 1. V1 最终范围

V1 是一个本地优先、单用户使用的学习管理工作台，完成以下真实闭环：

```text
创建学习目标
→ 上传 PDF、Markdown 或 TXT 文件
→ 手动创建课程和知识点
→ 创建今日任务
→ 创建或恢复基础学习会话
→ 保存手动笔记并更新知识点、任务和会话状态
→ 今日页和进度页读取更新后的 SQLite 数据
```

V1 的实现范围包括：

- React + TypeScript + Vite 前端；
- FastAPI + Pydantic + SQLAlchemy 后端；
- SQLite 持久化与 Alembic 迁移；
- 学习目标、资料、课程、知识点、今日任务和基础学习会话 CRUD；
- PDF、Markdown、TXT 文件校验、保存、列表和同步删除；
- 六个左侧导航页面和一个基础学习会话页；
- 加载、空状态、失败、表单校验、删除确认和 Toast；
- Demo 数据脚本、后端测试、前端测试和真实 API 验收脚本。

## 2. 实际目录结构

以下为 V1 的源码与文档结构，不包含 `.git`、虚拟环境、`node_modules`、构建产物、SQLite 文件和上传文件：

```text
PersonalLearning/
├─ backend/
│  ├─ alembic/
│  │  ├─ env.py
│  │  ├─ script.py.mako
│  │  └─ versions/
│  │     └─ 20260729_0001_initial_v1.py
│  ├─ app/
│  │  ├─ api/
│  │  │  ├─ deps.py
│  │  │  ├─ router.py
│  │  │  └─ routes/
│  │  │     ├─ courses.py
│  │  │     ├─ daily_tasks.py
│  │  │     ├─ dashboard.py
│  │  │     ├─ demo.py
│  │  │     ├─ health.py
│  │  │     ├─ learning_goals.py
│  │  │     ├─ learning_sessions.py
│  │  │     └─ materials.py
│  │  ├─ core/
│  │  │  ├─ config.py
│  │  │  └─ errors.py
│  │  ├─ db/
│  │  │  ├─ base.py
│  │  │  └─ session.py
│  │  ├─ models/
│  │  │  ├─ course.py
│  │  │  ├─ daily_task.py
│  │  │  ├─ enums.py
│  │  │  ├─ knowledge_point.py
│  │  │  ├─ learning_goal.py
│  │  │  ├─ learning_session.py
│  │  │  └─ material.py
│  │  ├─ schemas/
│  │  │  ├─ common.py
│  │  │  ├─ course.py
│  │  │  ├─ daily_task.py
│  │  │  ├─ dashboard.py
│  │  │  ├─ learning_goal.py
│  │  │  ├─ learning_session.py
│  │  │  └─ material.py
│  │  ├─ services/
│  │  │  ├─ crud.py
│  │  │  ├─ demo.py
│  │  │  └─ materials.py
│  │  └─ main.py
│  ├─ tests/
│  │  ├─ conftest.py
│  │  ├─ test_courses_tasks_sessions.py
│  │  ├─ test_health_goals.py
│  │  └─ test_materials.py
│  ├─ alembic.ini
│  ├─ pyproject.toml
│  └─ requirements.txt
├─ frontend/
│  ├─ src/
│  │  ├─ api/
│  │  │  ├─ client.ts
│  │  │  └─ resources.ts
│  │  ├─ components/
│  │  ├─ layouts/AppLayout.tsx
│  │  ├─ pages/
│  │  │  ├─ CoursesPage.tsx
│  │  │  ├─ LearningSessionPage.tsx
│  │  │  ├─ MaterialsPage.tsx
│  │  │  ├─ ProgressPage.tsx
│  │  │  ├─ ReviewsPage.tsx
│  │  │  ├─ SettingsPage.tsx
│  │  │  └─ TodayPage.tsx
│  │  ├─ test/
│  │  ├─ types/
│  │  ├─ utils/
│  │  ├─ App.tsx
│  │  ├─ main.tsx
│  │  └─ styles.css
│  ├─ package.json
│  ├─ package-lock.json
│  └─ vite.config.ts
├─ docs/
│  ├─ api.md
│  ├─ architecture.md
│  └─ data-model.md
├─ scripts/
│  ├─ acceptance_v1.py
│  ├─ clear_demo.py
│  ├─ reset_database.ps1
│  └─ seed_demo.py
├─ .env.example
├─ .gitignore
├─ README.md
├─ tokens.css
├─ V1_PROGRESS.md
├─ V1_RESUME_AUDIT.md
└─ V1_TASK.md
```

## 3. 数据库表

V1 共有六张业务表。

### `learning_goals`

保存学习目标、描述、目标日期、每日分钟数、当前水平、状态、Demo 标记和时间戳。

状态：`active`、`paused`、`completed`、`archived`。

约束：`daily_minutes` 必须在 5–1440 之间。

### `materials`

保存文件标题、原始文件名、UUID 存储文件名、绝对文件路径、来源类型、MIME、字节数、保存状态、错误信息和时间戳。

状态：`uploaded`、`ready`、`failed`。V1 的 `ready` 仅表示文件已经成功保存，不表示已解析或向量化。

### `courses`

保存所属学习目标、课程标题、描述、状态和时间戳。

状态：`draft`、`active`、`completed`、`archived`。

目标删除时课程使用 `CASCADE`。

### `knowledge_points`

保存所属课程、标题、描述、顺序、预计时间、状态和时间戳。

状态：`not_started`、`learning`、`completed`、`locked`。

约束：同一课程内 `order_index` 唯一，`estimated_minutes >= 1`。

### `daily_tasks`

保存目标、可选课程、可选知识点、标题、任务类型、预计时间、计划日期、状态和时间戳。

状态：`pending`、`in_progress`、`completed`、`skipped`。

课程或知识点删除时对应外键使用 `SET NULL`。

### `learning_sessions`

保存目标、可选课程、可选知识点、可选今日任务、开始/结束时间、会话状态、手动笔记和时间戳。

状态：`active`、`paused`、`completed`、`cancelled`。

相同今日任务存在活动或暂停会话时，创建接口返回已有会话，用于刷新恢复和防止重复活动会话。

## 4. API

所有路由挂载在 `/api`。

| 方法 | 路径 | V1 行为 |
|---|---|---|
| GET | `/api/health` | 健康检查 |
| GET | `/api/meta` | 应用、数据库和上传配置 |
| POST | `/api/learning-goals` | 创建目标 |
| GET | `/api/learning-goals` | 目标列表 |
| GET | `/api/learning-goals/{id}` | 目标详情 |
| PATCH | `/api/learning-goals/{id}` | 更新目标 |
| DELETE | `/api/learning-goals/{id}` | 删除目标 |
| POST | `/api/materials/upload` | 保存本地资料及元数据 |
| GET | `/api/materials` | 资料列表，支持名称搜索和类型筛选 |
| GET | `/api/materials/{id}` | 资料元数据详情 |
| DELETE | `/api/materials/{id}` | 删除数据库记录和本地文件 |
| POST | `/api/courses` | 创建课程 |
| GET | `/api/courses` | 课程列表 |
| GET | `/api/courses/{id}` | 课程详情 |
| PATCH | `/api/courses/{id}` | 更新课程 |
| DELETE | `/api/courses/{id}` | 删除课程 |
| POST | `/api/courses/{id}/knowledge-points` | 创建知识点 |
| GET | `/api/courses/{id}/knowledge-points` | 课程知识点列表 |
| PATCH | `/api/knowledge-points/{id}` | 更新知识点 |
| DELETE | `/api/knowledge-points/{id}` | 删除知识点 |
| GET | `/api/today` | 今日目标、任务、最近课程和会话 |
| POST | `/api/daily-tasks` | 创建任务 |
| PATCH | `/api/daily-tasks/{id}` | 更新任务 |
| DELETE | `/api/daily-tasks/{id}` | 删除任务 |
| POST | `/api/learning-sessions` | 创建或恢复会话 |
| GET | `/api/learning-sessions` | 会话列表 |
| GET | `/api/learning-sessions/{id}` | 会话详情 |
| PATCH | `/api/learning-sessions/{id}` | 更新笔记、状态及关联状态 |
| GET | `/api/progress` | 真实数据库进度聚合 |
| GET | `/api/review-items` | 未完成知识点和历史任务 |
| POST | `/api/demo-data` | 幂等导入 Demo |
| DELETE | `/api/demo-data` | 清理 Demo |

错误响应统一为：

```json
{
  "error": {
    "code": "error_code",
    "message": "面向用户的错误信息",
    "details": null
  }
}
```

## 5. 页面

| 路由 | 页面 | 已实现行为 |
|---|---|---|
| `/today` | 今日学习 | 当前目标、目标日期、每日时间、今日任务、最近课程、最近会话、开始/恢复学习 |
| `/courses` | 课程 | 课程 CRUD、知识点 CRUD、状态修改、手动课程结构 |
| `/materials` | 资料 | 拖拽/选择上传、搜索、类型筛选、状态和大小显示、删除确认 |
| `/reviews` | 复习 | 学习中/未开始知识点、历史未完成任务、手动加入今日 |
| `/progress` | 进度 | 目标、课程、知识点、任务和最近七天会话聚合 |
| `/settings` | 设置 | 后端、数据库、上传配置、Demo 导入和清理 |
| `/learning-sessions/{id}` | 学习会话 | 课程目录、手动笔记、知识点状态、暂停、继续、完成和结束 |

六个主页面使用统一左侧导航。移动端切换为顶部栏和抽屉导航。

## 6. 测试与验收结果

V1 完成时的实际结果：

- Alembic `upgrade head`：通过；
- Alembic `check`：通过，无待生成迁移；
- 当前迁移复核：`20260729_0001 (head)`；
- 后端 pytest：`9 passed`；
- Python `compileall`：通过；
- 前端 Vitest：`7 passed`；
- ESLint：通过；
- TypeScript 编译：通过；
- Vite 生产构建：通过；
- 后端健康检查：`{"status":"ok"}`；
- Vite 生产预览：HTTP 200；
- 桌面端和 390px 移动端浏览器检查：通过；
- 今日、课程、资料、复习、进度、设置、学习会话七个页面真实加载：通过。

六个真实 API 验收场景全部通过：

1. 目标创建并通过独立 GET 验证持久化；
2. PDF 与 Markdown 上传、元数据和 `ready` 状态验证；
3. 手动创建课程与六个知识点；
4. 今日任务出现在 `/api/today`；
5. 创建会话、保存笔记并完成知识点和任务；
6. 今日页和进度聚合反映完成状态。

验收脚本最后会删除验收资料及其本地文件，并删除验收学习目标。

## 7. 启动命令

### 安装

```powershell
Copy-Item .env.example .env

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r .\backend\requirements.txt

Set-Location .\frontend
npm install
Set-Location ..
```

### 数据库迁移

```powershell
Set-Location .\backend
..\.venv\Scripts\alembic.exe upgrade head
Set-Location ..
```

### 后端

```powershell
Set-Location .\backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 前端

```powershell
Set-Location .\frontend
npm run dev
```

默认前端地址为 `http://localhost:5173`，默认 API 地址为 `http://127.0.0.1:8000/api`。

### Demo

```powershell
.\.venv\Scripts\python.exe .\scripts\seed_demo.py
.\.venv\Scripts\python.exe .\scripts\clear_demo.py
```

## 8. 已知限制

- 单用户、本地 SQLite，不提供身份认证和多用户隔离；
- V1 仅按扩展名判断允许类型，MIME 由扩展名映射，不校验文件内容签名；
- `ready` 仅代表本地文件保存成功；
- 文件删除先提交数据库删除，再删除本地文件；数据库与文件系统之间不是跨资源原子事务；
- 资料详情接口只返回元数据，不返回文件内容或预览；
- 复习页仅使用知识点和任务状态，没有自动复习调度；
- 进度数据只做确定性数据库聚合，没有掌握度分数；
- 受限验收环境无法绑定 Vite 默认 5173，实际浏览器验收使用 4173；正常本地环境按 README 使用 5173；
- Recharts 位于独立进度页路由包，生产构建中该路由包约 369 kB。

## 9. 明确未实现能力

V1 没有实现或伪装实现以下能力：

- PDF、Markdown、TXT 正文解析；
- 文档清洗、标题识别、切片和 Chunk 表；
- Embedding、FAISS、pgvector 和向量索引；
- RAG、资料引用和资料问答；
- LLM Provider、Prompt、Structured Output；
- LangGraph、Agent、Checkpoint 和 SSE；
- AI 自动生成课程、讲解、题目、批改和总结；
- 掌握度算法、BKT、FSRS 和自动复习调度；
- MCP、GitHub、B站或其他外部资料源；
- Redis、Celery、消息队列、微服务和 Docker 编排；
- 登录、注册、多用户、云端部署、语音和视频。

本报告只记录已完成的 V1，不代表上述能力已经开始。
