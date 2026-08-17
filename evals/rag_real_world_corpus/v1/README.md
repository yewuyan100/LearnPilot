# LearnPilot RAG Real-world Corpus V1

这是与 `evals/rag_demo_corpus/v1/` 相互独立的真实世界语料版本。它冻结许可明确、提交固定的官方上游技术文档，用于后续真实规模 RAG 评测；它不是个人知识库，也不包含 Gold 问题或答案评测。

## 固定契约

- canonical corpus：`corpus/`
- provenance：`corpus_manifest.json`、`acquisition_lock.json`、`source_decisions.json`、`provenance/licenses/`
- deterministic validation：`validate_corpus.py`
- isolated public-API ingestion：`run_ingestion.py`
- immutable run artifacts：`results/ingestion_v1/<run-id>/`

导入器只调用：

- `POST /api/materials/upload`
- `POST /api/materials/{material_id}/process`
- `GET /api/materials/{material_id}/chunks`
- `GET /api/materials/index/status`

运行使用一次性 SQLite、uploads、FAISS 与 checkpoint 路径，提取去敏审计信息后删除运行时目录。它不会调用 RAG ask、DeepSeek 或任何其他答案模型。

## 复现

使用含 ReportLab 的 Python 可按 `acquisition_lock.json` 重新取得精确提交并重建语料。默认临时检出目录是 `<repo-root>/.tmp/rag-real-world-upstreams-20260813/`：

```powershell
& .venv/Scripts/python.exe evals/rag_real_world_corpus/v1/acquire_corpus.py --fetch-missing
```

`--fetch-missing` 只访问 manifest 中的官方 GitHub 仓库，并以 detached HEAD 检出精确提交。若已准备好上游检出，可省略该参数或通过 `--upstream-root` 指定隔离目录。

离线校验与切块投影：

```powershell
& .venv/Scripts/python.exe evals/rag_real_world_corpus/v1/validate_corpus.py
```

隔离导入：

```powershell
& .venv/Scripts/python.exe evals/rag_real_world_corpus/v1/run_ingestion.py
```

不要通过修改生产切块或 RAG 参数来适配此语料。新的 Gold 集应作为独立版本化契约建立。
