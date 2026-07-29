# PersonalLearning V4 完成报告

> 状态：实现、隔离测试、真实模型验收、V4 小型回归评测与最终发布门禁均已完成。

## 1. 开发前基线

- 版本 / 标签：`v3.0.0`
- HEAD：`b831f3e050d3c7e1a6f246685cb618bd22fbfc69`
- 提交：`feat: add grounded rag conversations with citations`
- Alembic：`20260730_0003 (head)`，check 通过
- 后端：`58 passed`，compileall 通过
- 前端：`15 passed`，lint / build 通过
- 工作区：clean

## 2. 实际新增文件

- 迁移：`backend/alembic/versions/20260730_0004_learning_activities.py`
- 模型：`learning_activity.py`、`activity_question.py`、`question_source.py`、`quiz_attempt.py`、`quiz_answer.py`、`wrong_answer.py`
- API：`learning_activities.py`、`quiz_attempts.py`、`wrong_answers.py`
- Schema：`backend/app/schemas/learning_activity.py`
- 服务：`services/learning_activities/*`、`services/grading/*`、`services/quiz_attempts.py`、`services/wrong_answers.py`
- 后端测试：`test_activity_validation.py`、`test_learning_activities_api.py`
- 前端页面：`ActivitiesPage.tsx`、`ActivityBuilderPage.tsx`、`QuizAttemptPage.tsx`、`QuizResultPage.tsx`、`WrongAnswersPage.tsx`
- 前端测试：`ActivitiesV4.test.tsx`
- 评测/验收：`evals/fixtures/v4/*`、`activity_generation_dataset.json`、`grading_dataset.json`、`scripts/acceptance_v4.py`、`scripts/evaluate_v4.py`
- 文档：`V4_TASK.md`、`V4_PROGRESS.md`、本报告、`docs/learning-activities.md`、`docs/grading.md`、`docs/wrong-answers.md`

## 3. 实际修改文件

`.env.example`、`README.md`、后端 Router/配置/模型与 Schema 导出、DailyTask、共享 LLM Provider、测试 Fake、V1/V3 验收脚本、前端版本/路由/API/布局/类型/样式，以及架构、API、数据模型和评测文档。

## 4. 数据库与模型

- Alembic head：`20260730_0004`
- 新表：`learning_activities`、`activity_questions`、`question_sources`、`quiz_attempts`、`quiz_answers`、`wrong_answers`
- `daily_tasks` 新增可空 `activity_id`
- 唯一约束覆盖生成/提交幂等、活动内题序、Attempt+Question、Attempt+Answer 和题目来源标签
- Material/Chunk、Course/KnowledgePoint 等历史外键按职责使用 `SET NULL` 或级联
- 隔离数据库已实际验证 `upgrade head → downgrade 0003 → upgrade head`
- V1–V3 历史迁移未修改

## 5. Activity 生命周期与题型

`draft → published → archived`。草稿支持标题/描述、删题和排序；发布会重新校验，发布后题目核心内容不可原地修改。当前支持单选、多选、判断和简答，生成题数不得少于所选题型数。

活动必须显式选择已解析且已索引的资料。课程和知识点只增加学习语境，不会取消资料边界或触发无边界全库出题。

## 6. 来源快照、生成与 Structured Output

生成复用 V2 `MaterialIndexService`、BGE-M3、FAISS 和 SQLite Chunk 回查。候选来源经过相关度、去重、来源数、单段字符和总字符预算后标记为 `S1…Sn`。

LLM 只选择本次上下文 Source ID；文件名、页码、章节由数据库确定。每题至少一个合法来源。QuestionSource 保存受限摘录，资料删除后外键置空而快照保留。

生成输出使用 `extra=forbid` 的 Pydantic 契约。题型字段、答案、选项、Rubric、分值、来源子集、题型覆盖和重复题均经过跨字段验证。无效输出整批最多修复一次，失败不写入半批 Activity。

## 7. 批改与总分

- 客观题：确定性代码评分；多选按集合比较；漏选、错选、非法选项和未作答严格处理，不调用 LLM。
- 简答题：`short-answer-grading-v1`、温度 0；固定 Rubric、结构化命中/缺失项、反馈和置信度；Rubric ID 与得分边界由代码复核。
- 失败语义：模型、解析或校验失败保留 `failed` 与空得分，不伪装为零分；同一 request_id 和答案快照可重试。
- 聚合：Decimal 汇总总分、百分比和正确/错误/部分得分数量；只有全部成功才完成 Attempt。

## 8. 错题闭环

客观题零分、简答题低于配置阈值和未作答会从真实 QuizAnswer 创建错题；`(attempt_id, answer_id)` 去重。错题支持 active/reviewing/resolved/dismissed。

复习会复制题目、答案、Rubric、解析与来源快照为新的 published review Activity。再次满分时增加 `review_count`、记录时间并 resolved；未满分回到 active。V4 不计算掌握度。

## 9. 学习会话、任务与幂等

Attempt 可关联 LearningSession。成功批改后才完成会话及匹配的 DailyTask；LLM 不能修改这些状态。

生成以 request_id + 配置哈希幂等，提交以 request_id + 答案哈希幂等，复习创建同样幂等。冲突请求返回 409。进程锁缩小同进程并发窗口，数据库唯一约束提供最终保护。

## 10. Prompt Injection 防护

资料和用户简答均以不可信标签包裹。Prompt 明确禁止执行其中指令、泄露 Prompt/Key、改变题型/答案/Rubric 或索要满分。模型输出仍必须通过来源、结构与评分代码校验。日志不记录 Key、完整 Prompt、完整资料、完整简答或模型推理。

## 11. 自动化验证

- 后端：`74 passed`
- Python compileall：通过
- Alembic current / heads / check：`20260730_0004 (head)` / 通过
- Alembic 隔离升级、降级、再升级：通过
- 前端：`19 passed`
- ESLint：通过
- TypeScript + Vite production build：通过
- V1 隔离验收：passed
- V2 真实 BGE-M3 验收：passed；模型 `BAAI/bge-m3`、1024 维、3 份资料，检索/重启/幂等重处理/删除通过
- V3 真实 LLM 回归：passed；会话持久化、引用快照、删除来源过滤和 SSE 通过
- V4 真实 LLM 验收：passed；`BAAI/bge-m3` + `deepseek-v4-flash`
- V4 验收覆盖：生成、真实来源、客观/简答批改、错题、复习、幂等、注入防护、重启恢复和来源删除快照
- V4 真实评测：completed

## 12. V4 评测

脚本会输出生成 Schema/来源/答案键/Rubric/重复率/数量完成/注入防护/失败率/延迟，客观题准确率，简答题区间 MAE/容差/Rubric/无效与失败率/延迟，以及错题创建/去重/复习解决指标。

实际指标：

| 指标 | 结果 |
|---|---:|
| Schema / 来源 / 答案键 / Rubric 有效率 | `1.0` |
| 请求题数完成率 / 注入防护率 | `1.0` |
| 重复题率 / 生成失败率 | `0.0` |
| 平均生成延迟 | `12167.105 ms` |
| 客观题批改准确率 | `1.0` |
| 简答区间 MAE | `0.0` |
| 简答容差率 / Rubric 匹配率 | `1.0` |
| 无效评分率 / 批改失败率 | `0.0` |
| 平均简答批改延迟 | `1907.427 ms` |
| 错题创建 / 去重 / 复习解决准确率 | `1.0` |

评测集是人工可核验的小型回归集，仅代表两个生成用例、三个简答用例和固定错题流程，不代表通用教学质量或通用评分准确率。

## 13. 已知限制

V4 未实现 LangGraph、Agent、掌握度、FSRS、自适应计划、多 Agent、外部 MCP 资料源、OCR、图片/音视频理解、多用户、登录或云部署。SQLite 进程锁适合当前单体单实例边界，不是分布式锁。简答评分仍受所配置模型稳定性影响，因此保留失败与重试状态。

## 14. Git 收口

- `git diff --check`：通过
- 敏感信息与忽略资产扫描：最终提交前复查
- Commit：承载本报告的 V4 功能提交；提交信息为 `feat: add grounded learning activities grading and wrong answers`，精确 hash 记录在最终汇报
- Tag：`v4.0.0`，仅在上述全部门禁通过后创建
