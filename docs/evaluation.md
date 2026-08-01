# 测试、验收与评测

普通 pytest/Vitest 使用临时业务 SQLite、临时 Checkpoint、临时上传与 FAISS、FakeEmbedder/FakeLLM 和固定时间，不读取个人知识库、不加载真实 BGE-M3、不调用外部 LLM。

真实 acceptance_v2–v6 使用临时存储和真实 `BAAI/bge-m3`；V3–V6 还使用 `.env` 配置的真实 OpenAI-compatible LLM，只发送 `evals/fixtures` 的人工专用材料。V6 验收固定规则时间，验证真实出题/批改、证据、掌握度/置信度、快照、连续错误、错题复习、薄弱点、调度、建议、Agent 工具、确认前零写入、批准/拒绝、幂等、未评估、快速路由与停服重启恢复。

`evaluate_v6.py` 的 12 个固定合成场景计算 Evidence Collection Accuracy、Deduplication、Mastery/Confidence Determinism、范围、等级、薄弱点、到期/逾期、原因、No-Phantom-Mastery、No-Write-Before-Confirmation、Task Idempotency、Agent Tool Selection 与回归率，以及快速路由、LLM 调用和延迟指标。

本轮最终 V5 真实小型评测：平均 22547.73 ms、P50 12320.45 ms、P95 47062.32 ms。V6 明确只读快速路由使用 0 次 LLM，固定本地 V6 评测平均 0.062 ms、P50 0.059 ms、P95 0.142 ms；两者工作负载不同，只能用于说明确定性快速路径消除了模型往返，不能作为通用生产延迟对比或教育效果结论。

所有 1.0 指标仅说明仓库内固定契约通过，不代表真实教育效果、通用 Agent 能力或生产分布表现。
