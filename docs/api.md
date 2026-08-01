# API

统一前缀 `/api`，错误格式为 `{"error":{"code","message","details"}}`。V1–V5 原有目标、课程、知识点、任务、学习会话、资料、RAG、活动、测验、错题和 Agent 接口保持兼容。

## V6 掌握度

- `GET /mastery`：`course_id`、`mastery_level`、`sort=weakness|mastery_desc|recent`、分页。
- `GET /mastery/weak-points`：`course_id`、`limit`、`include_unassessed`；明确区分 `weak` 与 `unassessed`。
- `GET /mastery/{knowledge_point_id}`：当前掌握度/置信度、证据摘要、最近 100 条证据、50 个快照、活跃日程与建议。
- `POST /mastery/rebuild`：全部、课程或知识点范围的幂等重建，返回真实统计与失败列表。
- `PUT /mastery/{knowledge_point_id}/self-assessment`：`rating` 1–5 和唯一 `request_id`。

## 复习与建议

- `GET /reviews`：状态、课程、日期范围、overdue 和 limit。
- `GET /adaptive-recommendations`：状态、课程和 limit。
- `POST /adaptive-recommendations/{id}/accept`：必须提交 `confirmed=true` 与 `request_id`；创建或重放唯一 DailyTask，并关联 Schedule/Recommendation。
- `POST /adaptive-recommendations/{id}/reject`：只改变建议状态，不改掌握度，不创建任务。
- `GET /adaptive-metrics`：RAG、测验、掌握度与 Agent 运行统计，含快速路由率、平均 LLM 调用数、平均/P50/P95 总延迟。

新增错误码包括 `mastery_not_found`、`mastery_calculation_failed`、`adaptive_recommendation_not_found`、`adaptive_recommendation_expired`、`adaptive_recommendation_conflict` 与 `adaptive_task_creation_failed`。无证据返回正常的 `unassessed`，不是服务器错误。

## V6 Agent 工具

只读：`get_knowledge_mastery`、`list_weak_knowledge_points`、`list_due_reviews`、`get_adaptive_recommendations`、`explain_mastery`。写入：`accept_review_recommendation`，内部复用建议服务与 DailyTask，仍必须经过 V5 Confirmation。
