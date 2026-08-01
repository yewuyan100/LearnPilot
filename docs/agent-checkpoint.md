# Agent Checkpoint 与恢复

Checkpoint 默认启用并写入 `./data/agent_checkpoints.sqlite`，与主业务 SQLite 分离。每个 AgentConversation 创建一次稳定随机 `thread_id`，新运行和确认恢复都使用同一值。写工具前，图先写入审计 ToolCall 与 Confirmation，再在 `await_confirmation` 调用 `interrupt()`。

确认接口校验 TTL、决定冲突、参数快照及 SHA-256 哈希，然后使用 `Command(resume=...)` 恢复。业务写入只位于恢复后的 `execute_write_tool`。ToolCall 的 `(run_id, step_index)` 唯一约束、业务服务自身的 request id，以及已完成结果重放共同防止重复执行。应用 lifespan 初始化 saver 并在关闭时释放连接；Windows 使用 `tzdata` 注入 `Asia/Shanghai` 时间。
