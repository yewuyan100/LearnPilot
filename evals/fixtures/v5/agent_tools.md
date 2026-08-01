# PersonalLearning Agent 工具原则

学习 Agent 只能调用登记在允许列表中的工具。查询工具可以直接执行；任何会改变学习数据的工具都必须先生成确认卡片，并在用户批准后执行。

一次运行最多包含四个工具步骤，最多三个查询工具和一个写工具。复合计划必须先查询、后写入，禁止写入后继续查询，也禁止循环调用。

Checkpoint 使用稳定的 thread_id 保存中断状态。恢复确认时必须使用原 thread_id，并验证待执行参数快照的哈希；重复批准只能返回同一业务结果，不能再次写入。

应用流式接口只发送 accepted、status、tool_start、tool_result、confirmation_required、message_start、delta、citations、done 和 error 等事件，不发送图状态、节点名、内部计划、思维链或系统提示。
