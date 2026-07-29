# MCP 学习材料：三类核心原语

MCP 的核心学习原语包括 Tools、Resources 和 Prompts。

## Tools

Tools 是由 MCP Server 暴露、由模型主动选择和调用的可执行操作。工具调用通常可能产生副作用，因此宿主应用应保留权限确认、参数校验和结果审查。

## Resources

Resources 是由应用控制并提供给模型的上下文数据。资源通过 URI 标识，适合表达文件内容、数据库记录或其他只读上下文。读取资源本身不等于执行工具。

## Prompts

Prompts 是由用户显式选择的可复用交互模板。它们可以帮助用户以一致结构发起任务，但不会替代 Tools 或 Resources。

## 控制方向

Tools 是模型控制的调用入口；Resources 是应用控制的上下文；Prompts 是用户控制的模板。三者的核心差异是控制方和用途。
