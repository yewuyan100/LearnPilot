# 索引生命周期、重复导入与删除

LearnPilot 接受 PDF、UTF-8 Markdown 和 UTF-8 TXT。上传阶段检查扩展名、大小和空文件，为存储文件生成随机 UUID 文件名，并创建 Material 记录。Material 的 title 默认取原文件名的 stem。当前上传契约没有按内容哈希或原文件名做去重，因此同一文件可以被多次上传，并产生不同 Material ID；受控 corpus 导入器必须自行维护 `document_id → material_id` 映射，避免无意重复导入。

处理阶段先解析、清洗和切块，再以当前结果替换该 Material 的全部旧 chunks。chunk 序号从 0 开始，在一份资料内唯一；chunk 主键是数据库自增整数。成功重新处理可能产生新的 chunk 主键，即使内容和 chunk 序号相同，所以 gold case 不应持久绑定数据库 chunk ID。失败的重新处理会回滚未提交替换，并保留此前可审计的 chunk 内容，同时把 ingestion 状态标为 failed。

每次资料处理成功后，API 触发整个资料索引重建，而不是只追加这一份资料的向量。重建仅选择 ingestion completed 且 deletion active 的 chunks，批量生成向量，创建新的随机 index version，并原子保存 FAISS 文件和 Manifest。没有可索引 chunk 时会清除两份索引文件，并把索引状态记为已完成但不可用。

手工 rebuild 使用同一流程；并发 rebuild 会返回冲突。索引状态通过当前可索引 chunks 的内容校验和判断 stale。模型名、revision、归一化设置或维度变化也要求重建。

资料删除是可重试的维护流程。系统先把 Material 标为 deletion pending，使其退出可索引集合，然后重建 FAISS；重建失败则保留资料并标记可重试失败。索引更新成功后才删除原始文件和 Material 数据。MaterialChunk 随 Material 级联删除，而历史 RAG Citation 的外键设为 NULL、快照字段保留。新检索因此不会命中已删除资料，旧回答仍保留当时的引用证据。
