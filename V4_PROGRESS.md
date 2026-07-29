# PersonalLearning V4 进度

最后更新：2026-07-30

## 开发前真实基线

- 工作区：干净；
- HEAD：`b831f3e050d3c7e1a6f246685cb618bd22fbfc69`；
- 提交：`feat: add grounded rag conversations with citations`；
- 标签：`v3.0.0`；
- Alembic current / heads：`20260730_0003 (head)`；
- Alembic check：通过；
- 后端 pytest：`58 passed`；
- Python compileall：通过；
- 前端 Vitest：`15 passed`；
- ESLint、TypeScript、Vite production build：通过。

## 当前阶段

- V4 增量迁移、六个数据模型、题目生成/验证、草稿发布、Attempt、批改、错题与学习联动已完成；
- 活动列表/生成、草稿管理、四类题型作答、结果和错题本页面已完成；
- 后端 `74 passed`，compileall、Alembic current/heads/check 通过；
- 前端 `19 passed`，ESLint 和 production build 通过；
- V2 真实 BGE-M3 验收通过：1024 维、3 份资料、检索/重启/幂等重处理/删除均验证；
- V1 隔离验收通过；
- V3 真实 LLM 回归通过：会话持久化、引用快照、删除来源过滤和 SSE 均验证；
- V4 真实验收通过：`BAAI/bge-m3` + `deepseek-v4-flash`，生成、来源、客观/简答批改、错题、复习、幂等、注入防护、重启和来源快照均验证；
- V4 小型人工回归集评测完成：结构、来源、答案键、Rubric、数量、注入防护、客观批改、简答容差、错题创建/去重/解决指标均为 `1.0`，重复率、生成失败率、无效/失败评分率和简答区间 MAE 均为 `0.0`；
- 平均生成延迟 `12167.105 ms`，平均简答批改延迟 `1907.427 ms`；
- 上述小型评测仅代表专用回归夹具，不代表通用教学质量。

## 最终发布门禁

Alembic upgrade/current/heads/check、后端 74 项测试、compileall、前端 19 项测试、ESLint、production build、V1–V4 验收、V4 评测和敏感信息扫描均已通过。

## 验证纪律

- 普通测试只使用临时 SQLite、上传目录、FAISS、FakeEmbedder 和 FakeLLM；
- 真实 BGE-M3 与真实 LLM 只在独立验收和评测中运行；
- 不读取或修改个人知识库来构造评测；
- 不把 FakeLLM 结果描述为真实 LLM 验收；
- 未实际运行的门禁不记录为通过。
