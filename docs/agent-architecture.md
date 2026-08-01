# V5 单学习 Agent 架构

V5 只包含一个学习 Agent，不包含 supervisor、多 Agent 或外部 MCP。编排使用显式 `StateGraph`，节点为：`load_context`、`classify_request`、`plan_actions`、`validate_plan`、`execute_read_tool`、`evaluate_tool_result`、`prepare_confirmation`、`await_confirmation`、`execute_write_tool`、`compose_response`、`persist_result`、`handle_failure`。

状态只保存可序列化业务字段：会话/运行/线程/请求标识、裁剪历史、注入的本地时间、意图、计划、当前步骤、待确认工具及参数哈希、结果、引用、错误和终态。服务依赖通过图构造上下文注入，不进入 checkpoint。每个稳定 `thread_id` 使用进程内 `asyncio.Lock` 串行化，最大四步、三个查询、一个写入。

模型只负责分类、受限规划和资料答案结构化输出；它不能直接访问数据库或执行业务写入。查询和写入都由注册工具包装既有 V2–V4 服务。
