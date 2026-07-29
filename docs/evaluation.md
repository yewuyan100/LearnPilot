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

## V4 活动与批改评测

资产：

- `evals/fixtures/v4/`：人工编写、可核验的 MCP 资料，其中包含一份 Prompt Injection 资料；
- `evals/activity_generation_dataset.json`：题型、数量、难度和来源范围用例；
- `evals/grading_dataset.json`：客观题确定性答案及简答题允许分数区间和预期 Rubric 项；
- `scripts/evaluate_v4.py`：隔离启动真实后端，通过 HTTP API 计算指标；
- `scripts/acceptance_v4.py`：验证真实生成、真实简答批改、错题复习、重启和来源删除快照。

生成指标包括 Schema Validity、Question Source Validity、Answer Key Validity、Rubric Validity、Duplicate Rate、Requested Count Completion、Prompt Injection Resistance、Generation Failure 和平均延迟。

批改指标包括 Objective Grading Accuracy，以及简答题 Score MAE（相对人工允许区间的越界距离）、Within-Tolerance、Rubric Match、Invalid Grade、Failure 和平均延迟。错题指标包括创建准确率、去重率和复习解决准确率。

```powershell
.\.venv\Scripts\python.exe .\scripts\evaluate_v4.py --isolated
```

这是小型回归数据集，只验证当前专用资料和契约的稳定性，不代表通用教学质量或通用评分准确率。真实 Provider 不可用时必须如实记录失败，不能用 FakeLLM 替代。
