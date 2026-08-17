# AI 应用后端的分层接口

LearnPilot 是本地单体应用。React 前端通过 JSON 或经过校验的 SSE 调用 FastAPI。后端按 route、Pydantic schema、service、repository 和 SQLAlchemy model 分层：route 负责 HTTP 状态与请求映射，schema 负责输入输出验证，service 负责业务事务，repository 集中数据查询，model 定义持久化结构。

这种分层不是为了增加目录数量，而是让调用方只依赖稳定接口。例如资料问答 route 只负责创建会话、提交问题和返回 `RagAnswerResponse`；检索、拒答、模型调用、引用落库和幂等冲突都隐藏在 RAG module 内。MaterialIndexService 则作为资料搜索和 RAG 共同使用的索引接口，避免维护第二套检索实现。

统一 API 前缀是 `/api`。错误响应使用 `{"error":{"code","message","details"}}` 结构。资料上传使用 201；资料不存在使用 404；并发索引构建、陈旧索引或 request ID 冲突使用明确冲突语义；Embedding 或模型服务不可用使用 503，而不是把基础设施故障伪装成“没有答案”。

流式 RAG 使用 POST StreamingResponse。服务端先完成结构化生成、验证、持久化，再发送 retrieval completed、generation completed、answer completed、citation artifact 和 run completed 等事件。它不是把未经校验的模型 token 直接透传给浏览器。传输中断不撤销已经完成的数据库事实，页面可以重新读取会话获得最终状态。

评测客户端应依赖公开 HTTP 响应，不直接读取 SQLite 或 FAISS 推断结果。离线 foundation 校验可以检查 corpus 文件和 JSON 契约，但真正的 RAG eval 应通过 API 创建隔离会话、提交唯一 request ID，并从响应中的 retrieval summary、answerability 和 citations 计算指标。
