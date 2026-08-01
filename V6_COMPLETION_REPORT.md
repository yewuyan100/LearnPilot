# V6 完成报告

1. 开发前基线：`d1689d5` / `v5.0.0` / Alembic `20260801_0005`；后端 79、前端 20；V1–V5 真实隔离验收 passed。发现并保护既有 `V5_COMPLETION_REPORT.md` 未提交修改。
2. 新增文件：0006 迁移、五个模型、adaptive_learning 服务包、mastery/reviews/adaptive/metrics routes、V6 后端与前端测试、三个页面、V6 夹具/评测/验收、算法/调度/面试/发布文档。
3. 修改文件：配置、模型导出、Router、测验/错题/任务/会话生命周期、Agent schema/state/graph/tools/service、前端路由/导航/API/types/styles、Demo、README 与最终文档。
4. Alembic：`20260801_0006 (head)`；未修改 0001–0005；`0006 → 0005 → 0006`、current、heads、check 通过。
5. 数据模型：`KnowledgeMastery` 当前状态、`MasteryEvidence` 不可变事实、`MasterySnapshot` 不可变历史、`ReviewSchedule` 日程、`AdaptiveRecommendation` 建议。
6. Evidence 类型：objective_quiz、short_answer_quiz、wrong_answer、successful_review、task_completion、learning_session、self_assessment。
7. Evidence 去重：`source_type + source_id + evidence_type` 唯一，另存内容哈希；重建幂等。
8. 掌握度算法：`mastery-rule-v1`，每类近期 N 条 + 30 天半衰期 + 类别聚合 + 现有类别权重归一化 + 两位 Decimal 舍入。
9. 权重：0.40 / 0.25 / 0.15 / 0.08 / 0.07 / 0.05；这是项目工程规则，不是教育科学结论。
10. 时间衰减：`0.5 ^ (age_days / 30)`，每类最多 10 条，固定时间可注入。
11. 缺失证据：缺失类别不记零，仅在现有类别重归一化；完全无证据为 null + unassessed + confidence 0。
12. 置信度：证据数 40%、多样性 25%、新鲜度 25%、直接测验 10%，另有确定性冲突惩罚，独立于掌握度。
13. Snapshot：有意义变化才追加；相同结果不重复；保存类别分、选中证据 ID、触发与算法版本。
14. 薄弱点：低掌握 50%、低置信 15%、近期失败 20%、逾期 15%；unassessed 与 weak 分离。
15. 复习调度：beginner 1 天、developing 3 天、proficient 7 天、strong 14 天；strong 低置信 7 天；失败 1 天；active 错题最晚 3 天；逾期保留原日期。
16. Recommendation：V6 完整实现 `review_task`；事实、优先级、日期和时长由代码生成，无 LLM 也可模板输出。
17. Agent 新增工具：5 个只读掌握度/薄弱点/到期/建议/解释工具，1 个 `accept_review_recommendation` 受控写工具。
18. 人工确认：Agent 写入继续冻结参数、哈希校验、interrupt 与 Command(resume)；普通接受 API 要求 `confirmed=true`。
19. 幂等：Evidence 唯一键、Snapshot 变化检测、单活跃 Schedule、Recommendation `created_task_id`、Agent ToolCall/Confirmation/Checkpoint 多层保护。
20. 前端：掌握度总览、详情、证据、快照、低置信提示、自评、复习分组、建议确认/拒绝与 Agent 原页面复用。
21. 性能优化：明确任务/错题/掌握度/薄弱点/复习查询确定性快速路由；Planner 和 Composer 模板跳过；写请求不快速路由。
22. LLM 调用变化：V5 明确查询通常为分类 + 规划 2 次；V6 明确只读快速路径为 0 次。模糊查询与写请求仍调用模型。
23. V5/V6 延迟：本轮最终真实 V5 评测平均 22547.73 ms、P50 12320.45、P95 47062.32；V6 固定本地快速路由评测平均 0.062 ms、P50 0.059、P95 0.142，且平均 LLM 调用为 0。工作负载不同，只能说明确定性快速路由移除了模型往返，不能作通用生产对比；Token 对比因 V5 未持久化 usage 而不可得。
24. 后端测试：92 项通过；新增 13 项覆盖无证据、归一化、衰减、最近 N、冲突权重、自评/去重、API、建议确认/拒绝/幂等、Agent 工具/安全/快速路由/指标。
25. 前端：24 项通过，ESLint 与生产 Build 通过。
26. V1–V6 验收：V1–V6 passed；V2–V6 使用真实 BGE-M3，V3–V6 使用真实 OpenAI-compatible LLM；V6 为 `deepseek-v4-flash`。
27. V6 评测：12/12 固定合成场景；确定性、范围、等级、安全和工具选择指标 1.0；不代表通用教育效果。
28. 重启恢复：真实 V6 验收停服后 Mastery/Snapshot/Schedule/Recommendation 仍在，待确认 Run 恢复并只写一次。
29. 已知限制：单用户/单机/SQLite/FAISS，无多 Agent、外部 MCP、联网、OCR、多用户、云部署或复杂机器学习掌握度。
30. 演示数据：`[DEMO]` 目标、课程、知识点、任务、会话、活动、Attempt、Answer、WrongAnswer、Mastery/Snapshot/Schedule/Recommendation；重复 seed/clear 通过。
31. 面试文档：`docs/interview-guide.md` 覆盖两分钟介绍、全链路、RAG、LangGraph、Checkpoint、确认、幂等、批改、掌握度与取舍。
32. Git diff：仅 V6 实现与文档；现有 `V5_COMPLETION_REPORT.md` 用户修改不纳入 V6 提交。
33. Commit：发布门禁全部通过，使用 `feat: add adaptive mastery review and final project release`。
34. Tag：创建 `v6.0.0`，指向 V6 最终提交。
35. 主线结论：V6 完成后 PersonalLearning 主线开发结束并冻结架构，不自动创建 V7。

V6 未实现多 Agent、MCP 外部资料源、OCR、多用户、云部署和复杂机器学习掌握度模型。这些能力不属于 PersonalLearning 主线完成条件。
