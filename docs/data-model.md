# V1 数据模型

## 关系

```text
learning_goals
  ├─ courses
  │   └─ knowledge_points
  ├─ daily_tasks
  └─ learning_sessions

courses / knowledge_points
  ├─ daily_tasks
  └─ learning_sessions

materials（V1 独立保存文件元数据）
```

SQLite 外键已启用。目标或课程删除时，关联记录按外键级联；资料删除由服务同步处理数据库与本地文件。

## learning_goals

| 字段 | 说明 |
|---|---|
| `id` | 主键 |
| `title` / `description` | 目标内容 |
| `target_date` | 可空目标日期 |
| `daily_minutes` | 每日分钟数，5–1440 |
| `current_level` | 当前水平 |
| `status` | `active`、`paused`、`completed`、`archived` |
| `is_demo` | Demo 数据标记 |
| `created_at` / `updated_at` | 时间戳 |

## materials

| 字段 | 说明 |
|---|---|
| `title` | 默认取安全化后的文件主名 |
| `original_filename` | 原始文件名 |
| `stored_filename` | UUID 存储名 |
| `file_path` | 本地受控路径 |
| `source_type` / `mime_type` | 文件类型 |
| `file_size` | 字节数 |
| `processing_status` | V1 为 `uploaded`、`ready`、`failed` |
| `error_message` | 保存失败说明 |
| `created_at` / `updated_at` | 时间戳 |

V1 不保存正文、Chunk 或向量。

## courses

| 字段 | 说明 |
|---|---|
| `learning_goal_id` | 所属目标 |
| `title` / `description` | 课程信息 |
| `status` | `draft`、`active`、`completed`、`archived` |
| `is_demo` | Demo 数据标记 |
| `created_at` / `updated_at` | 时间戳 |

## knowledge_points

| 字段 | 说明 |
|---|---|
| `course_id` | 所属课程 |
| `title` / `description` | 知识点信息 |
| `order_index` | 课程内顺序；与 `course_id` 联合唯一 |
| `estimated_minutes` | 预计分钟数，至少 1 |
| `status` | `not_started`、`learning`、`completed`、`locked` |
| `created_at` / `updated_at` | 时间戳 |

V1 的状态由用户或 Demo 脚本维护，不代表掌握度。

## daily_tasks

| 字段 | 说明 |
|---|---|
| `learning_goal_id` | 所属目标 |
| `course_id` / `knowledge_point_id` | 可空课程与知识点 |
| `title` | 任务标题 |
| `task_type` | `learning`、`review`、`summary` |
| `estimated_minutes` | 预计分钟数 |
| `scheduled_date` | 计划日期 |
| `status` | `pending`、`in_progress`、`completed`、`skipped` |
| `created_at` / `updated_at` | 时间戳 |

## learning_sessions

| 字段 | 说明 |
|---|---|
| `learning_goal_id` | 所属目标 |
| `course_id` / `knowledge_point_id` | 可空学习上下文 |
| `daily_task_id` | 可空今日任务 |
| `started_at` / `ended_at` | 开始和结束时间 |
| `status` | `active`、`paused`、`completed`、`cancelled` |
| `notes` | 手动学习笔记 |
| `created_at` / `updated_at` | 时间戳 |

同一未完成任务再次“开始学习”时返回已有的活动/暂停会话，从而支持刷新和恢复。

## 迁移

首个迁移为 `20260729_0001_initial_v1.py`。应用不会在生产启动路径中调用 `create_all`；数据库结构以 Alembic 为准。
