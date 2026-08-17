# 可观测性、版本与可复现性

可复现的 RAG 结果需要同时冻结语料、问题契约和运行配置。Corpus Manifest 为每篇文档分配稳定 document ID，记录 title、topic、source type、source reference、version/date、language、预期 ingestion type、仓库相对路径和内容 SHA-256。文件内容变化必须产生新的校验和，并应形成新的 corpus version，而不是静默覆盖已经用于基线的 V1。

FAISS Manifest 是不同的运行时对象。它记录一次导入后的 chunk IDs、Embedding 配置、维度、内容校验和、索引校验和和随机 index version。Corpus Manifest 描述离线输入；FAISS Manifest 描述某次运行时派生索引。二者不能合并，也不能用 index version 代替 corpus version。

Gold Case 保存 question、difficulty、type、answerable、expected document IDs、key facts 和 citation expectations。答案文字可以变化，但关键事实和来源集合提供稳定判断依据。`multi_doc` case 至少需要两份文档共同支持；`citation_sensitive` case 要求每个可核验事实绑定正确来源；`unanswerable` case 的 expected document IDs 与 key facts 为空。

运行时已经暴露 retrieval query、top K、candidate/source counts、最低分、index version、检索时延、resolved material IDs、模型名、prompt version、answerability、refusal reason 和 citations。评测器应保存这些原始结果，再派生 Hit@K、source precision、citation validity/coverage、answerability accuracy 和分层失败计数。

固定仓库契约通过只说明这些受控输入上的工程行为，不代表真实教育效果、通用 Agent 能力或生产分布表现。报告必须标出样本数、语料版本和限制，避免用小型 demo corpus 宣称普适质量。
