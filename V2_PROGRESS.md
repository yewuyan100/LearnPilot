# PersonalLearning V2 进度

最后更新：2026-07-30

## 开发前真实基线

- 工作区：干净；
- 实际 HEAD：`4ccd352 docs: add v1 completion and v2 handoff`；
- 当前标签：`v1.0.0`，指向 `4ccd352`；
- 附件写明的 `1b9de60` 是 V1 业务完成提交，但随后已有文档提交 `4ccd352`；
- Alembic current：`20260729_0001 (head)`；
- Alembic heads：`20260729_0001 (head)`；
- Alembic check：通过，无待生成变更；
- 后端 pytest：`9 passed`；
- Python compileall：通过；
- 前端 Vitest：`7 passed`；
- ESLint：通过；
- TypeScript：通过；
- Vite production build：通过。

## 已完成

- 阅读 `V1_COMPLETION_REPORT.md`、`V2_HANDOFF.md`、`V1_TASK.md`、`V1_PROGRESS.md`、`README.md`、`docs/api.md`、`docs/data-model.md` 和 `.env.example`；
- 对照实际 Material Model、Schema、Service、Router、前端 API、页面、迁移和测试；
- 确认 V1 没有独立 Material Repository；
- 确认 V1 `processing_status=ready` 仅表示文件保存成功；
- 新增 `20260730_0002` 增量迁移、Material V2 字段和 `material_chunks`；
- 实现 TXT、Markdown、PDF Parser，确定性 Cleaner、Chunker 和事务性 Pipeline；
- 实现 BGE-M3 离线懒加载、批量归一化 `float32` Embedding 和 FakeEmbedder 注入；
- 实现 FAISS `IndexFlatIP`、Manifest、一致性校验、原子全量重建和进程内锁；
- 实现资料处理、Chunk 分页、索引状态、全量重建和语义检索 API；
- 完成资料知识库页面、状态/错误、Chunk 对话框、检索测试区和索引管理；
- 默认后端测试：`46 passed`；
- Python compileall：通过；
- Alembic upgrade/current/heads/check：`20260730_0002 (head)`，通过；
- 前端测试：`13 passed`；
- ESLint、TypeScript 和生产构建：通过；
- V1 六场景真实 API 回归：`passed`；
- V2 真实 HTTP 验收：`passed`；
- 真实模型：`BAAI/bge-m3`，维度 `1024`，离线加载通过；
- V2 验收处理 TXT、Markdown、可提取文本 PDF 共 3 份；
- FAISS 重启恢复、重新处理幂等、删除后不召回均通过；
- 更新 README、API、数据模型和完成报告。

## 进行中

- 无。V2 已完成全套检查与版本收口。

## 尚未完成

- V2 范围内无未完成项。LLM、RAG 最终回答、LangGraph、Agent、OCR 等继续留在后续版本。

## 真实验收结果

```json
{
  "status": "passed",
  "embedding_model": "BAAI/bge-m3",
  "embedding_dimension": 1024,
  "materials_processed": 3,
  "index_available": true,
  "search_verified": true,
  "restart_verified": true,
  "reprocessing_idempotent": true,
  "deletion_verified": true
}
```

验收脚本通过 HTTP API 工作，并自行使用临时 SQLite、上传目录、FAISS 文件启动和重启隔离后端；不直接操作数据库代替验收。

## 验证纪律

- 默认测试使用临时 SQLite、上传目录、FAISS 目录和 FakeEmbedder；
- 默认 pytest 不加载真实 BGE-M3；
- 真实 BGE-M3 只在独立验收中执行；
- 未实际运行的项目不记录为通过。
