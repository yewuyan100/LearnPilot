# V4 架构

PersonalLearning V4 仍是本地单体、单用户应用，不引入消息队列或微服务。V4 复用已有 SQLite、V2 BGE-M3/FAISS 和 V3 OpenAI-compatible LLM Provider。

```text
React + TanStack Query
          │ JSON / multipart
          ▼
FastAPI Router + Pydantic
          │
          ├─ V1 CRUD / 聚合 ───────── SQLAlchemy ── SQLite
          │
          └─ Material Pipeline
                ├─ Parser / Cleaner / Chunker
                ├─ Repository ─────── SQLite material_chunks
                ├─ BGE-M3 ────────── 本地 Hugging Face 缓存
                └─ FAISS Store ───── 索引文件 + Manifest
          │
          └─ Trusted RAG
                ├─ Query Rewriter（有限历史）
                ├─ V2 Retrieval + Candidate Filter
                ├─ Answerability Gate
                ├─ OpenAI-compatible Structured Output
                ├─ Citation Validator / Repair
                └─ SQLite Conversation / Message / Citation
```

## 分层

- `app/api/routes`：HTTP 参数、依赖注入、状态码和响应；
- `app/schemas`：Pydantic 数据契约；
- `app/repositories`：Material / MaterialChunk 查询、分页、批量替换和搜索回查；
- `app/services/material_processing`：Parser、Cleaner、Chunker 与处理编排；
- `app/services/embedding`：可注入 Embedding 协议和 BGE-M3 离线实现；
- `app/services/vector_store`：FAISS、Manifest、索引生命周期、搜索和进程内锁；
- `app/models` / `app/db`：SQLAlchemy、SQLite 外键与会话；
- `alembic`：显式增量迁移。

Router 不承载检索与生成编排；LLM 不直接读取数据库、不修改数据库，也不决定引用元数据。

## 一致性边界

Chunk 替换在单个 SQLite 事务内完成。解析失败时回滚，不覆盖上一批完整 Chunk。

SQLite、原文件和 FAISS 不是同一事务，因此采用：

- 原文件上传先独立可靠保存；
- Chunk 成功提交后才构建索引；
- FAISS 与 Manifest 通过临时文件、校验、备份恢复和原子替换保持完整；
- 索引失败不删除原文件或 Chunk；
- 搜索命中必须回查 SQLite，删除或无效 ID 不返回；
- 内容 checksum 用于识别 SQLite 与索引不一致。

## 前端

资料页保持 V1 视觉与 Query 模式，新增三个聚合组件：

- `MaterialIndexPanel`：索引状态与重建；
- `MaterialChunksDialog`：真实分页 Chunk；
- `MaterialSearchPanel`：非聊天式资料片段检索。

变更成功后失效 `["materials"]` 与 `["material-index"]`，不使用定时器伪造状态。

## V3 可信边界

- 用户问题与有限历史用于可选的独立查询改写；新增英文实体必须来自现有输入，否则回退原问题；
- V2 检索结果经过阈值、重复片段、单资料占比、来源数和字符预算限制；
- 没有足够来源时由确定性代码拒答，完全不调用 LLM；
- 资料片段被明确标记为不可信数据，其内部指令不得覆盖系统规则；
- 模型只能返回 Pydantic 结构；引用必须同时出现在正文和声明列表，并属于实际上下文；
- 首次引用校验失败只允许一次修复；再次失败时稳定拒答；
- SSE 先完成生成、解析、引用校验和数据库持久化，再分段发送最终安全内容；
- API Key、完整 Prompt、完整历史、完整资料正文不写日志。

## V4 学习活动调用链

```text
React 活动配置
→ FastAPI Router
→ ActivityGenerationService
   ├─ 范围校验与 V2 检索
   ├─ 去重和字符预算
   ├─ 不可信 Sources S1…Sn
   ├─ LLM Structured Output
   └─ Question / Source Validator → 原子保存 draft
→ 草稿管理 → 发布
→ QuizAttemptService
   ├─ ObjectiveGrader（纯代码）
   ├─ ShortAnswerGrader（LLM + Rubric）
   ├─ ScoreAggregator
   └─ WrongAnswerService
→ 结果、来源快照、学习会话与关联任务
```

活动生成和提交均以进程锁缩小并发竞态窗口，以数据库唯一约束保证最终幂等。Router 只负责 HTTP 契约；生成、验证、批改、聚合和错题分别由服务承担。LLM 不直接访问数据库，也不能直接修改分数、任务或学习状态。

## 一致性与安全边界

- 生成输出整体通过 Pydantic 与来源子集验证后，才在一个事务内保存；修复最多一次，失败不保留半批题目；
- 发布后题目核心字段不可原地修改，Attempt 保存独立答案与结果；
- 客观题只由确定性代码评分，简答题评分结果必须匹配已定义 Rubric；
- 批改失败保留 `failed`，不伪装成零分；同一提交可重试；
- QuestionSource 保存受限摘录和数据库确定的文件/页码/章节元数据，Material/Chunk 删除时外键置空；
- 资料和用户答案都被标记为不可信数据，完整 Prompt、API Key、完整正文和模型推理不进入日志。

## 版本边界

V4 提供资料约束的测验、批改和错题闭环，但不提供 LangGraph、Agent、掌握度、FSRS、自适应计划、多 Agent 或外部 MCP 资料源。
