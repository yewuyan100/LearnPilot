# V3 架构

PersonalLearning V3 仍是本地单体、单用户应用，不引入消息队列或微服务。外部依赖仅增加一个可配置的 OpenAI-compatible LLM。

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

## 版本边界

V3 提供可信引用式问答，但不提供 LangGraph、Agent、工具调用、OCR、自动课程和教学闭环。
