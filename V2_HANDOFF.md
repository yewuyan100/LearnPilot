# PersonalLearning V2 交接说明

交接基线：

- Git 提交：`1b9de60 feat: complete personal learning agent v1`
- Git 标签：`v1.0.0`
- Alembic：`20260729_0001 (head)`
- V1 后端测试：`9 passed`
- V1 前端测试：`7 passed`
- V1 六场景验收：全部通过

本文只描述 V1 的实际实现和 V2 的文件级接入预期，不实现文档解析、Embedding、FAISS、RAG 或 LLM。

## 1. V1 资料上传实际调用链

### 前端

```text
MaterialsPage
  └─ 文件选择或 drop
      └─ acceptFile(file)
          └─ TanStack Query mutation
              └─ materialsApi.upload(file)
                  └─ FormData: key = "file"
                      └─ api("/materials/upload", POST)
                          └─ http://127.0.0.1:8000/api/materials/upload
```

具体行为：

1. `MaterialsPage.tsx` 的隐藏 `<input type="file">` 和拖拽区域只接受 `.pdf`、`.md`、`.markdown`、`.txt`；
2. `materialsApi.upload` 创建 `FormData`，字段名固定为 `file`；
3. `api()` 检测到 `FormData` 后不手动设置 `Content-Type`，由浏览器生成 multipart boundary；
4. 成功后前端失效 `["materials"]` 查询并重新获取列表；
5. 错误由统一 `ApiError` 读取后端 `error.message`，再通过 Toast 展示。

### 后端

```text
FastAPI app
  └─ app.include_router(api_router, prefix="/api")
      └─ materials.router, prefix="/materials"
          └─ POST /upload
              └─ upload_material(db, settings, file)
                  └─ save_upload(db, file, settings)
                      ├─ safe_display_name()
                      ├─ 扩展名白名单
                      ├─ 创建 upload_dir
                      ├─ UUID 存储名
                      ├─ 1 MB 分块写入和累计大小检查
                      ├─ 空文件检查
                      ├─ 创建 Material，状态设为 ready
                      ├─ db.commit() / db.refresh()
                      └─ 异常时 rollback + 删除部分文件
```

成功响应使用 `MaterialRead`，HTTP 状态为 201。

实际错误行为：

- 不支持扩展名：HTTP 415，`unsupported_file_type`；
- 超过大小限制：HTTP 413，`file_too_large`；
- 空文件：HTTP 422，`empty_file`；
- 保存或数据库异常：回滚数据库并删除已写入的部分文件；
- 无论成功或失败，最终都会关闭 `UploadFile`。

## 2. Material 各层文件位置

| 层 | 实际文件 | 实际职责 |
|---|---|---|
| Model | `backend/app/models/material.py` | `materials` SQLAlchemy 模型 |
| 状态枚举 | `backend/app/models/enums.py` | `MaterialStatus` |
| Schema | `backend/app/schemas/material.py` | `MaterialRead` 响应 |
| Service | `backend/app/services/materials.py` | 文件名安全化、上传保存、失败清理、本地文件删除 |
| 通用 CRUD | `backend/app/services/crud.py` | `get_or_404`、`commit`、通用字段更新 |
| Router | `backend/app/api/routes/materials.py` | 上传、列表、详情和删除接口 |
| Router 注册 | `backend/app/api/router.py` | 把 materials router 加入 `/api` 路由 |
| 依赖 | `backend/app/api/deps.py` | 注入 `Session` 和 `Settings` |

### Repository 现状

V1 **没有独立的 Material Repository 文件或 `repositories/` 目录**。

当前职责分布为：

- `GET /materials` 的 `select(Material)`、搜索、类型筛选和排序直接写在 Router；
- `GET/DELETE /materials/{id}` 使用 `services/crud.py` 的 `get_or_404`；
- 文件保存和删除放在 `services/materials.py`；
- 事务提交分别由 `save_upload` 或通用 `commit` 完成。

V2 如果引入资料处理队列、Chunk 查询、批量状态迁移或更复杂事务，可以新增 Repository 层；交接时不能假设 V1 已经存在该层。

## 3. 文件存储配置

配置位置：`backend/app/core/config.py`  
示例环境变量：`.env.example`

| 配置 | 默认值 | 说明 |
|---|---|---|
| `UPLOAD_DIR` | `./uploads` | 相对后端运行目录；README 从 `backend` 启动，因此实际默认目录为 `backend/uploads` |
| `MAX_UPLOAD_SIZE_MB` | `20` | 单文件上限 |
| `ALLOWED_FILE_EXTENSIONS` | `.pdf,.md,.markdown,.txt` | 扩展名白名单 |
| `DATABASE_URL` | `sqlite:///./data/personal_learning.sqlite3` | 默认 SQLite 文件 |

上传目录和数据库目录均在 `.gitignore`：

```text
backend/uploads/
backend/data/
```

存储规则：

- 原始文件名经过 `Path(filename).name` 去除路径；
- 删除 NUL，替换回车、换行和 Tab，并截断到 255 字符；
- 本地存储名为 `uuid4().hex + 原扩展名`；
- `Material.original_filename` 保留安全化后的原文件名；
- `Material.file_path` 保存 `path.resolve()` 生成的绝对路径；
- MIME 不采用客户端值，而是按扩展名映射；
- 文件按 1 MB 分块读取，不一次性加载进内存。

## 4. 删除逻辑

前端调用链：

```text
MaterialsPage 删除按钮
  └─ window.confirm
      └─ materialsApi.remove(id)
          └─ DELETE /api/materials/{id}
              └─ 成功后失效 ["materials"] 查询
```

后端调用链：

```text
delete_material()
  ├─ get_or_404(db, Material, id, "资料")
  ├─ 保存 material.file_path
  ├─ db.delete(material)
  ├─ commit(db)
  ├─ delete_material_file(material)
  │   └─ Path(material.file_path).unlink(missing_ok=True)
  └─ 204 + X-Deleted-File 响应头
```

需要注意的实际边界：

- 当前顺序是先提交数据库删除，再删除本地文件；
- SQLite 事务与文件系统删除不是同一原子事务；
- `missing_ok=True` 允许文件已不存在时仍完成记录删除；
- 如果数据库提交后遇到文件权限等 `unlink` 错误，可能遗留孤立文件；
- V1 测试覆盖正常删除时数据库记录和本地文件同时消失。

## 5. 资料页面和前端 API 位置

| 文件 | 职责 |
|---|---|
| `frontend/src/pages/MaterialsPage.tsx` | 拖拽/选择、搜索、筛选、列表、状态、删除确认和 Toast |
| `frontend/src/api/resources.ts` | `materialsApi.list/upload/remove` |
| `frontend/src/api/client.ts` | API 基地址、fetch、FormData 处理、统一错误 |
| `frontend/src/types/index.ts` | `Material` TypeScript 类型 |
| `frontend/src/utils/format.ts` | 文件大小、日期和状态文案 |
| `frontend/src/test/App.test.tsx` | 前端上传调用测试 |

前端默认 API：

```text
VITE_API_BASE_URL=http://127.0.0.1:8000/api
```

## 6. Alembic 当前版本

当前数据库与迁移头均为：

```text
20260729_0001 (head)
```

迁移文件：

```text
backend/alembic/versions/20260729_0001_initial_v1.py
```

该迁移一次性创建：

- `learning_goals`
- `materials`
- `courses`
- `knowledge_points`
- `daily_tasks`
- `learning_sessions`

V2 必须创建新的增量迁移，不允许重写、重排或删除 `20260729_0001`。

## 7. V2 可以复用的接口

### 可直接保持兼容

- `POST /api/materials/upload`：本地文件进入系统的稳定入口；
- `GET /api/materials`：资料收件箱、名称搜索和类型筛选；
- `GET /api/materials/{id}`：处理详情和后续内容页的资料主记录入口；
- `DELETE /api/materials/{id}`：资料生命周期删除入口；
- `GET /api/meta`：前端获取允许类型、大小和上传目录；
- `Material.id`：后续 Chunk、处理任务、课程关联和引用的外键基础；
- `Material.file_path`：本地解析器读取源文件的位置；
- `Material.processing_status` 和 `error_message`：可扩展处理状态与失败说明；
- `Settings`、`DbSession`、统一 `AppError` 和错误响应；
- TanStack Query 的 `["materials"]` 缓存键与 `materialsApi` 封装。

### 复用时必须澄清的语义

V1 的 `ready` 只表示“文件保存成功”。如果 V2 把它改为“解析和索引完成”，必须提供迁移和前后端兼容方案，不能无声改变已有数据含义。

## 8. V2 预计新增和修改的文件

以下只是后续实施预估，本轮没有创建这些文件。

### 预计新增

```text
backend/app/models/material_chunk.py
backend/app/models/material_processing_job.py        # 仅在确有持久化任务状态需要时
backend/app/schemas/material_chunk.py
backend/app/schemas/material_processing.py
backend/app/repositories/materials.py                # 若查询与事务复杂度达到需要
backend/app/repositories/material_chunks.py
backend/app/services/material_processing/
├─ parsers/
│  ├─ base.py
│  ├─ pdf.py
│  ├─ markdown.py
│  └─ text.py
├─ cleaning.py
├─ chunking.py
└─ pipeline.py
backend/tests/test_material_parsers.py
backend/tests/test_material_chunking.py
backend/tests/test_material_processing_api.py
backend/alembic/versions/<new_revision>_material_processing.py
```

如果 V2 范围包含 Embedding、FAISS、RAG 或 LLM，再在 V2 的独立任务审查后决定对应目录；本交接不预设实现。

### 预计修改

```text
backend/app/models/material.py
backend/app/models/__init__.py
backend/app/models/enums.py
backend/app/schemas/material.py
backend/app/api/routes/materials.py
backend/app/api/router.py
backend/app/core/config.py
backend/requirements.txt
frontend/src/types/index.ts
frontend/src/api/resources.ts
frontend/src/pages/MaterialsPage.tsx
frontend/src/test/App.test.tsx
.env.example
docs/api.md
docs/data-model.md
README.md
```

修改应通过新增字段、接口或页面状态渐进完成，不应把现有上传 CRUD 整体推倒重写。

## 9. V1 不允许被破坏的行为

1. 仍然支持 PDF、MD、Markdown、TXT 上传；
2. 原始文件名与 UUID 存储文件名分离；
3. 继续执行服务端类型、大小和空文件校验；
4. 大文件继续分块读取，不能退化为一次性读入内存；
5. 保存或数据库失败时清理部分文件并回滚；
6. 上传成功后页面刷新仍能从 SQLite 读取资料；
7. `GET /api/materials` 的名称搜索、类型筛选和新到旧排序保持可用；
8. `GET /api/materials/{id}` 对不存在记录继续返回统一 404；
9. 删除资料时数据库记录和本地文件都必须清理；
10. 现有 `MaterialRead` 字段和现有 API 路径保持兼容；
11. 非法类型继续返回 415，超大文件继续返回 413，空文件继续返回 422；
12. 测试继续使用临时 SQLite 和临时上传目录，不能写入真实用户目录；
13. `.gitignore` 继续忽略 SQLite、上传内容、虚拟环境和构建产物；
14. 现有目标、课程、知识点、今日任务和学习会话链路不能因资料处理改造而回归；
15. V2 数据库改动必须使用新的 Alembic 增量迁移；
16. 前端不能用硬编码资料或处理状态冒充后端结果；
17. 新增处理失败必须写入清晰状态和错误信息，不能只返回 500 堆栈；
18. V1 的单用户本地启动命令和 Windows PowerShell 运行方式保持有效。

## 10. 当前测试与验收命令

### 后端测试

```powershell
Set-Location .\backend
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe -m compileall app ..\scripts
..\.venv\Scripts\alembic.exe check
Set-Location ..
```

当前基线：`9 passed`，Alembic 无待生成变更。

### 前端测试、Lint 和构建

```powershell
Set-Location .\frontend
npm run test
npm run lint
npm run build
Set-Location ..
```

当前基线：`7 passed`，ESLint、TypeScript 和 Vite build 通过。

### 真实 API 验收

先启动后端：

```powershell
Set-Location .\backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

在另一个 PowerShell 窗口执行：

```powershell
.\.venv\Scripts\python.exe .\scripts\acceptance_v1.py
```

预期输出：

```json
{
  "status": "passed"
}
```

V2 开发开始前应先执行上述基线命令；V2 完成后必须再次执行，并新增资料解析相关测试，而不是替换 V1 测试。
