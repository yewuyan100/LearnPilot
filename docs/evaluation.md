# V3 RAG 评测

## 资产

- `evals/fixtures/`：3 份小型、可人工核验的 MCP 学习资料，其中一份包含恶意资料指令；
- `evals/rag_eval_dataset.json`：5 个可回答问题、2 个应拒答问题和 1 个 Prompt Injection 问题；
- `scripts/evaluate_v3.py`：只通过 HTTP API 评测，不读取 SQLite、FAISS 或模型内部状态；
- `scripts/acceptance_v3.py`：在临时目录启动两次真实后端，验证真实 LLM、SSE、重启和删除快照。

## 指标

- Retrieval Hit@K：可回答问题的最终引用是否命中至少一个预期文件；
- Source Precision：最终引用中属于人工预期来源的比例；
- Citation Validity Rate：正文标签与 Citation 标签是否完全一致；
- Citation Coverage Rate：有回答时是否至少有引用、拒答时是否没有引用；
- Refusal Accuracy：应拒答问题被正确拒答的比例；
- Answerable Accuracy：可回答问题得到回答的比例；
- Invalid Output Rate：非 200 或无法形成有效响应的比例；
- Latency：检索、LLM、总耗时平均值，以及总耗时 p50 / p95。

Citation Coverage 是结构覆盖指标，不等价于逐句事实蕴含判断；小型数据集用于 V3 回归门槛，不代表通用基准。

## 执行

推荐使用隔离模式。它会在临时目录启动 API、导入 `evals/fixtures`，结束后清理，不污染开发数据库：

```powershell
.\.venv\Scripts\python.exe .\scripts\evaluate_v3.py --isolated
```

可选输出文件应写到已忽略的 `evals/results/`：

```powershell
.\.venv\Scripts\python.exe .\scripts\evaluate_v3.py --isolated `
  --output .\evals\results\latest.json
```

真实验收：

```powershell
$env:HF_HOME = "D:\AIModels\HuggingFace"
$env:HF_HUB_OFFLINE = "1"
.\.venv\Scripts\python.exe .\scripts\acceptance_v3.py
```

缺失 Key、余额不足、网络故障或限流都必须报告为失败，不能用 FakeLLM 结果标记真实验收通过。
