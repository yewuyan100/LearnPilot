# 数据模型

V1–V5 表继续保存学习管理、资料/Chunk、RAG 会话与引用快照、活动/题目/来源、Attempt/Answer、错题和 Agent 审计/确认。

V6 迁移 `20260801_0006` 新增：

- `knowledge_masteries`：每知识点唯一当前状态；nullable mastery、confidence、level、证据数、最近证据/练习/复习、下次复习、算法版本和计算时间。
- `mastery_evidence`：不可变事实；知识点、类型、来源类型/ID、发生时间、原始值、归一化分、配置权重、必要摘要和内容哈希。`source_type + source_id + evidence_type` 唯一。
- `mastery_snapshots`：不可变历史；分数、置信度、等级、证据数/摘要、算法版本、触发类型/来源和计算时间。
- `review_schedules`：知识点、状态、优先分、建议/到期时间、原因、来源快照和完成任务；SQLite 部分唯一索引保证每知识点最多一个 pending/scheduled。
- `adaptive_recommendations`：V6 实现 `review_task`；状态、优先级、标题、原因事实、建议日期/时长、来源快照和创建任务。

删除知识点会级联删除 V6 计算记录；删除来源业务记录不会抹去独立证据摘要和历史快照。删除任务只会将 Schedule/Recommendation 的任务外键置空。Snapshot 不作为 Evidence 再计算，避免递归增益。
