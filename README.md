# PersonalLearning

PersonalLearning 是本地优先、单用户使用的完整学习工作台。当前版本 **V6：掌握度、自适应复习与最终工程收官**，项目已完成主线开发。

## V1–V6 能力

- V1：学习目标、课程、知识点、今日任务、学习会话、笔记与进度。
- V2：PDF / Markdown / TXT 解析、清洗、切片、本地 BGE-M3、FAISS、Manifest、语义检索与来源定位。
- V3：Query Rewrite、Answerability Gate、OpenAI-compatible Structured Output、引用校验/修复、拒答、会话、幂等与 SSE。
- V4：资料约束的四类题型、草稿/发布、客观题确定性批改、简答题 rubric 受控批改、错题与复习、来源快照。
- V5：显式 LangGraph 单学习 Agent、有限计划、受控工具、写前人工确认、SQLite Checkpoint、稳定 thread_id、审计、幂等与 SSE。
- V6：真实学习证据、确定性掌握度与置信度、不可变快照、薄弱点、复习调度、自适应建议、Agent 掌握度工具、确认后创建复习任务、快速只读路由、全链路评测与发布收口。

核心闭环：

```text
学习/任务/测验/错题复习
→ 不可变 MasteryEvidence
→ mastery-rule-v1 掌握度与置信度
→ MasterySnapshot
→ 薄弱点与 ReviewSchedule
→ AdaptiveRecommendation
→ Agent 查询
→ 用户确认
→ 真实 DailyTask
→ 新学习记录进入下一轮计算
```

掌握度只来自数据库真实记录，LLM 不计算或修改数值。无证据显示“未评估”，不显示虚假 0 分。权重、半衰期、阈值和复习间隔是可配置的项目初始工程规则，不是教育科学定论。

## 技术栈

- 前端：React 19、TypeScript、Vite、React Router、TanStack Query、Lucide React、ECharts。
- 后端：Python、FastAPI、Pydantic 2、SQLAlchemy 2、Alembic、SQLite。
- 知识库：pypdf、sentence-transformers、`BAAI/bge-m3`、NumPy、FAISS `IndexFlatIP`。
- AI：OpenAI-compatible Chat Completions、Pydantic Structured Output、LangGraph 1.2.10、SQLite Checkpoint。
- 质量：pytest、FastAPI TestClient、Vitest、Testing Library、ESLint、V1–V6 acceptance 与 V3–V6 evaluation。

## 安装

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
Set-Location frontend
npm install
Set-Location ..
```

在 `.env` 配置本地模型缓存。真实 RAG、出题、简答批改和 Agent 规划还需要 `LLM_API_KEY`、`LLM_BASE_URL` 与 `LLM_MODEL`；不要提交 `.env` 或密钥。

## 数据库与启动

```powershell
Set-Location backend
..\.venv\Scripts\alembic.exe upgrade head
..\.venv\Scripts\alembic.exe current
..\.venv\Scripts\alembic.exe heads
..\.venv\Scripts\alembic.exe check
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

另一个终端：

```powershell
Set-Location frontend
npm run dev
```

前端：`http://localhost:5173`；OpenAPI：`http://127.0.0.1:8000/docs`。主要入口包括 `/agent`、`/mastery`、`/reviews`、`/activities`、`/wrong-answers`、`/rag` 与 `/materials`。

## 测试、验收与评测

普通测试使用临时 SQLite、临时 Checkpoint、临时上传/FAISS、FakeEmbedder 与 FakeLLM，不加载真实模型、不扫描个人资料、不修改开发知识库。

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe -m compileall app ..\scripts
Set-Location ..\frontend
npm run test
npm run lint
npm run build
```

真实隔离验收：

```powershell
$env:HF_HOME = "D:\AIModels\HuggingFace"
$env:HF_HUB_OFFLINE = "1"
.\.venv\Scripts\python.exe .\scripts\acceptance_v1.py --isolated
.\.venv\Scripts\python.exe .\scripts\acceptance_v2.py
.\.venv\Scripts\python.exe .\scripts\acceptance_v3.py
.\.venv\Scripts\python.exe .\scripts\acceptance_v4.py
.\.venv\Scripts\python.exe .\scripts\acceptance_v5.py
.\.venv\Scripts\python.exe .\scripts\acceptance_v6.py
```

V3–V6 真实评测/验收只会发送 `evals/fixtures` 下的专用人工夹具，不读取个人知识库。固定小型评测集只验证仓库契约，不代表通用 Agent 能力或教育效果。

## 演示数据

```powershell
.\.venv\Scripts\python.exe .\scripts\seed_demo.py
.\.venv\Scripts\python.exe .\scripts\clear_demo.py
```

脚本只管理带 `is_demo=true` 和 `[DEMO]` 标记的数据，可重复执行，不使用个人资料。

## 安全与边界

模型不能直接访问数据库。一次 Agent Run 最多四步、三次查询和一次写入；写工具必须经过不可变参数快照、人工确认与 Checkpoint 恢复。快速路由只用于明确的低风险读取，写请求不能跳过 Planner 或 Confirmation。日志和响应不包含 Key、完整 Prompt、完整长答案、Graph State 或思维链。

本主线未实现多 Agent、Supervisor、MCP 外部资料源、联网搜索、OCR、图片/音视频理解、多用户、权限系统、云部署、微服务和复杂机器学习掌握度模型。这些是未来可选扩展，不属于 PersonalLearning 主线完成条件。

详细说明见 [架构](docs/architecture.md)、[API](docs/api.md)、[数据模型](docs/data-model.md)、[自适应闭环](docs/adaptive-learning.md)、[掌握度算法](docs/mastery-algorithm.md)、[复习调度](docs/review-scheduling.md)、[Agent 架构](docs/agent-architecture.md)、[评测](docs/evaluation.md)、[面试指南](docs/interview-guide.md) 与 [V6 发布](docs/release-v6.md)。
