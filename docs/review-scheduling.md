# 复习调度规则

调度器使用 `APP_TIMEZONE`，相同输入生成相同到期时间。基础间隔：beginner 1 天、developing 3 天、proficient 7 天、strong 14 天；strong 且置信度低于 60 时使用 7 天验证性复习。

覆盖规则：最近复习再次失败时次日复习；存在从未解决的 active 错题时最晚 3 天；已经逾期的活跃日程保留原日期并在响应中标记 `review_overdue`；无有效证据不创建“薄弱复习”。

每个知识点最多一条 `pending`/`scheduled` 活跃日程。新快照可将旧日程标记 `superseded`；已有同知识点同日任务时复用并关联；Agent 创建任务后日程变为 `scheduled`，真实任务完成后变为 `completed`。系统不删除任务，也不自动改写已有计划。

薄弱度公式：

```text
(100 - mastery) × 0.50
+ (100 - confidence) × 0.15
+ recent_failure × 0.20
+ overdue × 0.15
```

无掌握度的知识点单独标记 `unassessed`，不进入已知薄弱排名。
