# 拒答与运行失败不是同一件事

LearnPilot 的 answerability gate 先判断是否存在可交给模型的真实来源。资料范围为空、索引不存在、索引过期、搜索不可用、没有向量结果、全部候选低于阈值或上下文为空时，系统返回固定的资料不足答复，`answerable=false` 且 citations 为空。Prompt injection 请求也会在生成前拒绝。

模型收到来源后仍可以声明资料不足。合法的模型拒答必须 `answerable=false`、blocks 为空并带 refusal reason；后端不会为拒答保存 citation。若模型声称可回答，却缺少 evidence block、引用未知来源或在正文中伪造 source syntax，系统先尝试一次契约修复，仍失败则转为稳定拒答。

基础设施失败有不同语义。已经检索到资料但 LLM 未配置时，接口返回 503；provider 超时、鉴权失败、无效结构化输出等服务错误也不应被统计为正确拒答。并发索引构建、stale index 和 request ID 冲突同样需要单独记录。

Unanswerable gold case 的预期不是“回答里出现抱歉”，而是 `answerable=false`、没有引用，并且 refusal reason 属于允许类别。Answerable case 如果因为 LLM 未配置而返回 503，不能算作拒答准确；它是 eval 环境未就绪。相反，如果检索到的文档只与问题主题相似、没有关键事实，模型拒答应被视为正确行为。

评测报告至少应分开统计 retrieval miss、wrong-source retrieval、answerability error、citation error、grounding validation fallback 和 infrastructure error。把这些合成一个失败率会掩盖真正需要修复的层级。
