# V1 API

默认基地址：`http://127.0.0.1:8000/api`

FastAPI 交互文档：`http://127.0.0.1:8000/docs`

## 接口清单

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查 |
| GET | `/meta` | 版本、数据库、上传配置 |
| GET / POST | `/learning-goals` | 列表 / 创建目标 |
| GET / PATCH / DELETE | `/learning-goals/{id}` | 目标详情 / 更新 / 删除 |
| POST | `/materials/upload` | 上传 PDF、MD、Markdown、TXT |
| GET | `/materials` | 资料列表，支持 `search`、`source_type` |
| GET / DELETE | `/materials/{id}` | 资料详情 / 同步删除文件和记录 |
| GET / POST | `/courses` | 课程列表 / 创建 |
| GET / PATCH / DELETE | `/courses/{id}` | 课程详情 / 更新 / 删除 |
| GET / POST | `/courses/{id}/knowledge-points` | 知识点列表 / 创建 |
| PATCH / DELETE | `/knowledge-points/{id}` | 更新 / 删除知识点 |
| GET | `/today` | 当前目标、今日任务、最近课程和会话 |
| POST | `/daily-tasks` | 创建任务 |
| PATCH / DELETE | `/daily-tasks/{id}` | 更新 / 删除任务 |
| GET / POST | `/learning-sessions` | 会话列表 / 创建或恢复 |
| GET / PATCH | `/learning-sessions/{id}` | 会话详情 / 更新状态和笔记 |
| GET | `/review-items` | 未完成知识点与历史任务 |
| GET | `/progress` | 数据库聚合进度 |
| POST / DELETE | `/demo-data` | 导入 / 清理 Demo |

## 查询示例

创建目标：

```json
{
  "title": "三周入门 MCP",
  "description": "理解 MCP 的核心概念并完成一个基础 Server",
  "target_date": "2026-08-19",
  "daily_minutes": 40,
  "current_level": "了解普通 API",
  "status": "active"
}
```

创建课程：

```json
{
  "learning_goal_id": 1,
  "title": "MCP 基础",
  "description": "手动建立的 V1 课程",
  "status": "active"
}
```

完成学习会话并同步状态：

```json
{
  "status": "completed",
  "notes": "记录本次学习结论",
  "knowledge_point_status": "completed",
  "daily_task_status": "completed"
}
```

## 错误结构

业务错误统一返回：

```json
{
  "error": {
    "code": "resource_not_found",
    "message": "学习目标不存在",
    "details": null
  }
}
```

输入校验错误使用 HTTP 422，并在 `details` 中返回字段位置与原因。常用状态码：

- `200`：读取或更新成功；
- `201`：创建成功；
- `204`：删除成功；
- `400`：文件类型、大小或关联字段错误；
- `404`：记录不存在；
- `409`：唯一顺序等数据冲突；
- `422`：Pydantic 参数校验失败；
- `503`：数据库不可用。

## 事务说明

- 目标、课程、知识点、任务和会话写操作在数据库事务中提交；
- 完成会话可在一个事务中同步会话、知识点和任务状态；
- 资料删除先定位受控文件，数据库删除失败会回滚；文件操作异常返回清晰业务错误。
