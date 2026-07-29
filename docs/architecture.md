# V1 架构

## 边界

PersonalLearning V1 是本地单体应用：React 前端通过 HTTP 调用 FastAPI，FastAPI 使用 SQLAlchemy 访问 SQLite，并把上传文件保存到本地受控目录。

```text
React + TanStack Query
          │ JSON / multipart
          ▼
FastAPI 路由 + Pydantic Schema
          │
          ├─ CRUD / 聚合服务 ── SQLAlchemy ── SQLite
          │
          └─ MaterialService ──────────────── 本地 uploads/
```

V1 不包含模型调用、异步任务、向量索引或 Agent 运行时。

## 后端分层

- `app/api/routes`：HTTP 路由、状态码、依赖注入和响应 Schema；
- `app/schemas`：请求与响应的 Pydantic 模型；
- `app/services`：通用 CRUD、文件保存/删除、Demo 数据事务；
- `app/models`：六张 SQLAlchemy 表和状态枚举；
- `app/db`：Base、命名约定、会话工厂和 SQLite 外键设置；
- `app/core`：环境配置与统一错误处理；
- `alembic`：显式数据库迁移。

写操作以单个数据库会话为事务边界。出现异常时回滚；API 不直接序列化 SQLAlchemy 实例，而是转换为 Pydantic 响应。

## 前端结构

- `src/api`：统一请求、错误解析和资源 API；
- `src/types`：前后端数据契约的 TypeScript 类型；
- `src/layouts`：桌面侧边栏、移动导航和路由出口；
- `src/pages`：今日、课程、资料、复习、进度、设置和学习会话；
- `src/components`：Dialog、Toast、表单与统一状态组件；
- `src/test`：路由、加载、CRUD 交互和错误状态测试。

页面使用 TanStack Query 读取真实 API。变更成功后按资源失效缓存，页面刷新时重新从 SQLite 读取。

## 基础学习链路

1. 今日页读取 `/api/today`；
2. 用户从任务创建或恢复 `learning_session`；
3. 前端跳转 `/learning-sessions/{id}`；
4. 工作台读取会话、课程知识点和任务；
5. 用户保存笔记、暂停/继续或完成；
6. 完成请求在一个事务中同步更新会话、知识点和今日任务状态；
7. 今日页与进度页重新聚合真实数据。

## 文件安全

- 扩展名白名单：PDF、MD、Markdown、TXT；
- 服务端流式计数并执行大小限制；
- 存储文件名使用 UUID，与原始文件名分离；
- 文件保存在配置目录内；
- 删除数据库记录时同步删除对应文件；
- 测试通过临时目录隔离上传内容。

## 后续扩展点

后续版本可在 `services` 下增加解析、检索与教学模块，并把资料处理状态扩展为更细阶段。V1 没有创建空的 LLM、RAG、MCP 或 Agent 假实现，也没有相关运行依赖。
