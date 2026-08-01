import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { Bot, Check, MessageSquarePlus, Send, ShieldCheck, X } from "lucide-react";
import { agentApi } from "../api/resources";
import type { AgentCitation, AgentConfirmation, AgentConversation, AgentConversationDetail, AgentRun } from "../types";

export function AgentPage() {
  const [conversations, setConversations] = useState<AgentConversation[]>([]);
  const [selected, setSelected] = useState<AgentConversationDetail | null>(null);
  const [input, setInput] = useState("");
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [runId, setRunId] = useState<number | null>(null);
  const [confirmation, setConfirmation] = useState<AgentConfirmation | null>(null);
  const [events, setEvents] = useState<Array<{ label: string; detail: string }>>([]);
  const controller = useRef<AbortController | null>(null);

  const loadList = async () => {
    const rows = await agentApi.list();
    setConversations(rows.filter((item) => item.status === "active"));
    if (!selected && rows[0]) setSelected(await agentApi.get(rows[0].id));
  };
  const refresh = async (id: number) => setSelected(await agentApi.get(id));

  useEffect(() => {
    agentApi.list().then(async (rows) => {
      const active = rows.filter((item) => item.status === "active");
      setConversations(active);
      if (active[0]) setSelected(await agentApi.get(active[0].id));
    }).catch((e: Error) => setError(e.message));
  }, []);
  useEffect(() => () => controller.current?.abort(), []);

  const createConversation = async () => {
    const row = await agentApi.create();
    await loadList();
    setSelected(await agentApi.get(row.id));
    setConfirmation(null); setEvents([]);
  };

  const send = async (event: FormEvent) => {
    event.preventDefault();
    if (!selected || !input.trim() || busy) return;
    const text = input.trim(); setInput(""); setDraft(""); setError(""); setBusy(true); setConfirmation(null); setEvents([]);
    controller.current = new AbortController();
    try {
      await agentApi.stream(selected.id, text, crypto.randomUUID(), controller.current.signal, (name, raw) => {
        const data = raw as Record<string, unknown>;
        if (name === "accepted") setRunId(Number(data.run_id));
        if (name === "status") setEvents((items) => [...items, { label: "状态", detail: String(data.status ?? "处理中") }]);
        if (name === "tool_start") setEvents((items) => [...items, { label: "调用工具", detail: String(data.tool) }]);
        if (name === "tool_result") setEvents((items) => [...items, { label: "工具结果", detail: String(data.user_summary ?? "已完成") }]);
        if (name === "confirmation_required") setConfirmation(data as unknown as AgentConfirmation);
        if (name === "delta") setDraft((value) => value + String(data.text ?? ""));
        if (name === "error") setError(String(data.message ?? "学习助手运行失败"));
      });
      await refresh(selected.id); await loadList();
    } catch (e) { setError(e instanceof Error ? e.message : "发送失败"); }
    finally { setBusy(false); }
  };

  const decide = async (decision: "approve" | "reject") => {
    if (!runId) return;
    setBusy(true); setError("");
    try {
      const run: AgentRun = await agentApi.confirm(runId, decision);
      setDraft(run.final_answer ?? ""); setConfirmation(null);
      if (selected) await refresh(selected.id);
      setEvents(run.tool_calls.map((call) => ({ label: call.tool_kind === "write" ? "写入工具" : "查询工具", detail: `${call.tool_name} · ${call.status}` })));
    } catch (e) { setError(e instanceof Error ? e.message : "确认失败"); }
    finally { setBusy(false); }
  };

  const citations: AgentCitation[] = selected?.messages.at(-1)?.citations ?? [];
  return (
    <section className="page-shell agent-page">
      <header className="page-header page-header--split">
        <div><p className="eyebrow">V5 · 受控工具编排</p><h1>学习助手</h1><p>查询会直接执行；创建或更新内容前会展示不可变参数并等待你的确认。</p></div>
        <button className="button button--primary" onClick={createConversation}><MessageSquarePlus size={17} /> 新会话</button>
      </header>
      {error && <div className="alert alert--error">{error}</div>}
      <div className="agent-workspace">
        <aside className="agent-conversations" aria-label="助手会话">
          <h2>会话</h2>
          {conversations.map((item) => <button key={item.id} className={selected?.id === item.id ? "is-active" : ""} onClick={() => refresh(item.id)}>
            <strong>{item.title}</strong><small>{item.last_message_at ? new Date(item.last_message_at).toLocaleString() : "暂无消息"}</small>
          </button>)}
        </aside>
        <main className="agent-chat">
          <div className="agent-messages" aria-live="polite">
            {!selected?.messages.length && <div className="agent-empty"><Bot size={36} /><h2>从一个学习请求开始</h2><p>例如：查看今日任务、根据资料回答问题，或创建一个测验草稿。</p></div>}
            {selected?.messages.map((message) => <article key={message.id} className={`agent-message agent-message--${message.role}`}>
              <span>{message.role === "user" ? "你" : "学习助手"}</span><p>{message.content}</p>
              {!!message.citations.length && <div className="agent-citation-chips">{message.citations.map((source) => <span key={source.source_label} className="citation-chip">{source.source_label}</span>)}</div>}
            </article>)}
            {draft && <article className="agent-message agent-message--assistant"><span>学习助手</span><p>{draft}</p></article>}
            {confirmation && <section className="agent-confirmation">
              <header><ShieldCheck size={20} /><div><strong>需要你的确认</strong><p>{confirmation.summary}</p></div></header>
              <pre>{JSON.stringify(confirmation.arguments, null, 2)}</pre>
              <div><button className="button button--primary" disabled={busy} onClick={() => decide("approve")}><Check size={17} /> 确认执行</button>
                <button className="button button--ghost" disabled={busy} onClick={() => decide("reject")}><X size={17} /> 取消</button></div>
            </section>}
          </div>
          <form className="agent-composer" onSubmit={send}><textarea aria-label="给学习助手发送消息" value={input} onChange={(e) => setInput(e.target.value)} placeholder="告诉学习助手你想查什么或做什么……" rows={3} />
            <button className="button button--primary" disabled={!selected || busy || !input.trim()}><Send size={17} /> {busy ? "处理中" : "发送"}</button></form>
        </main>
        <aside className="agent-detail" aria-label="运行详情"><h2>本次运行</h2>
          <p className="agent-safety-note"><ShieldCheck size={17} /> 最多 4 步、只允许 1 次写入</p>
          {events.length ? <ol>{events.map((item, index) => <li key={`${item.label}-${index}`}><strong>{item.label}</strong><span>{item.detail}</span></li>)}</ol> : <p className="muted">工具执行摘要会显示在这里，不包含内部推理或提示词。</p>}
          {!!citations.length && <div className="agent-sources"><h3>资料引用</h3>{citations.map((source) => <article key={source.source_label}><span className="citation-chip">{source.source_label}</span><strong>{source.original_filename}</strong><p>{source.content_excerpt}</p></article>)}</div>}
        </aside>
      </div>
    </section>
  );
}
