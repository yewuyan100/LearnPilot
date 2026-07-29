# PersonalLearning V3 进度

最后更新：2026-07-30

## 开发前真实基线

- 工作区：干净；
- HEAD：`2ccbcabeb6f157e32a7784e113ea34253d945d57`；
- 提交：`feat: add local material knowledge indexing and semantic search`；
- 标签：`v2.0.0`；
- Alembic current / heads：`20260730_0002 (head)`；
- Alembic check：通过；
- 后端 pytest：`46 passed`；
- Python compileall：通过；
- 前端 Vitest：`13 passed`；
- ESLint、TypeScript、Vite production build：通过；
- V1 隔离真实 HTTP 验收：`passed`；
- V2 真实 BGE-M3 HTTP 验收：`passed`，实际维度 1024。

## 配置审查

- 最终预检确认 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL` 均已配置；
- 只检查是否存在，不输出配置值；
- 普通测试继续使用 FakeLLM；真实 V3 验收与评测使用用户配置的真实 Provider。

## 已完成

- 完整读取 V3 附件要求；
- 阅读 README、V2 完成报告、任务、进度、API、数据模型和环境示例；
- 核对 V2 Material、MaterialChunk、Embedding、FAISS、Manifest、API 与前端链路；
- 完成全部开发前基线检查和 V1/V2 回归。
- 新增 `20260730_0003` 增量迁移；实际升级到 head，Alembic check 无差异；
- 新增 RAG 会话、消息和引用快照模型、Schema、Repository 与 CRUD API；
- 实现 OpenAI-compatible Structured Output Provider、有限历史改写、V2 检索复用、候选筛选、上下文预算和确定性拒答；
- 实现引用合法性校验、一次修复、幂等 request_id、同步问答和校验后 SSE；
- 实现 `/rag` 资料问答页、会话恢复、资料范围、引用详情、AbortController；
- 新增隔离 RAG 后端测试与前端测试；后端当前 `58 passed`，前端当前 `15 passed`；
- 新增 3 份可核验资料、8 个评测问题、评测脚本和隔离真实验收脚本。
- V3 真实 LLM 验收通过：真实回答、追问、资料范围、拒答、Prompt Injection、幂等、SSE、重启、引用快照和删除来源清理均已验证；
- 隔离真实评测完成：8 个案例全部有效，Hit@K、来源精度、引用合法率、引用覆盖率、拒答准确率、可回答准确率均为 1.0，无效输出率为 0；
- V1 隔离回归、V2 真实 BGE-M3 回归、Alembic、compileall、前后端测试、Lint 和 Build 全部重新通过。

## 进行中

- 无。V3 已完成并完成 Git 收口。

## 尚未完成

- 无。

## 验证纪律

- 默认测试隔离 SQLite、上传、FAISS、Embedding 和 LLM；
- 日志、API、Git 不输出 API Key、完整 Prompt、完整历史或完整资料；
- 未运行的检查不记录为通过；
- 未配置真实 LLM 时不创建 V3 标签。
