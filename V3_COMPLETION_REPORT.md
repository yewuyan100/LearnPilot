# PersonalLearning V3 完成报告

> 发布状态：**V1/V2/V3 验收、真实 LLM、真实评测和全部发布检查均已通过，可以提交并创建 `v3.0.0` 标签。**

## 1. 开发前 Git 基线

- 开发前工作区：clean；
- HEAD：`2ccbcabeb6f157e32a7784e113ea34253d945d57`；
- 提交：`feat: add local material knowledge indexing and semantic search`；
- 标签：`v2.0.0`；
- Alembic：`20260730_0002 (head)`；
- 后端：46 passed；
- 前端：13 passed；
- V1 隔离 HTTP 验收、V2 真实 BGE-M3 验收：passed。

## 2. V1、V2 回归结果

- V1：使用临时 SQLite、上传目录和 V3 最新迁移启动本地后端，六个场景全部 passed；
- V2：真实 `BAAI/bge-m3`、维度 1024，3 份资料处理、检索、重启、幂等重处理和删除全部 passed；
- 开发数据库只读核对未发现 V1 验收标记记录。

## 3. 实际新增文件

- 数据库与后端：`20260730_0003_rag_conversations.py`，3 个 RAG Model，`schemas/rag.py`，`repositories/rag.py`，`api/routes/rag.py`；
- LLM：`services/llm/{base,errors,schemas,openai_compatible}.py`；
- RAG：`services/rag/{types,prompts,query_rewriter,retrieval,validation,service}.py`；
- 测试：`backend/tests/test_rag.py`、`test_rag_units.py`；
- 前端：`pages/RagPage.tsx`、`test/RagPage.test.tsx`；
- 评测与验收：3 份 fixture、`rag_eval_dataset.json`、`evaluate_v3.py`、`acceptance_v3.py`；
- 文档：`V3_TASK.md`、`V3_PROGRESS.md`、本报告、`docs/rag.md`、`docs/evaluation.md`。

## 4. 实际修改文件

`.env.example`、`.gitignore`、`README.md`、后端配置/依赖注入/Router/Main/Model 导出与枚举、现有架构/API/数据模型文档，以及前端版本、路由、导航、API Client、类型和样式。

V1 的 `0001`、V2 的 `0002`、V1/V2 业务 API 和 V2 检索实现均未改写。

## 5. Alembic 迁移

- 新版本：`20260730_0003`；
- `upgrade head`：通过；
- `current` / `heads`：均为 `20260730_0003 (head)`；
- `alembic check`：`No new upgrade operations detected`。

## 6. Conversation、Message、Citation 数据模型

- `rag_conversations`：标题、active/archived、默认 top_k、最近消息时间；
- `rag_messages`：用户/助手角色、reply_to、状态、会话内唯一 request_id、原问题、检索查询、可回答性、拒答原因、Prompt/模型/Token/延迟/错误；
- `rag_citations`：助手消息、S 标签、可空 Material/Chunk 外键、rank/score、文件/位置/摘录快照；
- 删除会话级联消息和引用；删除 Material/Chunk 后 Citation 外键置空但快照保留。

## 7. Query Rewrite 流程

只在存在最近历史且问题具有上下文追问特征时运行。最多读取 6 条、6000 字符；Structured Output 只允许 `standalone_query`。改写新增历史中不存在的英文实体或调用失败时回退原问题。数据库只保存最终短查询。

## 8. Retrieval 流程

直接复用 V2 `MaterialIndexService`、同一 BGE-M3、FAISS、Manifest 和 SQLite 回查。候选稳定排序，应用初始阈值 0.35、相邻重叠去重、单资料占比、最多 6 来源、单片段 2200 字符和总计 12000 字符预算。0.35 明确只是评测起点。

## 9. Context Builder

最终候选重新编号 `S1…Sn`，包含文件名、页码/章节和受限正文。资料在独立 user 消息中标记为不可信数据；用户问题不拼入 system 消息。

## 10. Answerability Gate

索引缺失/过期/不可用、无结果、全部低于阈值、限定资料为空或预算后上下文为空时，由确定性代码直接拒答，不调用回答 LLM。显式系统提示窃取请求也直接拒答。

## 11. Prompt 版本

- 回答：`rag-answer-v1`；
- 查询改写：`rag-rewrite-v1`；
- 版本写入配置和助手消息，不记录完整 Prompt。

## 12. LLM Provider

实现 OpenAI-compatible `/chat/completions` Provider，配置 API Key、Base URL、Model、60 秒超时、2 次重试、0.1 温度和 1200 输出 Token。API Key 使用 `SecretStr`，状态 API 仅返回是否配置。

## 13. Structured Output

回答严格使用 `RagModelAnswer(answerable, answer_markdown, cited_source_ids, refusal_reason)`，查询改写使用 `QueryRewriteResult`，均 `extra=forbid`。JSON/Pydantic 无效时返回受控错误或进入一次修复，不透传原始输出。

## 14. Citation Validator

有答案时正文必须含 `[S数字]`；正文集合必须等于声明集合并属于实际上下文。重复引用同一来源允许。拒答不得包含正文标签或 Citation。首次失败只修复一次，再失败稳定拒答。

## 15. 拒答策略

稳定文案为“当前资料不足以可靠回答……”。拒答保存 `answerable=false`、具体 `refusal_reason` 和空 Citation。LLM 未配置/故障与资料不足区分，相关资料存在时返回清晰 503。

## 16. 幂等策略

助手消息使用 `(conversation_id, request_id)` 唯一约束。相同 ID 与相同问题直接返回原消息，不新增用户消息、不再次调用 LLM；相同 ID 用于不同问题返回 409。

## 17. SSE 策略

使用 POST `StreamingResponse`，顺序为 `accepted → retrieval → message_start → delta* → citations → done`，失败为 `error`。服务端先完整生成、Structured Parse、引用校验和持久化，再分段发送最终内容。前端使用 Fetch Stream + AbortController，断线后重新 GET 会话恢复。

## 18. 前端功能

新增左侧“资料问答”和 `/rag` 三栏工作台：会话列表/新建/归档、真实状态、消息历史、资料范围、阶段状态、停止、拒答标识、S 标签与引用详情、来源删除后的快照状态、加载/空/错误状态。浏览器本地冒烟检查通过，并修正标题响应式和 V3 页脚。

## 19. 安全与 Prompt Injection

资料片段明确为不可信数据；资料内指令不能覆盖 system 规则；用户问题不进入 system；显式窃取 Prompt 的请求确定性拒答；日志不包含 Key、完整 Prompt、完整历史、完整资料或内部推理。

## 20. 默认测试结果

- 后端：`58 passed`；
- 覆盖 V1/V2 回归、模型/API、Structured Output、重试、改写、检索过滤、拒答、引用修复、幂等、SSE、删除快照和 Prompt Injection；
- `compileall`：通过。

## 21. 前端测试、Lint、Build

- Vitest：3 files、15 passed；
- ESLint：通过；
- TypeScript + Vite production build：通过（2337 modules transformed）。

## 22. 真实 LLM 验收

`acceptance_v3.py` 使用真实 BGE-M3 和用户配置的真实 OpenAI-compatible Provider，在临时目录启动两次后端，结果 passed：

- 真实 LLM 回答与引用：通过；
- 上下文追问、限定资料、拒答和 Prompt Injection：通过；
- request_id 幂等和 POST SSE：通过；
- 12 条消息重启恢复：通过；
- 删除资料后的 Citation 快照：通过；
- 已删除资料不再被新检索命中：通过。

FakeLLM 测试未被描述为真实 LLM 验收。

## 23. 评测结果

隔离真实评测使用 3 份人工可核验 MCP 资料和 8 个问题：

- Retrieval Hit@K：1.0；
- Source Precision：1.0；
- Citation Validity Rate：1.0；
- Citation Coverage Rate：1.0；
- Refusal Accuracy：1.0；
- Answerable Accuracy：1.0；
- Invalid Output Rate：0.0；
- 平均检索耗时：131.375 ms；
- 平均 LLM 耗时：1416 ms；
- 平均总耗时：1565.01125 ms；
- 总耗时 p50：2273.125 ms；
- 总耗时 p95：2564.56 ms。

## 24. 已知限制

- 真实质量与默认分数阈值仍需目标 Provider 的评测结果校准；
- Citation Coverage 当前是结构覆盖，不是逐句自然语言蕴含判断；
- SSE 是“校验后分段输出”，首段延迟包含完整模型生成时间；
- 仅支持 V2 已解析的文本资料；无 OCR、图片、音频、视频或网络资料；
- 单用户本地进程内并发边界依赖 SQLite 唯一约束，不含分布式锁。

V3 未实现 LangGraph、Agent、外部工具、自动课程、自动出题、自动批改、掌握度和多用户。

## 25. Git diff

敏感信息扫描未发现真实 Key；`.env`、SQLite、上传文件、FAISS、Manifest、模型、`node_modules`、构建产物和评测临时输出均未纳入 Git。`git diff --check` 仅有 Windows 行尾提示，无空白错误。

## 26. Commit

已使用以下单一功能提交收口；实际 hash 通过 `git log -1` 核对：

```text
feat: add grounded rag conversations with citations
```

## 27. Tag

已创建 `v3.0.0`，只指向上述全部发布门槛通过的 V3 提交。
