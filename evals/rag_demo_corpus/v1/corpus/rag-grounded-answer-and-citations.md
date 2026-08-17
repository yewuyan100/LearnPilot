# Grounded Answer 与引用契约

进入回答模型的每个来源都被包装成独立的只读、不可信数据块，包含临时 source ID、原文件名、位置和正文。位置优先使用页码；没有页码时使用章节标题；二者都没有时使用从 1 开始显示的片段序号。资料正文中的指令不能覆盖系统规则。

回答模型必须返回结构化 evidence blocks。可回答结果要求 `answerable=true`，至少一个非空 block，每个 block 都包含自然 Markdown 和一个或多个真实支持它的 source ID。block 正文不能自行写 `[S1]` 之类的标记。拒答结果要求 `answerable=false`、blocks 为空，并给出非空 refusal reason。

后端验证 source ID 是否属于本次实际上下文、每个 block 是否有来源、正文是否为空、是否夹带引用语法以及总长度是否超限。初稿不符合契约时只允许一次受控修复；修复仍失败时系统稳定拒答，不会把未校验草稿暴露给用户。

引用标记由后端确定性渲染。每个 block 的 source IDs 被去重后按声明顺序追加为 `[S1][S2]`，全部 block 再用空行连接。因而最终正文中的引用和持久化 citation 记录来自同一份已验证 source ID 集合，而不是模型分别生成的两个可能不一致的结果。

每条 citation 保存 assistant message ID、source label、rank、score、chunk ID、material ID、原文件名、chunk 序号、页码、章节标题、正文摘录和学习范围快照。删除原资料后，chunk/material 外键会变为 NULL，但原文件名、位置和摘录仍保留，历史回答仍可解释。`source_available=false` 表示原始 chunk 已不可回查，不表示历史摘录被删除。
