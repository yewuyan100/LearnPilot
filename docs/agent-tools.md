# Agent 工具清单

查询工具：`answer_from_materials`、`search_materials`、`list_courses`、`list_knowledge_points`、`list_daily_tasks`、`get_learning_progress`、`list_learning_activities`、`get_activity_summary`、`list_quiz_attempts`、`get_wrong_answers`。

需确认写工具：`create_daily_task`、`update_daily_task_status`、`save_learning_note`、`generate_learning_activity`（仅草稿）、`create_wrong_answer_review`、`start_quiz_attempt`。

工具统一返回 `success`、`tool`、`data`、`user_summary`、`resource_ids`、`citations`、`error_code`、`retryable`。计划校验器拒绝未知工具、超过上限、多个写入、写后查询，以及删除、改分、修改答案/rubric、代码、shell、SQL、文件、网络、环境变量与密钥相关参数。
