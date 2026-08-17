# LearnPilot Grounded RAG

RAG 的 canonical 设计、评测决策链和 CUDA 证据已合并到 [LearnPilot Architecture](architecture.md)，本文件只保留当前运行契约，避免继续传播旧 Top6 文档。

```text
Question / bounded history
→ safe query rewrite (failure keeps original query)
→ BGE-M3 + FAISS Dense Candidate Top18
→ eligibility
→ bge-reranker-v2-m3 PyTorch CUDA FP32
→ overlap / diversity / character-budget governance
→ Final Top7 context (S1…Sn)
→ deterministic answerability gate
→ DeepSeek structured evidence blocks
→ source-ID validation, one bounded repair, deterministic citation rendering
→ message and immutable citation snapshots
```

Candidate recall depth (`RAG_CANDIDATE_TOP_K=18`) 与 final context depth (`RAG_FINAL_CONTEXT_TOP_K=7`) 是不同参数。Reranker 初始化或推理不可用时，provider 进入稳定 degraded state，请求走 `dense_fallback` 并保留同一 governance；索引或证据不可用时则在生成调用前明确拒答。

Citation validity 只证明引用 ID 来自本次 selected context；citation semantic support 另行判断来源是否真正支持相应 claim。两者不能互换。

详细证据和 trade-offs 见 [Architecture](architecture.md)；启动配置见根目录 [README](../README.md)。
