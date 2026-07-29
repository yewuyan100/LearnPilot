# 错题闭环

## 创建规则

批改成功后，系统从真实 QuizAnswer 确定性创建错题：

- 客观题得分为零：`incorrect`；
- 简答题得分比例低于 `WRONG_ANSWER_SHORT_ANSWER_THRESHOLD`：`partial` 或 `incorrect`；
- 未作答：`unanswered`。

正确答案不创建错题；`(attempt_id, answer_id)` 唯一，重复提交不会生成重复记录。

## 状态

错题支持 `active`、`reviewing`、`resolved`、`dismissed`。用户可手动标记已掌握或忽略；这只是用户状态，不是算法掌握度。

## 复习

用户可选择一个或多个错题创建独立、已发布的 `review` Activity。复习题复制原题、答案、Rubric、解析和来源快照，不依赖原资料继续存在。系统立即创建新的 Attempt。

复习提交后，正确完成的对应错题增加 `review_count`、记录 `last_reviewed_at` 并转为 `resolved`；仍错误则保持待复习状态。映射保存在复习 Activity 的来源范围快照中，不靠模型推断。

错题列表支持按状态、课程和知识点筛选；详情和结果页可查看解析与来源。V4 不计算掌握度、不使用 FSRS，也不做自适应复习排程。
