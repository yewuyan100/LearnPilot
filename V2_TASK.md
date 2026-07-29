# PersonalLearning V2 任务

## 版本目标

将 V1 的“本地文件已保存”扩展为可持久化、可重建、可语义检索的本地学习资料知识库：

```text
资料上传
→ PDF / Markdown / TXT 正文解析
→ 确定性清洗与切片
→ MaterialChunk 持久化
→ 本地 BAAI/bge-m3 Embedding
→ FAISS IndexFlatIP 与 Manifest 原子保存
→ 语义检索与来源定位
```

## 实施阶段

- [x] 阅读 V1 完成报告、V2 交接和实际代码
- [x] 执行 Git、迁移、后端和前端基线检查
- [x] 新增 V2 增量迁移和 MaterialChunk
- [x] 扩展 Material 处理与索引状态
- [x] 实现 Repository、Parser、Cleaner、Chunker 和 Pipeline
- [x] 实现 BGE-M3 懒加载 Embedding
- [x] 实现 FAISS、Manifest、原子全量重建和索引锁
- [x] 实现处理、Chunk、索引状态、重建和语义检索 API
- [x] 完成资料页面处理、Chunk 分页、检索和索引管理
- [x] 补齐后端与前端测试
- [x] 完成 Alembic、pytest、compileall、Vitest、Lint、Build
- [x] 回归 V1 验收
- [x] 使用真实本地 BGE-M3 完成 V2 验收和重启恢复
- [x] 更新 README、API、数据模型和 V2 完成报告
- [x] 检查 Git 差异，提交并创建 `v2.0.0`

## 明确不实现

- LLM 生成回答或总结；
- RAG 最终答案；
- LangChain、LangGraph、Agent、Prompt、SSE；
- OCR、图片、音频或视频解析；
- 自动课程、自动知识点、自动出题、自动批改；
- 多用户、登录、Redis、Celery、消息队列、微服务和云部署。

## 完成条件

只有迁移、默认测试、前端检查、V1 验收、真实 BGE-M3 V2 验收、索引重启恢复和 Git 收口全部通过，V2 才能标记完成。
