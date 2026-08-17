# Agent 确认、恢复与幂等

AgentConversation 在创建时获得稳定的 `thread_id`。LangGraph checkpoint 使用独立 SQLite 保存中断状态；它与业务数据库分离。一次新运行和之后的确认恢复都必须使用原 thread ID，否则无法安全恢复原图状态。

写工具执行前，系统先在业务审计记录中保存 ToolCall 与 Confirmation，然后冻结待执行工具名和参数并计算 SHA-256 快照哈希。图在确认节点调用 interrupt。此时业务写入尚未发生，用户看到的是可检查的确认卡片，而不是已经执行后的通知。

确认接口校验决定是否冲突、确认是否过期、参数快照和哈希是否仍一致。批准后以 `Command(resume=...)` 恢复原运行，真正的业务写入只发生在恢复后的 write-tool 节点。拒绝不会执行写工具。

幂等性由多层约束共同提供：ToolCall 的 run ID 与 step index 唯一；业务写服务接受稳定 request ID；已经完成的确认会重放原结果。重复批准不能再次创建任务或第二次修改同一业务对象。相同 request ID 若被用于不同输入，应该返回冲突而不是覆盖历史。

Checkpoint 解决的是工作流恢复，不是业务事实持久化。即使图可以恢复，写入正确性仍依赖业务事务、唯一约束和幂等 request ID。评测问题应区分这两个概念，避免把“有 checkpoint”错误等同于“任意写入天然只执行一次”。
