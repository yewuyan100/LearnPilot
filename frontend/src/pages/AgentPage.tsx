import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type SyntheticEvent } from "react";
import { ArrowRight, Check, ChevronDown, MessageSquarePlus, Send, ShieldCheck, X } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { agentApi, coursesApi, goalsApi, lessonsApi, materialsApi } from "../api/resources";
import type { AgentConfirmation, AgentConversation, AgentConversationDetail, AgentRun } from "../types";
import { resolveAgentRouteContext } from "./agentContext";

const starterPrompts = ["梳理当前事项的下一步", "根据资料解释当前阶段", "分析一个问题并给出推进思路", "检查哪些内容需要加强"];
const contextMarker = "\n\n[系统已带入的协作上下文]";

function visibleMessage(content: string) {
  const visible = content.split(contextMarker)[0];
  return /操作未完成（[a-z][a-z0-9_]+）|tool_arguments_invalid/i.test(visible)
    ? "AI 协作暂时无法完成这项请求，请重试。"
    : visible;
}

function safeErrorMessage(value: unknown) {
  const message = typeof value === "string" ? value : "AI 协作暂时无法完成这项请求，请重试。";
  return /tool_arguments_invalid|操作未完成（[a-z][a-z0-9_]+）/i.test(message)
    ? "AI 协作暂时无法完成这项请求，请重试。"
    : message;
}

function confirmationDetails(confirmation: AgentConfirmation) {
  const labels: Record<string, string> = { title: "名称", scheduled_date: "安排日期", estimated_minutes: "预计时长", status: "状态" };
  return Object.entries(confirmation.arguments).filter(([key, value]) => labels[key] && (typeof value === "string" || typeof value === "number")).map(([key, value]) => <div key={key}><span>{labels[key]}</span><strong>{String(value)}{key === "estimated_minutes" ? " 分钟" : ""}</strong></div>);
}

export function AgentPage() {
  const [params] = useSearchParams();
  const [conversations, setConversations] = useState<AgentConversation[]>([]);
  const [selected, setSelected] = useState<AgentConversationDetail | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [input, setInput] = useState("");
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [runId, setRunId] = useState<number | null>(null);
  const [confirmation, setConfirmation] = useState<AgentConfirmation | null>(null);
  const [events, setEvents] = useState<string[]>([]);
  const [retryText, setRetryText] = useState("");
  const controller = useRef<AbortController | null>(null);
  const composer = useRef<HTMLTextAreaElement | null>(null);
  const routeContext = useMemo(() => resolveAgentRouteContext(params), [params]);
  const { context: conversationContext, materialId, lessonId, error: contextParamError } = routeContext;
  const contextKey = `${conversationContext.context_type}:${conversationContext.context_id ?? "general"}`;
  const lesson = useQuery({ queryKey: ["lesson", lessonId], queryFn: () => lessonsApi.get(lessonId as number), enabled: conversationContext.context_type === "lesson" && !contextParamError });
  const material = useQuery({ queryKey: ["material", materialId], queryFn: () => materialsApi.get(materialId as number), enabled: conversationContext.context_type === "material" && !contextParamError });
  const courses = useQuery({ queryKey: ["courses", "agent-context"], queryFn: coursesApi.list, enabled: conversationContext.context_type === "goal" && !contextParamError });
  const resolvedGoalId = conversationContext.context_type === "goal"
    ? conversationContext.context_id
    : conversationContext.context_type === "lesson"
      ? lesson.data?.learning_goal_id ?? null
      : null;
  const requestedGoal = useQuery({ queryKey: ["goal", resolvedGoalId], queryFn: () => goalsApi.get(resolvedGoalId!), enabled: resolvedGoalId !== null && !contextParamError });
  const hasGoalContext = conversationContext.context_type === "goal" || conversationContext.context_type === "lesson";
  const contextGoalId = hasGoalContext ? requestedGoal.data?.id ?? null : null;
  const contextGoalTitle = hasGoalContext ? requestedGoal.data?.title ?? null : null;
  const contextCourseId = conversationContext.context_type === "lesson"
    ? lesson.data?.course_id ?? null
    : conversationContext.context_type === "goal"
      ? courses.data?.find((course) => course.learning_goal_id === contextGoalId)?.id ?? null
      : null;
  const points = useQuery({ queryKey: ["course-points", contextCourseId], queryFn: () => coursesApi.points(contextCourseId!), enabled: contextCourseId !== null });
  const lessonPoint = conversationContext.context_type === "lesson" ? lesson.data?.active_version?.knowledge_points.find((point) => point.role === "primary") : undefined;
  const contextPointId = lessonPoint?.knowledge_point_id;
  const contextPoint = points.data?.find((point) => point.id === contextPointId) ?? points.data?.find((point) => point.status !== "completed");
  const primaryContextLoading = conversationContext.context_type === "goal" ? requestedGoal.isLoading
    : conversationContext.context_type === "lesson" ? lesson.isLoading
      : conversationContext.context_type === "material" ? material.isLoading : false;
  const primaryContextError = conversationContext.context_type === "goal" ? requestedGoal.isError
    : conversationContext.context_type === "lesson" ? lesson.isError
      : conversationContext.context_type === "material" ? material.isError : false;
  const contextLoading = !contextParamError && (primaryContextLoading || (resolvedGoalId !== null && requestedGoal.isLoading));
  const contextError = contextParamError || (primaryContextError
    ? "当前协作上下文无法加载，请从原页面重试。"
    : resolvedGoalId !== null && requestedGoal.isError
      ? "当前协作上下文关联的事项无法加载，请从原页面重试。" : "");
  const contextReady = !contextLoading && !contextError;
  const refetchContext = () => {
    if (conversationContext.context_type === "goal") void requestedGoal.refetch();
    if (conversationContext.context_type === "lesson") void lesson.refetch();
    if (conversationContext.context_type === "material") void material.refetch();
  };
  const loadList = async () => {
    const rows = (await agentApi.list(conversationContext)).filter((item) => item.status === "active");
    setConversations(rows);
    if (!selected && rows[0]) setSelected(await agentApi.get(rows[0].id));
  };
  const refresh = async (id: number) => setSelected(await agentApi.get(id));
  useEffect(() => {
    let active = true;
    setSelected(null); setConversations([]); setConfirmation(null); setEvents([]); setError("");
    if (!contextReady) return () => { active = false; };
    void (async () => {
      const rows = (await agentApi.list(conversationContext)).filter((item) => item.status === "active");
      if (!active) return;
      setConversations(rows);
      if (rows[0]) {
        const first = await agentApi.get(rows[0].id);
        if (active) setSelected(first);
      }
    })().catch((reason: Error) => active && setError(safeErrorMessage(reason.message)));
    return () => { active = false; };
  }, [contextKey, contextReady, conversationContext]);
  useEffect(() => () => controller.current?.abort(), []);
  const createConversation = async () => {
    if (!contextReady) throw new Error(contextError || "当前协作上下文仍在加载，请稍候。 ");
    const row = await agentApi.create("新的 AI 协作会话", conversationContext);
    await loadList();
    const detail = await agentApi.get(row.id);
    setSelected(detail); setConfirmation(null); setEvents([]); setHistoryOpen(false);
    return detail;
  };
  const send = async (event: SyntheticEvent, shortcut?: string) => {
    event.preventDefault();
    const text = (shortcut ?? input).trim();
    if (!text || busy || !contextReady) return;
    setRetryText(text);
    setInput(""); setDraft(""); setError(""); setBusy(true); setConfirmation(null); setEvents(["正在理解你的学习请求"]);
    controller.current = new AbortController();
    try {
      const conversation = selected ?? await createConversation();
      const contextLines = [
        contextGoalId ? `learning_goal_id=${contextGoalId}` : "",
        contextCourseId ? `course_id=${contextCourseId}` : "",
        contextPointId ? `knowledge_point_id=${contextPointId}` : "",
        conversationContext.context_type === "material" && conversationContext.context_id
          ? `material_ids=[${conversationContext.context_id}]` : "",
      ].filter(Boolean);
      const request = contextLines.length ? `${text}${contextMarker}\n${contextLines.join("\n")}` : text;
      await agentApi.stream(conversation.id, request, crypto.randomUUID(), controller.current.signal, (name, raw) => {
        const data = raw as Record<string, unknown>;
        if (name === "run.started") setEvents((items) => [...items, "正在处理学习请求"]);
        if (name === "step.started") setEvents((items) => [...items, "正在查询相关学习信息"]);
        if (name === "step.completed") setEvents((items) => [...items, String(data.summary ?? "已完成一项学习相关处理")]);
        if (name === "approval.required") {
          setRunId(Number(data.run_id));
          setConfirmation(data as unknown as AgentConfirmation);
        }
        if (name === "answer.completed") setDraft(String(data.text ?? ""));
        if (name === "run.failed") setError(safeErrorMessage(data.safe_message));
      });
      await refresh(conversation.id); setDraft(""); await loadList();
    } catch (reason) { setError(safeErrorMessage(reason instanceof Error ? reason.message : "发送失败，请稍后重试")); }
    finally { setBusy(false); }
  };
  const decide = async (decision: "approve" | "reject") => {
    if (!runId) return;
    setBusy(true); setError("");
    try {
      const run: AgentRun = await agentApi.confirm(runId, decision);
      setDraft(run.final_answer ?? ""); setConfirmation(null);
      if (selected) await refresh(selected.id);
      setEvents(run.tool_calls.map((call) => call.result?.user_summary ?? (call.tool_kind === "write" ? "已完成一次内容更新" : "已查询学习信息")));
    } catch (reason) { setError(safeErrorMessage(reason instanceof Error ? reason.message : "确认失败，请稍后重试")); }
    finally { setBusy(false); }
  };
  const researchHref = conversationContext.context_type === "material" && materialId !== null
    ? `/knowledge?tab=qa&scope=material&material_id=${materialId}`
    : contextGoalId
      ? `/knowledge?tab=qa&scope=learning_goal&learning_goal_id=${contextGoalId}`
      : "/knowledge?tab=qa";
  const collaborationScope = conversationContext.context_type === "material"
    ? {
        eyebrow: "协作范围",
        title: "资料协作",
        description: "把这份资料作为当前协作上下文，继续理解和推进。",
        details: [
          { label: "当前资料", value: material.data?.title || material.data?.original_filename || "正在读取当前资料" },
          { label: "使用方式", value: "作为当前协作上下文" },
        ],
      }
    : hasGoalContext
      ? {
          eyebrow: "协作范围",
          title: "事项协作",
          description: "围绕当前事项判断下一步，不替代资料核对。",
          details: [
            { label: "当前事项", value: contextGoalTitle || "正在读取当前事项" },
            { label: "当前内容", value: lesson.data?.title ?? contextPoint?.title ?? "尚未进入具体内容" },
            { label: "可用资料", value: "使用事项已有资料" },
          ],
        }
      : {
          eyebrow: "当前上下文",
          title: "通用协作",
          description: "先从当前问题开始，需要时再带入事项或资料。",
          details: [
            { label: "事项", value: "尚未选择" },
            { label: "资料", value: "尚未限定" },
          ],
        };
  return <section className="page composition-page agent-page collaboration-workspace">
    <section className="collaboration-context-stage" aria-labelledby="ai-context-title">
      <div className="collaboration-context-stage__copy"><span>{conversationContext.context_type === "general" ? "通用协作" : conversationContext.context_type === "material" ? "资料上下文" : "事项上下文"}</span><h2 id="ai-context-title">{material.data?.title || material.data?.original_filename || contextGoalTitle || lesson.data?.title || "从当前问题开始"}</h2><p>{conversationContext.context_type === "material" ? "这份资料是当前协作上下文。AI 会帮助你理解内容并判断下一步。" : hasGoalContext ? "AI 会基于当前事项、已到达阶段和可用资料，帮助你判断下一步。" : "AI 会从你当前提出的问题开始，需要时再带入事项或资料。"}</p></div>
      <dl><div><dt>事项</dt><dd>{contextGoalId ? <Link aria-label={contextGoalTitle ?? "当前事项"} to={`/items/${contextGoalId}`}>打开当前事项</Link> : "尚未选择事项"}</dd></div><div><dt>当前内容</dt><dd>{lesson.data?.title ?? contextPoint?.title ?? "尚未进入具体内容"}</dd></div><div><dt>资料</dt><dd>{material.data ? <Link aria-label={material.data.title || material.data.original_filename} to={`/materials/${material.data.id}`}>打开当前资料</Link> : conversationContext.context_type === "goal" || conversationContext.context_type === "lesson" ? "使用事项的可用资料" : "尚未限定资料"}</dd></div></dl>
      <div className="collaboration-context-stage__actions"><button className="button button--secondary" onClick={() => setHistoryOpen((value) => !value)} disabled={!contextReady}>历史会话 <ChevronDown size={16}/></button><button className="button button--action" onClick={() => void createConversation()} disabled={!contextReady || busy}><MessageSquarePlus size={17}/>新建协作会话</button></div>
    </section>
    <section className="ai-action-menu" aria-labelledby="ai-action-title">
      <header><h2 id="ai-action-title">你希望 AI 帮你做什么</h2></header>
      <div>
        {lesson.data ? <Link to={`/lessons/${lesson.data.id}${params.get("session_id") ? `?session=${params.get("session_id")}` : ""}`}><strong>理解与讨论</strong><span>回到当前内容，继续带上下文提问</span><ArrowRight size={16}/></Link> : <button onClick={(event) => void send(event, "解释当前事项中我正在推进的阶段，并用一个例子帮助我理解")}><strong>理解与讨论</strong><span>围绕当前阶段解释、举例和检查理解</span><ArrowRight size={16}/></button>}
        <Link to={researchHref}><strong>结合资料思考</strong><span>{material.data ? `带着《${material.data.title || material.data.original_filename}》理解问题，再决定下一步` : "结合当前可用资料理解问题，再决定下一步"}</span><ArrowRight size={16}/></Link>
        <button onClick={(event) => void send(event, "梳理当前事项的下一步，并说明为什么现在应该做它")}><strong>推进事项</strong><span>查看下一步、安排动作或处理反馈</span><ArrowRight size={16}/></button>
        <button onClick={() => composer.current?.focus()}><strong>其他问题</strong><span>直接描述你现在想解决的问题</span><ArrowRight size={16}/></button>
      </div>
    </section>
    {historyOpen && <section className="agent-history" aria-label="历史会话">{conversations.length ? conversations.map((item) => <button key={item.id} className={selected?.id === item.id ? "is-active" : ""} onClick={() => { void refresh(item.id); setHistoryOpen(false); }}><strong>{item.title}</strong><small>{item.last_message_at ? new Date(item.last_message_at).toLocaleString("zh-CN") : "暂无消息"}</small></button>) : <p>暂无历史会话。</p>}</section>}
    {(contextError || error) && <div className="notice notice--warning">{contextError || error}{contextError && !contextParamError ? <button className="button button--secondary" onClick={refetchContext}>重试</button> : !contextError && retryText ? <button className="button button--secondary" onClick={(event) => void send(event, retryText)} disabled={busy}>重试</button> : null}</div>}
    <div className="assistant-layout"><main className="agent-chat"><div className="agent-messages" aria-live="polite">{!selected?.messages.length && <div className="assistant-empty"><h2>从一件要推进的事开始</h2><p>可以请求解释当前阶段、结合资料思考、安排下一步，或复盘反馈。</p><div>{starterPrompts.map((prompt) => <button key={prompt} onClick={(event) => void send(event, prompt)} disabled={busy || !contextReady}>{prompt}</button>)}</div></div>}{selected?.messages.map((message) => <article key={message.id} className={`agent-message agent-message--${message.role}`}><span>{message.role === "user" ? "你" : "AI 助手"}</span><p>{visibleMessage(message.content)}</p>{!!message.citations.length && <div className="agent-citation-chips">{message.citations.map((source) => <span key={source.source_label} className="citation-chip">{source.source_label}</span>)}</div>}</article>)}{draft && <article className="agent-message agent-message--assistant"><span>AI 助手</span><p>{visibleMessage(draft)}</p></article>}{confirmation && <section className="agent-confirmation"><header><ShieldCheck size={20}/><div><strong>需要你的确认</strong><p>{confirmation.summary}</p></div></header><div className="confirmation-details">{confirmationDetails(confirmation)}</div><div className="button-row"><button className="button button--primary" disabled={busy} onClick={() => void decide("approve")}><Check size={17}/>确认执行</button><button className="button button--secondary" disabled={busy} onClick={() => void decide("reject")}><X size={17}/>取消</button></div></section>}</div><form className="agent-composer" onSubmit={(event) => void send(event)}><textarea ref={composer} aria-label="给 AI 协作发送消息" value={input} onChange={(event) => setInput(event.target.value)} placeholder="例如：结合当前上下文，帮我梳理这件事的下一步" rows={3} disabled={!contextReady}/><button className="button button--primary" disabled={busy || !input.trim() || !contextReady}><Send size={17}/>{busy ? "正在处理" : "发送"}</button></form></main>
      <aside className="assistant-context" aria-label="协作范围"><span>{collaborationScope.eyebrow}</span><h2>{collaborationScope.title}</h2><p>{collaborationScope.description}</p><dl className="assistant-context__scope">{collaborationScope.details.map((detail) => <div key={detail.label}><dt>{detail.label}</dt><dd>{detail.value}</dd></div>)}</dl>{events.length > 0 && <details><summary>本次处理摘要</summary><ol>{events.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ol></details>}</aside></div>
  </section>;
}
