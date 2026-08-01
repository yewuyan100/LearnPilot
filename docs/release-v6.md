# V6 发布与验收

环境：Windows 10/11、Python 3.11+、Node 20+、npm 10+、本地 `BAAI/bge-m3` 缓存，以及可选的 OpenAI-compatible LLM。复制 `.env.example` 为 `.env`，填写本地路径与 LLM 配置；不要提交 `.env` 或密钥。

迁移与启动：

```powershell
Set-Location backend
..\.venv\Scripts\alembic.exe upgrade head
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

前端：`Set-Location frontend; npm run dev`。

全量验证：后端 `pytest`、`compileall`、Alembic current/heads/check 和 `0006 → 0005 → 0006`；前端 test/lint/build；根目录执行 `acceptance_v1.py` 至 `acceptance_v6.py`，以及 `evaluate_v3.py` 至 `evaluate_v6.py`。V2–V6 真实验收需要本地 BGE-M3；V3–V6 还会把 `evals/fixtures` 下明确标记的专用人工夹具发送给配置的 LLM。

演示：`python scripts/seed_demo.py` 可重复执行且只创建 `[DEMO]` 数据；`python scripts/clear_demo.py` 只清理 `is_demo=true` 目标及其演示活动/测验/错题/掌握度关联。

V6 发布标签为 `v6.0.0`。发布后 PersonalLearning 主线架构冻结，不自动开启 V7。
