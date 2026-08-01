# V6 任务

完整实现 PersonalLearning 最终主线版本：以真实学习记录形成确定性、可解释、可追溯的知识点掌握度与置信度，生成薄弱点、复习计划和自适应建议；扩展 V5 单 Agent 的只读工具，并在既有人工确认、Checkpoint 与幂等边界内创建真实复习任务。完成性能优化、隔离测试、真实验收、评测、演示数据、文档、提交与 `v6.0.0` 发布。

明确不实现多 Agent、Supervisor、MCP 外部资料源、联网搜索、OCR、多用户、云部署和复杂机器学习掌握度模型；这些不属于 PersonalLearning 主线完成条件。

## 开发前基线（2026-08-01）

- Git：`d1689d549f0f658d752015e1645d96c72486afd6`，tag `v5.0.0`，Alembic `20260801_0005 (head)`。
- 发现并保护既有未提交修改：`V5_COMPLETION_REPORT.md` 被改为仅保留标题标记；V6 不覆盖、不回退该修改。
- 后端：79 项 pytest 通过；compileall 通过；Alembic current/heads/check 通过。
- 前端：20 项测试通过；ESLint 通过；生产构建通过。
- V1：passed。
- V2：passed，真实 `BAAI/bge-m3`，1024 维，重启与幂等通过。
- V3：passed，真实 LLM、引用快照、SSE 与重启持久化通过。
- V4：passed，`BAAI/bge-m3` + `deepseek-v4-flash`，生成、批改、错题、幂等和重启通过。
- V5：passed，`BAAI/bge-m3` + `deepseek-v4-flash`，确认前零写入、批准/拒绝、Checkpoint 重启恢复和只写一次通过。
