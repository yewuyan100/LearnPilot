# 资料解析、清洗与切块契约

资料处理支持三类输入。PDF 使用 pypdf 按页提取文本并记录从 1 开始的页码；加密、损坏、无法提取文字或扫描版 PDF 会明确失败，系统不执行 OCR。Markdown 必须是 UTF-8 或 UTF-8-SIG，按标题拆成章节，移除围栏标记但保留代码块内容，并把常见内联 Markdown 转成可检索文本。TXT 同样要求 UTF-8 或 UTF-8-SIG，并作为单个初始 section。

清洗统一换行符、移除 NULL 和控制字符、把 tab 展开为空格、删除行尾空白并压缩过多空行。PDF 额外修复英文单词在换行处的连字符断裂。清洗只做确定性格式修复，不总结、不翻译，也不改变语义标点。

默认 chunk size 是 800 字符，overlap 是 120，minimum chunk size 是 80。切块优先在空行、换行、句末标点、英文句点、逗号或冒号边界结束；找不到合适边界时使用硬长度。下一片段从前一片段末尾向前保留 overlap，并跳过起点空白。过短尾片段或新增尾部不足 minimum 时会合并回前一片段。

chunk 不跨 section 生成，因此 Markdown 章节标题和 PDF 页码可以准确继承。每个 MaterialChunk 保存数据库 ID、material ID、从 0 开始的 chunk index、正文、字符数、SHA-256 content hash、可空 page number 和可空 section title。`material_id + chunk_index` 唯一，字符数必须为正。

Corpus V1 优先使用 Markdown，因为章节标题能稳定进入 chunk metadata，且文本可在代码审查中直接核验。PDF 用例应留给专门的解析回归；混入扫描 PDF 会把 OCR 缺失错误地变成 RAG 质量问题。
