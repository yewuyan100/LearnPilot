# Agent 工具

V5 原有 10 个只读工具和 6 个确认写工具保持不变。

V6 新增只读工具：

- `get_knowledge_mastery(knowledge_point_id)`：真实当前分数、置信度、等级、证据数、最近练习、下次复习和依据。
- `list_weak_knowledge_points(course_id?, limit?, include_unassessed?)`：薄弱排名、掌握度、置信度、active 错题和复习状态；未评估单独分类。
- `list_due_reviews(start_date?, end_date?, course_id?, status?, overdue?, limit?)`。
- `get_adaptive_recommendations(status?, course_id?, limit?)`：只返回数据库真实建议。
- `explain_mastery(knowledge_point_id)`：确定性证据摘要，不重新计算结论。

V6 新增高层写工具 `accept_review_recommendation(recommendation_id)`。它读取并冻结真实建议，经 V5 Confirmation 后调用现有任务业务模型，关联 Recommendation 与 ReviewSchedule。重复批准返回同一任务。工具不能直接设置掌握度，也没有放宽一次运行一个写工具的限制。

所有工具统一返回 success、tool、data、user_summary、resource_ids、citations、error_code 与 retryable。计划校验器拒绝未知工具、缺失参数、超限、多写、写后读以及删除、改分、答案/rubric、代码、shell、SQL、文件、网络、环境变量与密钥参数。
