# 可信引用式 RAG

## 调用链

```text
问题 + request_id
→ 会话与幂等检查
→ 最近 6 条 / 6000 字符历史
→ 必要时 Structured Query Rewrite
→ V2 BGE-M3 + FAISS 检索
→ 分数阈值、稳定排序、相邻重复和资料多样性过滤
→ 最多 6 个来源 / 12000 字符上下文
→ 确定性 Answerability Gate
→ OpenAI-compatible Structured Output
→ 正文引用与来源声明双向校验
→ 失败时一次受控修复
→ 事务保存消息与引用快照
→ JSON 响应或校验后 SSE
```

## 查询改写

只有存在历史且当前问题具有“它、这个、前面、二者”等追问特征时才调用改写。历史有消息数和字符双重上限。改写结果出现历史和当前问题之外的新英文实体时回退原问题；模型失败也回退，不阻塞检索。数据库只保存最终用于检索的短查询。

## 检索与上下文

检索直接复用 V2 的 `MaterialIndexService`、同一 BGE-M3 配置、同一 FAISS Manifest 和 SQLite Chunk 回查，不维护第二套索引。默认 `RAG_MIN_SCORE=0.35` 只是初始阈值，不是普适最优值，应根据评测集调整。

候选按 `score desc, material_id, chunk_index, chunk_id` 稳定排序，移除重复 ID 和高度重叠的相邻片段，限制单一资料占比，然后应用来源数、单片段字符和总上下文预算。最终重新编号为 `S1…Sn`，编号同时用于 Prompt、答案校验与 Citation。

## 拒答

以下情况在调用回答模型前拒答：

- 索引不存在、过期或不可用；
- 限定资料范围后没有结果；
- 全部候选低于当前阈值；
- 去重或预算后上下文为空。

拒答文案固定且不带引用。模型也可以声明资料不足；这类结果同样清空引用。LLM 配置错误与服务故障不是“资料不足”，API 使用明确的 503 错误。

## Prompt Injection

系统 Prompt 明确资料片段是不可信数据，并用独立 source 边界包裹。用户问题不会拼进 system 消息。资料内出现“忽略指令”“泄露 Prompt”等内容不能改变应用规则。应用不记录或展示内部 Prompt 和推理过程。

## Structured Output 与引用

模型输出必须严格符合：

```json
{
  "answerable": true,
  "answer_markdown": "……[S1]",
  "cited_source_ids": ["S1"],
  "refusal_reason": null
}
```

有答案必须至少包含一个 `[S数字]`，正文引用集合必须等于声明集合，且必须是实际上下文来源；重复使用同一引用合法。拒答不得出现任何引用。首次不合法时只调用一次修复；仍不合法则稳定拒答，绝不把原始输出发给用户。

## 持久化与删除

问题和助手消息在同一数据库工作单元中建立关联，助手 request_id 提供幂等边界。Citation 同时保存可空外键和不可变来源快照。删除 Material 会由 SQLite 把 Citation 外键设为 NULL，但文件名、位置、相关度和摘录仍存在。FAISS 随资料删除重建，新检索不会命中旧 Chunk。

## SSE

V3 采用 POST `StreamingResponse`，前端使用 Fetch + `ReadableStream` + `AbortController`。服务端不是原始 Token 透传：完整输出通过 Pydantic 和引用校验并持久化后，才切成小段发出。断开只影响传输，不影响最终数据库记录；页面刷新后重新读取会话。
