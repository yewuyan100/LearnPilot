# 最终架构

```text
React / TypeScript
        ↓ JSON / SSE
FastAPI + Pydantic
        ├─ V1 Learning Management ───────────────┐
        ├─ V2 Knowledge Base → BGE-M3 → FAISS   │
        ├─ V3 Grounded RAG → OpenAI-compatible  │
        ├─ V4 Activities / Grading / Wrongs     ├→ SQLite 业务数据库
        ├─ V5 LangGraph Single Agent ───────────┤
        │       └→ SQLite Checkpoint            │
        └─ V6 Adaptive Learning                 │
                Evidence → Mastery/Confidence   │
                → Snapshot → Weak Point         │
                → Schedule → Recommendation ────┘
```

应用保持本地单体、单用户、单进程。SQLite 保存业务事实，独立 SQLite 保存 LangGraph Checkpoint，FAISS 保存向量索引，Manifest 将索引与 MaterialChunk/模型版本绑定。BGE-M3 负责 embedding；OpenAI-compatible LLM 只用于可信问答、资料约束出题、rubric 简答批改、Agent 分类/有限规划，以及可选的原因文字整理。

分层：API route 负责 HTTP 契约；Pydantic schema 负责输入输出验证；service 负责业务事务；repository 负责资料查询；SQLAlchemy model 负责持久化；LangGraph 只通过 ToolRegistry 调用服务，不能直接操作数据库。

V6 自适应刷新在主业务提交后运行，失败可诊断并可幂等重建。规则算法不依赖 LLM。明确只读请求可跳过分类/规划 LLM，直接进入经 Schema 和 Tool Registry 校验的单个读工具；任何写入仍经过 Planner、参数冻结、interrupt、人工确认和 Command(resume)。

安全边界：资料、用户输入和历史消息均不可信；检索内容不能覆盖系统规则；RAG 只允许引用实际送入模型的来源；客观批改纯代码；简答批改失败不伪装零分；Agent 不提供删除、改分、答案/rubric 修改、代码、shell、SQL、任意文件、网络、环境变量或密钥工具。
