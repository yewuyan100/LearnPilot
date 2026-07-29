# V2 架构

PersonalLearning V2 仍是本地单体、单用户应用，不引入消息队列、微服务或外部模型 API。

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

Router 不承载解析或向量逻辑；LLM 不参与任何 V2 流程。

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

## 边界

V2 只提供资料处理、Embedding、向量索引和来源检索。RAG 答案、LLM、LangGraph、Agent、OCR、自动课程和教学逻辑不在本版本。
