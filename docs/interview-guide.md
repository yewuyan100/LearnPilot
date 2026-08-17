# LearnPilot 面试指南

## 两分钟介绍

LearnPilot 是本地优先的单用户学习工作台。V1 管理目标、课程、知识点、任务和会话；V2 用 BGE-M3 与 FAISS 建本地资料库；V3 提供带来源快照和引用校验的可信 RAG；V4 把资料变成四类测验并区分确定性客观批改和受控简答批改；V5 用显式 LangGraph 单 Agent、SQLite Checkpoint 与人工确认编排受控工具；V6 用真实学习证据和版本化规则计算掌握度与置信度，再生成复习建议。当前架构以 `docs/architecture.md` 为准。

## 一次请求调用链

React → FastAPI/Pydantic → 业务服务 → SQLite。资料查询还会经过 BGE-M3 → FAISS → Answerability Gate → OpenAI-compatible Structured Output → Citation Validator。Agent 请求经过分类 → 有限计划 → Schema 校验 → 注册工具 → 写前 interrupt → 恢复执行 → 审计与响应。V6 学习事件在主事务提交后进入 Evidence → Mastery/Confidence → Snapshot → Weak Point → Schedule → Recommendation。

## 关键取舍

- BGE-M3：统一处理中文与英文语义检索，本地缓存可离线运行；代价是模型体积和 CPU 延迟。
- FAISS：单机向量检索简单、快速、可与 SQLite 清晰分工；不适合多机实时共享。
- 防幻觉：检索门控、受控上下文、Structured Output、引用白名单与一次修复；资料不足时拒答。
- 显式 StateGraph：节点、状态、边和中断点可测试、可审计；比自由 Agent 更受控，但灵活性较低。
- Checkpoint 与业务库：Checkpoint 保存图执行位置；业务库保存用户事实和审计。分离可避免把临时 Graph State 当业务真相。
- 人工确认：写工具先冻结参数与哈希并 `interrupt()`；批准后用同一 `thread_id` 和 `Command(resume)` 恢复，写入只存在于恢复后的节点。
- 幂等：HTTP request_id、业务唯一约束、工具调用 `(run_id, step_index)`、确认快照哈希和已完成结果重放共同防重复写。
- 批改：客观题纯代码确定性比较；简答题只允许依据固定 rubric 的结构化受控 LLM 评分，失败不记零分证据。
- 掌握度不用 LLM：数值结论必须同输入同结果、可解释、可回放、可版本化。LLM 只可润色既定原因。

## 已知限制与指标解释

单用户、本地 SQLite、单进程、无 OCR、无外部 MCP、无联网搜索、无多 Agent、无云部署。规则掌握度不是科学测评模型；固定小评测集的 1.0 只说明仓库内契约得到满足，不说明真实学习效果或生产分布表现。V5 延迟基线来自真实小型评测，V6 快速路由只改善模式明确的只读请求。
