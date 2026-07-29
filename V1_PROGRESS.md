# PersonalLearning V1 进度

最后更新：2026-07-29

## 已完成

- 完成空工作区、Git 状态、目录、依赖、模型、API、页面和测试审查；
- 创建 `V1_RESUME_AUDIT.md`；
- 确认本机 Python 3.11、Node.js 24 与 npm 11 可用；
- 明确 V1 边界和验收标准；
- 建立 React + TypeScript + Vite 前端和 FastAPI 后端；
- 完成六张 SQLAlchemy 表、状态约束和首个 Alembic 迁移；
- 完成目标、资料、课程、知识点、任务、会话 CRUD；
- 完成安全文件上传、元数据保存和文件同步删除；
- 完成六个核心页面与基础学习会话工作台；
- 完成真实进度聚合、基础复习列表和设置页；
- 完成幂等 Demo 导入、清理与开发数据库重置脚本；
- 完成后端、前端、Lint、TypeScript、构建、迁移一致性和真实 API 验收；
- 完成桌面端、390px 移动端和七个页面的真实浏览器检查；
- 完成 README、架构、数据模型和 API 文档。

## 进行中

- 无。V1 已按收敛范围完成。

## 尚未开始

- V2 及以后：LLM、RAG、Agent、SSE、自动出题、掌握度、自动复习、MCP 和外部资料源。本轮未开始。

## 验证记录

- Alembic `upgrade head`：通过，当前版本 `20260729_0001`；
- Alembic `check`：通过，无未生成结构变更；
- 后端 pytest：`9 passed`；
- Python `compileall`：通过；
- 前端 Vitest：`7 passed`；
- ESLint：通过；
- TypeScript + Vite 生产构建：通过，按页面拆包；
- `scripts/acceptance_v1.py`：六个验收场景全部通过；
- 后端健康检查：`{"status":"ok"}`；
- Vite 生产预览：HTTP 200；
- 浏览器检查：今日、课程、资料、复习、进度、设置、学习会话页均从真实 API 加载；390px 移动端无横向溢出。

## 验收场景结果

1. 创建“三周入门 MCP”目标并独立 GET：通过；
2. 上传 PDF 与 Markdown、显示元数据、删除文件和记录：通过；
3. 手动创建“MCP 基础”与六个知识点：通过；
4. 创建今日任务并由 `/api/today` 返回：通过；
5. 创建/恢复学习会话、保存笔记、完成知识点和任务：通过；
6. 首页与 `/api/progress` 更新完成数和七天会话：通过。

## 当前遗留

- Vite 开发服务器默认 5173 端口在本次受限验收环境中不可绑定；生产预览使用 4173 成功。正常 Windows 本地环境仍按 README 使用 5173；
- 进度页的 Recharts 路由包约 369 kB，已与主包拆分，不影响 V1；
- 自动复习、资料解析和 AI 能力明确留到后续版本。
