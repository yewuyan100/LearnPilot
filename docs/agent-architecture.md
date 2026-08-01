# Agent 架构

V6 保留 V5 单一显式 LangGraph StateGraph，不引入多 Agent 或 Supervisor。标准路径仍是上下文加载、分类、有限计划、校验、只读执行、结果评估、确认准备、interrupt、恢复写入、模板响应和持久化；最多四步、三次读取、一次写入，禁止写后读取。

明确的今日任务、错题、知识点掌握度、薄弱点、到期复习和建议查询可走确定性快速路由：先匹配小型稳定模式，仍生成合法意图和参数，再经过同一个计划校验与 ToolRegistry 执行；Planner 跳过，简单结果用模板组合。模糊请求继续调用模型，写请求绝不命中快速路径。

每个 Run 将 `fast_route_used`、`planner_skipped`、`composer_skipped`、`llm_call_count`、总延迟和工具耗时作为可观测性能信息返回/聚合。Checkpoint 与业务库继续分离，V6 掌握度数据库记录不是 Graph State。
