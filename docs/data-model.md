# PersonalLearning 数据模型

## 关系

```text
learning_goals
  ├─ courses
  │   └─ knowledge_points
  ├─ daily_tasks
  └─ learning_sessions

materials
  └─ material_chunks
```

SQLite 外键已启用。V2 不把 Embedding 存入 SQLite；FAISS 位置通过 Manifest 的 `chunk_ids` 映射到 `material_chunks.id`。

## materials

V1 字段保留：

| 字段 | 说明 |
|---|---|
| `id` | 主键 |
| `title` | 默认取安全化后的文件主名 |
| `original_filename` | 用户上传文件名 |
| `stored_filename` | 唯一生成的受控存储名 |
| `file_path` | 服务端受控路径，不在 Chunk API/搜索 API 返回 |
| `source_type` / `mime_type` | 文件类型 |
| `file_size` | 字节数 |
| `processing_status` | V1 文件保存状态；`ready` 只表示保存成功 |
| `created_at` / `updated_at` | 时间戳 |

V2 新增字段：

| 字段 | 说明 |
|---|---|
| `ingestion_status` | `pending`、`processing`、`completed`、`failed` |
| `indexing_status` | `pending`、`indexing`、`completed`、`failed` |
| `chunk_count` | SQLite 中该资料的真实 Chunk 数 |
| `indexed_chunk_count` | 当前完整索引包含的该资料 Chunk 数 |
| `processed_at` | 最近解析和切片成功时间 |
| `indexed_at` | 最近索引成功时间 |
| `error_message` | 最近一次解析或索引的用户可理解错误 |

升级已有 V1 数据后，新状态为 `pending`，计数为 0，时间为空；原 `processing_status` 不变。

## material_chunks

| 字段 | 说明 |
|---|---|
| `id` | 主键，也是 Manifest 中的稳定 Chunk ID |
| `material_id` | `materials.id` 外键，`ON DELETE CASCADE`，有索引 |
| `chunk_index` | 资料内从 0 连续递增的稳定顺序 |
| `content` | 清洗后的真实文本 |
| `char_count` | `content` 字符数，必须大于 0 |
| `content_hash` | `content` 的 SHA-256 |
| `page_number` | PDF 页码，从 1 开始；其他类型可空 |
| `section_title` | Markdown 当前标题；其他类型可空 |
| `created_at` / `updated_at` | 时间戳 |

约束：

- `(material_id, chunk_index)` 唯一；
- `chunk_index >= 0`；
- `char_count > 0`；
- 删除 Material 时 Chunk 级联删除；
- 重新处理在同一数据库事务中先删旧 Chunk、再写完整新批次；失败回滚，因此旧完整批次保留。

## FAISS 与 Manifest

FAISS 文件使用归一化 `float32` 向量和 `IndexFlatIP`。Manifest 是 UTF-8 JSON，不保存正文和完整向量：

| 字段 | 说明 |
|---|---|
| `schema_version` | Manifest 结构版本，当前为 1 |
| `index_version` | 每次成功构建生成的 UUID |
| `model_name` / `model_revision` | Embedding 配置 |
| `embedding_dimension` | 模型实际输出维度 |
| `normalized` | 是否归一化 |
| `distance_metric` | `inner_product` |
| `chunk_count` | 索引向量数 |
| `chunk_ids` | FAISS 位置到 SQLite Chunk ID 的映射 |
| `built_at` | 构建时间 |
| `content_checksum` | 按 Chunk ID、Material ID、内容哈希生成的一致性校验 |
| `index_checksum` | FAISS 文件 SHA-256 |

索引与 Manifest 先写唯一临时文件，校验数量和维度后再替换正式文件。失败时恢复旧索引。加载时校验文件完整性、数量、维度、模型、归一化配置和 checksum。

## 保留的 V1 表

### learning_goals

学习目标内容、目标日期、每日分钟数、当前水平、状态、Demo 标记和时间戳。

### courses

关联学习目标，保存手动课程标题、描述、状态、Demo 标记和时间戳。

### knowledge_points

关联课程，保存标题、描述、唯一顺序、预计分钟数和用户维护状态。V2 仍不代表算法掌握度。

### daily_tasks

关联目标及可选课程/知识点，保存任务类型、计划日期、预计分钟数和状态。

### learning_sessions

关联目标及可选课程/知识点/任务，保存开始结束时间、基础状态和手动笔记。

## Alembic

- `20260729_0001_initial_v1.py`：V1 初始结构，未修改；
- `20260730_0002_material_knowledge_base.py`：新增 Material 状态字段和 `material_chunks`。

V2 完成时 head 为 `20260730_0002`。V3 继续使用显式增量迁移；应用启动不隐式执行 `create_all`。

## rag_conversations

保存单用户资料问答会话：`title`、`status(active/archived)`、可选默认 `top_k`、最近消息时间和时间戳。归档不会删除历史消息。

## rag_messages

每个问题保存一条 `user` 消息和一条通过 `reply_to_message_id` 关联的 `assistant` 消息。助手消息保存唯一 `(conversation_id, request_id)`、原问题、最终检索查询、回答/拒答状态、Prompt 版本、模型名、Token 和延迟。相同 request_id 不会创建第二组消息。

消息不保存完整 Prompt、完整历史或资料上下文。删除会话时消息级联删除；助手消息不会脱离对应用户消息独立写入。

## rag_citations

每个被最终答案实际引用的来源保存 `S1` 标签、rank、score、Material/Chunk 外键，以及文件名、片段序号、页码/章节和正文摘录快照。删除资料后外键设为 `NULL`，快照仍可读取；新检索依赖当前 V2 索引，因此不会继续命中已删除来源。

## Alembic V3

- `20260730_0003_rag_conversations.py`：新增 `rag_conversations`、`rag_messages`、`rag_citations`；
- 当前 head：`20260730_0003`；
- V1 的 `0001` 与 V2 的 `0002` 未修改。

## V4 学习活动

### learning_activities

保存活动标题、`quiz/review` 类型、`draft/published/archived/generation_failed` 状态、可空课程/知识点、来源范围、题数/总分、生成请求 ID、Prompt/模型版本和发布时间。生成请求 ID 唯一。课程或知识点删除时外键置空，历史活动保留。

### activity_questions

保存活动内唯一顺序、四种题型、选项、标准答案/参考答案、Rubric、解析、难度、分值和内容哈希。`(activity_id, question_index)` 唯一；结构化 JSON 入库前均经过严格 Schema 和跨字段校验。

### question_sources

保存题目引用标签、排序/相似度和受限正文摘录，以及由数据库确定的文件名、Chunk 序号、页码和章节。`(question_id, source_label)` 唯一。Material/Chunk 外键使用 `SET NULL`，因此删除资料不会破坏历史结果。

### quiz_attempts / quiz_answers

Attempt 保存活动、可选学习会话、提交请求、状态、总分统计、批改模型/Prompt 和错误状态。Answer 以 `(attempt_id, question_id)` 唯一，保存用户答案、评分状态、得分、反馈、Rubric 命中/缺失项和置信度。批改失败不会写成零分。

### wrong_answers

每条错题来自真实 Answer，以 `(attempt_id, answer_id)` 去重，保存 `incorrect/partial/unanswered` 类型、用户状态、复习次数和解决时间。它不表示算法掌握度。

### daily_tasks.activity_id

V4 为今日任务增加可空 Activity 外键。有关联 Activity 的任务只会在对应 Attempt 成功完成批改后自动完成；关联学习会话同样在成功批改后完成。

## Alembic V4

- `20260730_0004_learning_activities.py`：新增六张 V4 表、约束和查询索引，并为 `daily_tasks` 增加 `activity_id`；
- 当前 head：`20260730_0004`；
- `0001`、`0002`、`0003` 历史迁移均未修改。
# Alembic V5

迁移 `20260801_0005_langgraph_learning_agent.py` 新增 `agent_conversations`、`agent_messages`、`agent_runs`、`agent_tool_calls`、`agent_confirmations`。`conversation_id + request_id`、`run_id + step_index` 和每运行一个 confirmation 均有唯一约束。LangGraph checkpoint 不写入这些业务表，而是保存在 `AGENT_CHECKPOINT_DB_PATH` 指向的独立 SQLite 文件。
