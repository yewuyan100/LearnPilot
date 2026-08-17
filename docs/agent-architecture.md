# LearnPilot AI Orchestration

AI / Agent 的 canonical 说明已合并到 [LearnPilot Architecture](architecture.md)，本文件只保留入口，避免维护第二份架构事实。

当前 production 不是单一“万能 Agent”，也不是自主 multi-agent supervisor：

- Learning Runtime 装载带版本的 Learner Context，执行 policy checks，并以确定性 Router 选择 curriculum、tutor 或 operations capability；
- Curriculum 只产生等待审查的 proposal；Tutor 只在当前资料 scope 内检索、解释并校验引用；
- Operations Adapter 委托既有 LangGraph workflow，最多 4 steps / 3 reads / 1 write，写入通过 `interrupt` 等待人工确认；
- Harness Run、Learning Event、request ID、thread lock 与 SQLite checkpoint 支持幂等、审计和 resume；
- 不提供 Supervisor、MCP、任意 shell / SQL / 文件 / secret / web tools。

接口、Seam、失败策略和状态所有权以 [Architecture](architecture.md) 为准。
