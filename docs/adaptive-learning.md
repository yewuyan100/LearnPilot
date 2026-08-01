# V6 自适应学习闭环

V6 将 V1–V5 的真实业务记录连接成闭环：测验、错题复习、任务、学习会话和自评先转为不可变 `MasteryEvidence`；`mastery-rule-v1` 再计算当前 `KnowledgeMastery` 与不可变 `MasterySnapshot`；薄弱点服务、复习调度器和建议服务据此生成可解释的复习建议。建议不会自动创建任务，必须经普通 API 的显式确认，或经 V5 Agent 的 `interrupt` / `Command(resume)` 确认后写入。

主业务事务优先。测验或任务先提交成功，再刷新掌握度；自适应刷新失败会记录日志并可用 `POST /api/mastery/rebuild` 幂等重建，不会把已成功的主业务伪装成失败。

LLM 只可将确定性原因改写成自然语言。掌握度、置信度、等级、优先级、到期日期和任务状态全部由代码与数据库事实决定。

## 证据来源

| 类型 | 来源 | 用途 |
|---|---|---|
| `objective_quiz` | 已完成的客观题答案 | 直接表现，主权重 |
| `short_answer_quiz` | 已完成且批改成功的简答题 | 直接表现 |
| `wrong_answer` | active 错题 | 近期失败与复习优先级，不重复大幅扣分 |
| `successful_review` | resolved 错题 | 近期复习表现 |
| `task_completion` | 关联知识点且已完成的任务 | 弱正向证据 |
| `learning_session` | 关联知识点、已完成且有有效时长的会话 | 弱参与证据与置信度 |
| `self_assessment` | 1–5 自评 | 低权重补充证据 |

`source_type + source_id + evidence_type` 唯一，重建不会重复累计。证据只保存必要摘要，不保存完整长答案、Prompt、模型内部输出或思维链。
