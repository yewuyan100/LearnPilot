# 评测隔离与夹具边界

普通 pytest 和前端测试使用临时业务 SQLite、临时 checkpoint、临时上传目录与临时 FAISS，并注入 FakeEmbedder、FakeLLM 和固定时间。它们不读取个人知识库，不加载真实 BGE-M3，也不调用外部模型。这样的测试适合验证状态机、事务、排序稳定性、引用契约和错误语义。

真实 acceptance 使用另一组临时存储，加载真实 `BAAI/bge-m3`；需要回答模型的阶段再使用本地配置的 OpenAI-compatible provider。只把 `evals/fixtures` 中明确标记的人工材料发送给模型，避免把个人资料和生产数据库混入验证。

测试 fixture 与 demo corpus 不是同一概念。fixture 通常很短，并为了触发单个断言而刻意写入关键词、攻击文本或精确数字；它可以稳定证明某个回归没有发生，却不能代表真实检索分布。demo corpus 是一个有版本、来源清楚、主题互相覆盖的封闭文档集合，用于比较多种问题类型和引用行为。

Gold cases 也不应与运行时 Material ID 或 source label 绑定。Material ID 由每次隔离导入产生，S1、S2 由每次检索最终顺序产生。gold contract 只保存稳定 document IDs；评测导入器建立 document ID 到 Material ID 的映射，再用 response citation 中的 original filename 或映射后的 ID 判定命中。

一次正式 eval run 必须记录 corpus version、manifest schema、gold schema、Embedding model/revision/dimension、索引 version、RAG 配置、prompt version、LLM model 和运行时间。缺少其中任何关键配置时，不应把结果与另一轮直接比较。
