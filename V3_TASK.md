# PersonalLearning V3 任务

## 版本目标

在 V2 本地知识库之上实现可信引用式 RAG 学习问答：

```text
会话与问题
→ 有限历史 Query Rewrite
→ 复用 V2 BGE-M3 + FAISS
→ 来源筛选与上下文预算
→ Answerability Gate
→ OpenAI-compatible LLM Structured Output
→ 引用校验
→ 回答或稳定拒答
→ 消息与引用快照持久化
→ 受控 SSE 与前端恢复
→ 可量化评测
```

## 实施阶段

- [x] 阅读 V3 完整要求和 V2 真实代码/文档
- [x] 执行 Git、迁移、后端、前端基线检查
- [x] 重新运行 V1、V2 真实验收
- [x] 新增 `0003` 增量迁移及 Conversation、Message、Citation
- [x] 实现 Repository 与 Pydantic API Schema
- [x] 实现 OpenAI-compatible LLM Provider 与 FakeLLM
- [x] 实现 Query Rewrite、Retrieval、Context、Gate、Prompt 和 Citation Validator
- [x] 实现幂等问答事务与历史引用快照
- [x] 实现 Conversation CRUD、同步问答、受控 SSE 和状态 API
- [x] 实现资料问答页面、来源详情和资料范围
- [x] 完成后端、前端和 Prompt Injection 测试
- [x] 实现 V3 评测体系、数据集和评测脚本
- [x] 实现并运行 V3 真实 HTTP + 真实 LLM 验收
- [x] 重新运行 V1、V2、V3 验收和全部发布检查
- [x] 更新 README、架构、API、数据模型、RAG 和评测文档
- [x] 审计 Git 差异，通过后提交并创建 `v3.0.0`

## 明确不实现

- LangGraph、Agent Planner、多工具和外部联网工具；
- 自动课程、学习计划、出题、批改和掌握度；
- OCR、图片、音频、视频和网页爬取；
- Redis、Celery、消息队列、微服务、多用户、登录和云部署。

## 发布门槛

Alembic、全部后端测试、compileall、全部前端测试、Lint、Build、V1/V2/V3 验收和 V3 评测全部实际通过后，才允许提交和创建 `v3.0.0`。
