# 持久化与事务边界

LearnPilot 使用 SQLite 保存业务事实，使用另一份 SQLite 保存 LangGraph checkpoint，并使用 FAISS 文件保存向量索引。三种存储承担不同职责：业务库是 Material、Chunk、会话、消息与引用的事实来源；checkpoint 保存可恢复的图状态；FAISS 是可由业务数据重建的派生索引。

上传资料时，系统先把文件写到受控上传目录，再提交 Material 记录。发生异常时数据库回滚并删除刚写入的文件。资料处理会先提交 processing 状态，使并发请求能看到正在处理；解析与切块成功后，在一个数据库事务中替换该资料的 chunks 并更新计数和完成时间。处理失败会回滚未完成的 chunk 替换，并单独持久化失败状态和可读错误。

索引重建先从数据库读取全部可索引 chunks，再生成向量。FAISS 和其 Manifest 通过临时文件、校验与备份方式保存；保存成功后才把各 Material 的 indexing status、indexed chunk count 与 indexed time 提交到业务库。索引是派生数据，因此损坏或配置变化时应重建，而不是修补数据库中的 chunk 事实。

RAG 提问先建立用户消息与 pending assistant message 的关联，并用 conversation ID 与 request ID 唯一约束处理并发重放。有效回答的 citations 与 assistant message 在同一业务工作单元中提交。相同 request ID 和相同问题返回已有结果；相同 ID 对应不同问题或范围时返回冲突。

跨 SQLite 和 FAISS 不存在分布式事务。系统通过状态字段、内容校验和、维护任务和可重试重建收敛。评测因此既要观察最终回答，也要把 stale index、index unavailable、provider failure 等运行状态作为不同失败类别，不能全部统计成检索未命中。
