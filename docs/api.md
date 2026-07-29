# PersonalLearning API

默认基地址：`http://127.0.0.1:8000/api`

OpenAPI：`http://127.0.0.1:8000/docs`

## V2 资料知识库

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/materials/upload` | 保存 PDF、MD、Markdown、TXT；返回 `201` 和待解析状态 |
| GET | `/materials` | 列表；支持 `search`、`source_type` |
| GET | `/materials/{id}` | 资料详情和真实处理/索引状态 |
| DELETE | `/materials/{id}` | 删除记录、级联 Chunk、本地文件并重建索引 |
| POST | `/materials/{id}/process` | 解析、清洗、切片、事务替换 Chunk 并全量重建索引 |
| GET | `/materials/{id}/chunks` | 按 `chunk_index` 分页返回 Chunk |
| GET | `/materials/index/status` | 索引可用性、模型、维度、版本、数量和一致性 |
| POST | `/materials/index/rebuild` | 使用全部有效 Chunk 原子全量重建 |
| POST | `/materials/search` | BGE-M3 + FAISS 语义召回，不调用 LLM |

静态路径 `/search`、`/index/status`、`/index/rebuild` 在动态 `{id}` 路径之前注册。

### 上传语义

`POST /materials/upload` 保留 V1 兼容行为：文件保存成功即返回 `201`。此时典型状态为：

```json
{
  "processing_status": "ready",
  "ingestion_status": "pending",
  "indexing_status": "pending",
  "chunk_count": 0,
  "indexed_chunk_count": 0
}
```

它不表示正文已经解析或索引。

### 处理资料

```http
POST /api/materials/3/process
```

同步调用链：

```text
MaterialProcessingPipeline
→ Parser
→ Cleaner
→ Chunker
→ SQLite 事务替换 MaterialChunk
→ MaterialIndexService.rebuild
→ BGE-M3
→ FAISS + Manifest 原子替换
```

`pending`、`failed`、`completed` 均可处理。正在处理返回 `409`。解析失败常用 `422`；模型/索引不可用使用统一业务错误，不返回堆栈。

### Chunk 分页

```http
GET /api/materials/3/chunks?page=1&page_size=20
```

响应：

```json
{
  "items": [
    {
      "id": 12,
      "material_id": 3,
      "chunk_index": 0,
      "content": "原始资料的清洗后文本……",
      "char_count": 126,
      "content_hash": "sha256",
      "page_number": 6,
      "section_title": "Resources",
      "created_at": "2026-07-30T10:00:00",
      "updated_at": "2026-07-30T10:00:00"
    }
  ],
  "total": 8,
  "page": 1,
  "page_size": 20,
  "pages": 1
}
```

不返回向量，也不返回资料本地绝对路径。

### 索引状态

```http
GET /api/materials/index/status
```

```json
{
  "available": true,
  "building": false,
  "model_name": "BAAI/bge-m3",
  "embedding_dimension": 1024,
  "chunk_count": 24,
  "built_at": "2026-07-30T10:10:00",
  "index_version": "uuid",
  "stale": false,
  "error_message": null
}
```

没有索引时接口仍返回 `200`，`available=false`。索引/Manifest 损坏或配置不一致时 `stale=true` 并给出错误说明。

### 重建索引

```http
POST /api/materials/index/rebuild
```

一次只允许一个重建；锁已占用返回 `409 index_build_in_progress`。没有有效 Chunk 时会清除索引文件并返回 `chunk_count=0`，不会伪造可用索引。

### 语义检索

请求：

```json
{
  "query": "MCP 中 Tools 和 Resources 有什么区别？",
  "top_k": 5,
  "material_ids": [3],
  "min_score": null
}
```

响应：

```json
{
  "query": "MCP 中 Tools 和 Resources 有什么区别？",
  "model_name": "BAAI/bge-m3",
  "index_version": "uuid",
  "results": [
    {
      "rank": 1,
      "score": 0.82,
      "chunk_id": 12,
      "material_id": 3,
      "original_filename": "mcp-guide.pdf",
      "chunk_index": 4,
      "content": "……",
      "page_number": 6,
      "section_title": "Tools and Resources"
    }
  ],
  "duration_ms": 37
}
```

- `query` 会去除首尾空格，空值返回 `422`；
- `top_k` 默认 5，最大 20；
- `material_ids` 可空；传入不存在的资料返回 `404`；
- 无可用索引返回 `409 index_unavailable`；
- 结果按分数降序，同分按 `chunk_id` 稳定排序；
- 已删除、非解析完成或 SQLite 中不存在的 Chunk 不返回；
- 响应不包含 Embedding，不生成答案或总结。

## 保留的 V1 API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查 |
| GET | `/meta` | 版本、数据库与上传配置 |
| GET / POST | `/learning-goals` | 目标列表 / 创建 |
| GET / PATCH / DELETE | `/learning-goals/{id}` | 详情 / 更新 / 删除 |
| GET / POST | `/courses` | 课程列表 / 创建 |
| GET / PATCH / DELETE | `/courses/{id}` | 详情 / 更新 / 删除 |
| GET / POST | `/courses/{id}/knowledge-points` | 知识点列表 / 创建 |
| PATCH / DELETE | `/knowledge-points/{id}` | 更新 / 删除知识点 |
| GET | `/today` | 今日聚合 |
| POST | `/daily-tasks` | 创建任务 |
| PATCH / DELETE | `/daily-tasks/{id}` | 更新 / 删除任务 |
| GET / POST | `/learning-sessions` | 会话列表 / 创建或恢复 |
| GET / PATCH | `/learning-sessions/{id}` | 详情 / 状态和笔记 |
| GET | `/review-items` | 未完成知识点与历史任务 |
| GET | `/progress` | SQLite 聚合进度 |
| POST / DELETE | `/demo-data` | 导入 / 清理 Demo |

## 错误结构

```json
{
  "error": {
    "code": "index_unavailable",
    "message": "尚未建立可用的资料索引，请先处理资料或重建索引。",
    "details": null
  }
}
```

常用状态码：

- `200`：读取、更新、处理、检索或重建成功；
- `201`：上传/创建成功；
- `204`：删除成功；
- `404`：资料或其他记录不存在；
- `409`：索引不可用、正在重建或数据冲突；
- `422`：参数或资料正文校验失败；
- `503`：模型、索引或数据库暂时不可用。

服务端记录错误堆栈，API 只返回面向用户的消息。

## V4 学习活动 API

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/learning-activities/generate` | 在限定资料范围内生成完整 draft；`request_id` 幂等 |
| GET | `/learning-activities` | 按状态、课程、知识点分页查询 |
| GET | `/learning-activities/{id}` | 草稿返回管理字段；已发布活动隐藏答案字段 |
| PATCH | `/learning-activities/{id}` | 修改草稿元数据，或归档活动 |
| DELETE | `/learning-activities/{id}/questions/{question_id}` | 从草稿删除题目并重排 |
| POST | `/learning-activities/{id}/questions/reorder` | 按完整题目 ID 列表重排草稿 |
| POST | `/learning-activities/{id}/publish` | 校验后发布并固定题目 |
| POST | `/learning-activities/{id}/attempts` | 为已发布活动创建 Attempt |
| GET | `/quiz-attempts/{id}` | 进行中返回安全题面；完成后返回评分结果 |
| PUT | `/quiz-attempts/{id}/answers/{question_id}` | 逐题保存标准化答案或简答原文 |
| POST | `/quiz-attempts/{id}/submit` | 幂等提交、批改、聚合与错题创建 |
| GET | `/wrong-answers` | 按状态、课程、知识点分页查询错题 |
| GET | `/wrong-answers/{id}` | 查看答案、解析与来源快照 |
| PATCH | `/wrong-answers/{id}` | 标记 `resolved`、`dismissed` 等用户状态 |
| POST | `/wrong-answers/review` | 将指定错题复制为独立复习活动并开始 Attempt |

生成请求至少包含标题、已索引资料 ID、题型、题数、难度和 UUID `request_id`。相同 ID 与相同请求返回原草稿；相同 ID 配置不一致返回 `409 activity_request_conflict`。

进行中的 Attempt 绝不返回 `correct_answer`、`reference_answer`、`grading_rubric` 或 `explanation`。提交请求包含新的 UUID `request_id`；相同请求与相同答案重放结果，不同答案冲突。失败批改只能以相同请求和答案重试。

## V3 可信资料问答 API

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/rag/conversations` | 创建会话 |
| GET | `/rag/conversations` | 按状态分页列出会话 |
| GET | `/rag/conversations/{id}` | 获取会话、消息和引用快照 |
| DELETE | `/rag/conversations/{id}` | 归档会话 |
| POST | `/rag/conversations/{id}/ask` | 同步可信问答 |
| POST | `/rag/conversations/{id}/stream` | POST SSE 可信问答 |
| GET | `/rag/status` | LLM 配置与 V2 索引可用状态 |

同步问答请求：

```json
{
  "question": "MCP Tools 与 Resources 有什么区别？",
  "request_id": "browser-generated-uuid",
  "top_k": 6,
  "material_ids": [3]
}
```

`request_id` 在会话内唯一。相同 ID 与相同问题会返回原结果并设置 `idempotent_replay=true`；相同 ID 用于不同问题返回 `409 request_id_conflict`。`material_ids` 为空表示全部已索引资料。

响应同时包含：

- `user_message` 与最终 `assistant_message`；
- `assistant_message.citations`：只包含答案正文实际引用的快照；
- `retrieval`：最终检索查询、候选/来源数、阈值、索引版本与耗时；
- `model`：Provider、模型名和是否使用降级修复，不包含密钥；
- `idempotent_replay`。

资料不足时仍返回一条可恢复的 completed 助手消息，`answerable=false`、`citations=[]` 和稳定 `refusal_reason`。如果已有相关资料但 LLM 未配置或暂时不可用，返回 `503`，并保存失败状态供页面刷新恢复。

### SSE

`POST /rag/conversations/{id}/stream` 使用与同步问答相同的 JSON 请求。事件顺序为：

```text
accepted → retrieval → message_start → delta* → citations → done
```

发生错误时以 `error` 结束。服务端先完成模型输出解析、引用校验和数据库持久化，再发送 `delta`；不会把未经校验的原始模型 Token 直接转发。断线后客户端重新 GET 会话即可恢复最终状态。
