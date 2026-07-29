# PersonalLearning V2 完成报告

完成日期：2026-07-30

## 1. V1 基线检查

开发前工作区干净。实际 Git 基线是：

- HEAD：`4ccd352 docs: add v1 completion and v2 handoff`；
- tag：`v1.0.0` 指向该 HEAD；
- 附件中的 `1b9de60` 是更早的 V1 业务提交，之后已有文档提交；
- Alembic：`20260729_0001 (head)`，`check` 无差异；
- 后端：`9 passed`，compileall 通过；
- 前端：`7 passed`，ESLint、TypeScript、Vite build 通过。

V1 初始迁移未修改，原有学习目标、课程、知识点、任务、会话、资料上传/删除、今日页和进度页调用链全部保留。

## 2. V2 实际范围

已完成：

```text
上传 PDF / Markdown / TXT
→ 手动处理
→ 正文解析
→ 确定性清洗
→ 稳定切片
→ MaterialChunk 持久化
→ 本地 BAAI/bge-m3 Embedding
→ float32 归一化
→ FAISS IndexFlatIP
→ 索引 + Manifest 原子保存
→ 自然语言语义检索
→ 文件名、页码、章节、Chunk、分数来源定位
```

并实现失败重试、重新处理、全量重建、索引锁、损坏/不一致检测、应用重启后加载、资料删除后索引同步更新、前端真实状态/片段/检索/索引管理。

## 3. 新增文件

### 数据库、模型、Repository、Schema

- `backend/alembic/versions/20260730_0002_material_knowledge_base.py`
- `backend/app/models/material_chunk.py`
- `backend/app/repositories/__init__.py`
- `backend/app/repositories/materials.py`
- `backend/app/repositories/material_chunks.py`
- `backend/app/schemas/material_chunk.py`

### 资料处理

- `backend/app/services/material_processing/__init__.py`
- `backend/app/services/material_processing/types.py`
- `backend/app/services/material_processing/cleaning.py`
- `backend/app/services/material_processing/chunking.py`
- `backend/app/services/material_processing/pipeline.py`
- `backend/app/services/material_processing/parsers/__init__.py`
- `backend/app/services/material_processing/parsers/base.py`
- `backend/app/services/material_processing/parsers/text.py`
- `backend/app/services/material_processing/parsers/markdown.py`
- `backend/app/services/material_processing/parsers/pdf.py`

### Embedding 与向量索引

- `backend/app/services/embedding/__init__.py`
- `backend/app/services/embedding/base.py`
- `backend/app/services/embedding/bge_m3.py`
- `backend/app/services/embedding/service.py`
- `backend/app/services/vector_store/__init__.py`
- `backend/app/services/vector_store/base.py`
- `backend/app/services/vector_store/manifest.py`
- `backend/app/services/vector_store/faiss_store.py`
- `backend/app/services/vector_store/service.py`

### 测试与验收

- `backend/tests/__init__.py`
- `backend/tests/fakes.py`
- `backend/tests/pdf_utils.py`
- `backend/tests/test_material_parsers.py`
- `backend/tests/test_material_cleaning.py`
- `backend/tests/test_material_chunking.py`
- `backend/tests/test_embedding_service.py`
- `backend/tests/test_faiss_store.py`
- `backend/tests/test_material_processing_api.py`
- `frontend/src/test/MaterialsV2.test.tsx`
- `scripts/acceptance_v2.py`

### 前端与文档

- `frontend/src/components/MaterialChunksDialog.tsx`
- `frontend/src/components/MaterialIndexPanel.tsx`
- `frontend/src/components/MaterialSearchPanel.tsx`
- `V2_TASK.md`
- `V2_PROGRESS.md`
- `V2_COMPLETION_REPORT.md`

## 4. 修改文件

- 配置与依赖：`.env.example`、`.gitignore`、`backend/requirements.txt`
- 后端：`backend/app/api/deps.py`、`backend/app/api/routes/materials.py`、`backend/app/core/config.py`、`backend/app/main.py`
- 模型与 Schema：`backend/app/models/__init__.py`、`backend/app/models/enums.py`、`backend/app/models/material.py`、`backend/app/schemas/material.py`
- 后端测试夹具：`backend/tests/conftest.py`
- 前端：`frontend/package.json`、`frontend/package-lock.json`、`frontend/src/api/resources.ts`、`frontend/src/pages/MaterialsPage.tsx`、`frontend/src/styles.css`、`frontend/src/test/App.test.tsx`、`frontend/src/types/index.ts`、`frontend/src/utils/format.ts`
- 文档：`README.md`、`docs/api.md`、`docs/data-model.md`

## 5. Alembic 版本

- 保留：`20260729_0001_initial_v1.py`
- 新增：`20260730_0002_material_knowledge_base.py`
- 当前：`20260730_0002 (head)`
- `upgrade head`、`current`、`heads`、`check` 均通过；
- 临时 SQLite 上 `upgrade → downgrade 20260729_0001 → upgrade` 实际通过；
- upgrade 为已有 Material 补 `pending` / 0 / null 默认值；
- downgrade 删除 V2 表、索引和新增字段；
- V1 现有数据未重建、未丢失。

## 6. Material 字段变化

`processing_status` 语义不变：`ready` 仍只表示原文件保存成功。

新增：

- `ingestion_status`：`pending` / `processing` / `completed` / `failed`
- `indexing_status`：`pending` / `indexing` / `completed` / `failed`
- `chunk_count`
- `indexed_chunk_count`
- `processed_at`
- `indexed_at`

`error_message` 继续作为最近一次用户可理解的保存、解析或索引失败说明。

## 7. MaterialChunk

`material_chunks` 保存 `material_id`、连续 `chunk_index`、清洗后 `content`、`char_count`、SHA-256 `content_hash`、可空 `page_number` / `section_title` 和时间戳。

- `material_id` 有索引并使用 `ON DELETE CASCADE`；
- `(material_id, chunk_index)` 唯一；
- 向量不写入 SQLite；
- Chunk API 不返回 Embedding 或资料绝对路径。

## 8. 解析器设计

- TXT：只接受 UTF-8 / UTF-8-SIG；非法编码、空正文明确失败；
- Markdown：识别 1–6 级标题，传递当前标题，保留段落、列表与代码语义；
- PDF：pypdf 按页提取，页码从 1 开始；加密、损坏、无文本/扫描版明确失败；
- Parser 只构造 `ParsedDocument` / `ParsedSection`，不复制 Cleaner 或 Chunker。

## 9. 清洗规则

统一换行、移除 NUL 和无意义控制字符、Tab 转四空格、清行尾空白、最多保留一个段落空行；保留中英文、数字、标点、代码和公式字符。PDF 仅安全合并英文连字符断词，不拼接中文段落。逻辑确定且幂等。

## 10. Chunk 策略

默认 `800 / 120 / 80` 字符：先按 Parser 提供的标题/页分区，再优先段落、行、中文/英文句末和次级标点边界；超长内容退化为字符窗口；相邻窗口保留 overlap；尾部新增内容过小时合并；索引连续，内容哈希稳定。

## 11. BGE-M3 加载

`BgeM3Embedder` 通过依赖注入提供 `embed_documents` / `embed_query`：

- `SentenceTransformer("BAAI/bge-m3")`
- `HF_HOME` 可配置并兼容标准 `HF_HOME/hub`；
- `local_files_only=true`，默认不联网；
- 进程内懒加载且只初始化一次；
- 批量编码，输出动态维度 `float32`；
- 开启归一化并再次校验非零范数；
- 日志记录模型、设备、维度、批量数和耗时，不记录正文/向量。

默认单元测试注入 16 维 FakeEmbedder；真实验收加载本地 BGE-M3，实际维度为 1024。

## 12. FAISS 与 Manifest

索引：归一化向量 + `faiss.IndexFlatIP`，Inner Product 近似余弦相似度。

Manifest 字段：

- `schema_version`
- `index_version`
- `model_name`
- `model_revision`
- `embedding_dimension`
- `normalized`
- `distance_metric`
- `chunk_count`
- `chunk_ids`
- `built_at`
- `content_checksum`
- `index_checksum`

Manifest 不保存正文或向量。

## 13. 索引一致性策略

从 SQLite 查询全部 `ingestion_status=completed` 的 Chunk，按批生成向量，构建全新索引，写入唯一临时索引/Manifest，校验数量、维度和 checksum 后原子替换。失败时恢复旧完整文件并将相关资料标记为索引失败。

加载时校验：

- 索引和 Manifest 必须同时存在；
- 模型、归一化配置和可选维度一致；
- FAISS `ntotal`、维度、Chunk ID 数一致；
- FAISS 文件 checksum 正确；
- Manifest 与当前 SQLite 内容 checksum 比较并报告 `stale`。

进程内 `threading.Lock` 保证同一时刻只允许一次重建，重复请求返回 409。

## 14. API 调用链

处理资料：

```text
POST /materials/{id}/process
→ MaterialProcessingPipeline
→ Parser / Cleaner / Chunker
→ MaterialChunkRepository.replace_for_material（事务）
→ MaterialIndexService.rebuild
→ BgeM3Embedder
→ FaissStore.save
→ 返回最新 MaterialRead
```

语义检索：

```text
POST /materials/search
→ 校验 query / top_k / material_ids
→ embed_query
→ FAISS TopK
→ Manifest position → chunk_id
→ SQLite 回查 Chunk + Material
→ 过滤删除/未完成/指定资料
→ 稳定排序
→ 返回来源片段
```

V2 新增 API：

- `POST /api/materials/{id}/process`
- `GET /api/materials/{id}/chunks`
- `GET /api/materials/index/status`
- `POST /api/materials/index/rebuild`
- `POST /api/materials/search`

V1 的 upload/list/get/delete/meta 及学习业务 API 保持兼容。

## 15. 前端功能

资料页面真实展示文件名、类型、大小、上传时间、解析状态、索引状态、Chunk/已索引数、处理/索引时间和失败原因。

实现：

- 处理/重新处理按钮，mutation 期间禁用并刷新 Query；
- Chunk 分页对话框，展示页码、章节、字符数和正文；
- “资料检索测试”区，支持 query、Top K、资料范围和来源结果；
- 明确提示“当前结果是资料检索片段，不是 AI 生成回答”；
- 索引模型、维度、Chunk 数、构建时间、stale/error 和重建操作；
- 上传、文件名搜索、类型筛选和删除继续工作；
- 不显示本地绝对路径或 Embedding。

## 16. 删除和重新处理

重新处理事务性替换同一资料的 Chunk，不累计、不重复；失败时旧完整 Chunk 保留，其他资料不受影响。成功后触发全量索引原子重建。

删除顺序为数据库记录/级联 Chunk提交、受控原文件删除、FAISS 重建。文件系统和 SQLite 不是同一事务；索引重建失败时删除仍成立，响应头标记索引 stale，后续可手动重建。

## 17. 默认测试结果

后端：

```text
46 passed
compileall app scripts: passed
```

测试覆盖 Parser、Cleaner、Chunker、事务重处理、失败重试、搜索参数/过滤/来源、索引生命周期、并发锁、Embedding 适配器、FAISS 保存/加载/损坏/一致性/失败保留旧索引，以及所有 V1 API 测试。

前端：

```text
2 test files passed
13 tests passed
ESLint passed
TypeScript passed
Vite production build passed
```

## 18. 真实 BGE-M3 与 V1 回归

独立向量检查：

```text
shape=(2, 1024)
dtype=float32
norms=[1.0, 1.0]
local_files_only=true
```

`scripts/acceptance_v2.py` 通过真实 HTTP API：

```json
{
  "status": "passed",
  "embedding_model": "BAAI/bge-m3",
  "embedding_dimension": 1024,
  "materials_processed": 3,
  "index_available": true,
  "search_verified": true,
  "restart_verified": true,
  "reprocessing_idempotent": true,
  "deletion_verified": true
}
```

它使用临时数据库/上传/FAISS，启动后端、处理 TXT/Markdown/可提取 PDF、检索来源、停止并重启后端、再次检索、重处理、删除和清理；不直接操作数据库。

`scripts/acceptance_v1.py` 的六个原有业务场景也在隔离数据库上实际通过。

## 19. 已知限制

- 同步解析和 CPU Embedding 会占用请求时间；V2 按范围明确不引入任务队列；
- 全量重建适合当前单用户小规模资料，大型知识库后续需增量策略；
- 索引锁是单进程锁，多 worker 不在 V2 支持范围；
- 单一 `error_message` 同时承载最近解析/索引错误；
- Markdown Parser 是轻量确定性实现，不是完整 CommonMark AST；
- PDF 仅提取文本层，不支持 OCR、表格结构恢复、图片或复杂版面理解；
- 语义检索只是来源 Chunk 召回，不是 RAG 答案。

## 20. 明确未实现

V2 未实现 LLM 生成、RAG 最终回答、LangChain、LangGraph、Agent、Prompt、SSE、OCR、自动课程、自动知识点、自动出题、自动批改、学习规划、掌握度预测、多用户和云端部署。

## 21. Git 差异与版本

最终提交前已检查 `git status --short`、`git diff --stat`、`git diff --name-only` 和 `.gitignore`。运行产物、模型、SQLite、上传、FAISS、Manifest、虚拟环境、`node_modules` 与 `dist` 不在提交中。

最终暂存差异统计：

```text
66 files changed, 4585 insertions(+), 325 deletions(-)
```

V2 交付提交使用：

```text
feat: add local material knowledge indexing and semantic search
```

完成报告所在提交创建标签 `v2.0.0`。准确 commit hash 以 `git rev-parse --short v2.0.0` 和最终交付回复为准。
