import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  BookOpenCheck,
  FileSearch,
  MessageSquarePlus,
  NotebookPen,
  Send,
  Square,
} from "lucide-react";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { coursesApi, goalsApi, materialsApi, notesApi, ragApi } from "../api/resources";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { useToast } from "../components/toast-context";
import type { RagCitation, RagMessage } from "../types";
import { formatDateTime } from "../utils/format";

type StreamData = { text?: string; message?: string };

function AnswerText({
  message,
  onCitation,
}: {
  message: RagMessage;
  onCitation: (citation: RagCitation) => void;
}) {
  const citations = new Map(message.citations.map((item) => [item.source_label, item]));
  return (
    <p className="rag-answer">
      {message.content.split(/(\[S\d+\])/g).map((part, index) => {
        const label = part.match(/^\[(S\d+)\]$/)?.[1];
        const citation = label ? citations.get(label) : undefined;
        return citation ? (
          <button
            key={`${part}-${index}`}
            className="citation-chip"
            onClick={() => onCitation(citation)}
            title={`查看 ${citation.original_filename} 的引用片段`}
          >
            {label}
          </button>
        ) : (
          <Fragment key={`${part}-${index}`}>{part}</Fragment>
        );
      })}
    </p>
  );
}

export function RagPage() {
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [question, setQuestion] = useState("");
  const initialScope = searchParams.get("scope") ?? "all";
  const [scopeType, setScopeType] = useState(initialScope);
  const [goalId, setGoalId] = useState(searchParams.get("learning_goal_id") ?? "");
  const [courseId, setCourseId] = useState(searchParams.get("course_id") ?? "");
  const [pointId, setPointId] = useState(searchParams.get("knowledge_point_id") ?? "");
  const [materialIds, setMaterialIds] = useState<number[]>(searchParams.get("material_id") ? [Number(searchParams.get("material_id"))] : []);
  const [selectedCitation, setSelectedCitation] = useState<RagCitation | null>(null);
  const [streamText, setStreamText] = useState("");
  const [stage, setStage] = useState("");
  const [sending, setSending] = useState(false);
  const [targetNoteId, setTargetNoteId] = useState("");
  const controllerRef = useRef<AbortController | null>(null);

  const statusQuery = useQuery({ queryKey: ["rag-status"], queryFn: ragApi.status });
  const conversations = useQuery({
    queryKey: ["rag-conversations"],
    queryFn: ragApi.list,
  });
  const materials = useQuery({
    queryKey: ["materials", "", ""],
    queryFn: () => materialsApi.list(),
  });
  const goals = useQuery({ queryKey: ["goals"], queryFn: goalsApi.list });
  const courses = useQuery({ queryKey: ["courses"], queryFn: coursesApi.list });
  const points = useQuery({ queryKey: ["knowledge-points", courseId], queryFn: () => coursesApi.points(Number(courseId)), enabled: !!courseId });
  const detail = useQuery({
    queryKey: ["rag-conversation", conversationId],
    queryFn: () => ragApi.get(conversationId!),
    enabled: conversationId !== null,
  });
  const notes = useQuery({ queryKey: ["notes", "rag-picker"], queryFn: () => notesApi.list({ pageSize: 100 }) });

  useEffect(() => {
    if (conversationId === null && conversations.data?.items.length) {
      setConversationId(conversations.data.items[0].id);
    }
  }, [conversationId, conversations.data]);
  useEffect(() => () => controllerRef.current?.abort(), []);

  const usableMaterials = useMemo(
    () =>
      (materials.data ?? []).filter(
        (item) =>
          item.ingestion_status === "completed" &&
          item.indexing_status === "completed",
      ),
    [materials.data],
  );

  const createConversation = useMutation({
    mutationFn: () => ragApi.create(),
    onSuccess: async (item) => {
      await queryClient.invalidateQueries({ queryKey: ["rag-conversations"] });
      setConversationId(item.id);
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const archiveConversation = useMutation({
    mutationFn: ragApi.archive,
    onSuccess: async () => {
      setConversationId(null);
      setSelectedCitation(null);
      await queryClient.invalidateQueries({ queryKey: ["rag-conversations"] });
      showToast("会话已归档", "success");
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const saveCitation = async (noteId?: number) => {
    if (!selectedCitation?.material_id || !selectedCitation.source_available) {
      showToast("当前来源已经失效，无法建立新的资料摘录", "error");
      return;
    }
    const source = {
      material_id: selectedCitation.material_id,
      chunk_id: selectedCitation.chunk_id,
      source_title: selectedCitation.original_filename,
      source_locator: selectedCitation.page_number
        ? `第 ${selectedCitation.page_number} 页`
        : selectedCitation.section_title ?? `片段 ${selectedCitation.chunk_index + 1}`,
      quoted_text: selectedCitation.content_excerpt,
    };
    if (noteId) {
      await notesApi.addSource(noteId, source);
    } else {
      await notesApi.create({
        title: `资料摘录 · ${selectedCitation.original_filename}`,
        content_markdown: "## 我的补充\n",
        note_type: "material",
        links: [{ entity_type: "material", entity_id: selectedCitation.material_id }],
        sources: [source],
      });
    }
    await queryClient.invalidateQueries({ queryKey: ["notes"] });
    setTargetNoteId("");
    showToast(noteId ? "引用已添加到笔记" : "引用已保存为新笔记", "success");
  };
  const saveAnswer = async (message: RagMessage) => {
    await notesApi.create({
      title: "资料问答整理",
      content_markdown: `## 回答整理\n${message.content}\n\n## 我的补充\n`,
      note_type: "study",
      links: [{ entity_type: "rag_message", entity_id: message.id, relation_type: "derived_from" }],
    });
    await queryClient.invalidateQueries({ queryKey: ["notes"] });
    showToast("回答已作为草稿保存，请在笔记本继续整理", "success");
  };

  const send = async () => {
    const trimmed = question.trim();
    if (!trimmed || sending) return;
    let id = conversationId;
    try {
      if (id === null) {
        const created = await ragApi.create();
        id = created.id;
        setConversationId(id);
        await queryClient.invalidateQueries({ queryKey: ["rag-conversations"] });
      }
      setSending(true);
      setStreamText("");
      setStage("正在读取问题");
      const controller = new AbortController();
      controllerRef.current = controller;
      await ragApi.stream(
        id,
        {
          question: trimmed,
          request_id: crypto.randomUUID(),
          material_ids: materialIds.length ? materialIds : null,
          learning_goal_id: scopeType === "learning_goal" && goalId ? Number(goalId) : null,
          course_id: scopeType === "course" && courseId ? Number(courseId) : null,
          knowledge_point_id: scopeType === "knowledge_point" && pointId ? Number(pointId) : null,
        },
        controller.signal,
        (event, raw) => {
          const data = raw as StreamData;
          if (event === "run.started") setStage("正在准备资料问答");
          if (event === "retrieval.started") setStage("正在查找相关资料");
          if (event === "retrieval.completed") setStage("正在准备有依据的回答");
          if (event === "generation.completed") setStage("回答已完成校验");
          if (event === "answer.completed") setStreamText(data.text ?? "");
          if (event === "run.failed") throw new Error(data.message ?? "资料问答失败");
        },
      );
      setQuestion("");
      setStage("");
      setStreamText("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["rag-conversation", id] }),
        queryClient.invalidateQueries({ queryKey: ["rag-conversations"] }),
      ]);
    } catch (error) {
      if (!controllerRef.current?.signal.aborted) {
        showToast(
          error instanceof Error ? error.message : "资料问答失败",
          "error",
        );
      }
      if (id !== null) {
        await queryClient.invalidateQueries({
          queryKey: ["rag-conversation", id],
        });
      }
    } finally {
      setSending(false);
      setStage("");
      controllerRef.current = null;
    }
  };

  if (conversations.isLoading || statusQuery.isLoading) {
    return <LoadingState label="正在加载资料问答" />;
  }
  if (conversations.isError || statusQuery.isError) {
    const error = (conversations.error ?? statusQuery.error) as Error;
    return (
      <ErrorState
        message={error.message}
        onRetry={() => {
          conversations.refetch();
          statusQuery.refetch();
        }}
      />
    );
  }

  return (
    <div className="rag-page">
      <aside className="rag-sessions">
        <header>
          <div>
            <span>学习知识库</span>
            <h2>资料问答</h2>
          </div>
          <button
            className="icon-button"
            aria-label="新建资料问答"
            onClick={() => createConversation.mutate()}
            disabled={createConversation.isPending}
          >
            <MessageSquarePlus size={18} />
          </button>
        </header>
        <div className="rag-status-strip">
          <span
            className={
              statusQuery.data?.index_available
                ? "status-dot"
                : "status-dot status-dot--off"
            }
          />
          <div>
            <strong>
              {statusQuery.data?.index_available ? "资料可用于问答" : "资料正在准备"}
            </strong>
            <small>
              {statusQuery.data?.llm_configured ? "AI 回答可用" : "AI 回答尚未配置"}
            </small>
          </div>
        </div>
        <nav aria-label="资料问答会话">
          {conversations.data?.items.map((item) => (
            <button
              key={item.id}
              className={`rag-session-item ${
                conversationId === item.id ? "rag-session-item--active" : ""
              }`}
              onClick={() => {
                setConversationId(item.id);
                setSelectedCitation(null);
              }}
            >
              <strong>{item.title}</strong>
              <small>{formatDateTime(item.last_message_at ?? item.created_at)}</small>
            </button>
          ))}
        </nav>
        {!conversations.data?.items.length && (
          <p className="rag-list-empty">还没有会话，发送第一个问题即可创建。</p>
        )}
      </aside>

      <main className="rag-workspace">
        <header className="rag-workspace__head">
          <div>
            <span>仅依据本地资料回答</span>
            <h2>{detail.data?.title ?? "新建资料问答"}</h2>
          </div>
          {conversationId && (
            <button
              className="button button--secondary"
              onClick={() => archiveConversation.mutate(conversationId)}
            >
              <Archive size={16} /> 归档
            </button>
          )}
        </header>

        <section className="rag-messages" aria-live="polite">
          {detail.isLoading && <LoadingState label="正在恢复历史消息" />}
          {detail.isError && (
            <ErrorState
              message={(detail.error as Error).message}
              onRetry={() => detail.refetch()}
            />
          )}
          {!detail.isLoading && !detail.data?.messages.length && !streamText && (
            <EmptyState
              title="向你的资料提问"
              description="回答会标明来源；找不到足够依据时，系统会明确拒答。"
            />
          )}
          {detail.data?.messages.map((message) => (
            <article
              key={message.id}
              className={`rag-message rag-message--${message.role}`}
            >
              <div className="rag-message__meta">
                <strong>{message.role === "user" ? "你" : "资料助手"}</strong>
                <small>{formatDateTime(message.created_at)}</small>
              </div>
              {message.role === "assistant" ? (
                <AnswerText message={message} onCitation={setSelectedCitation} />
              ) : (
                <p>{message.content}</p>
              )}
              {message.role === "assistant" && message.answerable === false && (
                <span className="rag-refusal">{message.refusal_reason === "empty_material_scope" ? "当前范围还没有关联可检索资料，请先完成资料归类。" : "资料依据不足 · 未生成推测性答案"}</span>
              )}
              {message.role === "assistant" && message.answerable && <button className="text-button rag-note-action" onClick={() => void saveAnswer(message)}><NotebookPen size={15}/>保存回答到新笔记</button>}
            </article>
          ))}
          {sending && (
            <article className="rag-message rag-message--assistant">
              <div className="rag-message__meta">
                <strong>资料助手</strong><small>{stage}</small>
              </div>
              {streamText ? (
                <p className="rag-answer">{streamText}</p>
              ) : (
                <span className="spinner" />
              )}
            </article>
          )}
        </section>

        <section className="rag-composer">
          <div className="rag-scope">
            <FileSearch size={16} />
            <span>检索范围</span>
            <select
              aria-label="检索范围类型"
              value={scopeType}
              onChange={(event) => { setScopeType(event.target.value); setGoalId(""); setCourseId(""); setPointId(""); setMaterialIds([]); }}
            >
              <option value="all">全部可用于问答的资料</option><option value="learning_goal">事项</option><option value="course">路线</option><option value="knowledge_point">步骤</option><option value="material">指定资料</option>
            </select>
            {scopeType === "learning_goal" && <select aria-label="选择检索事项" value={goalId} onChange={(event) => setGoalId(event.target.value)}><option value="">选择事项</option>{goals.data?.map((goal) => <option key={goal.id} value={goal.id}>{goal.title}</option>)}</select>}
            {(scopeType === "course" || scopeType === "knowledge_point") && <select aria-label="选择检索路线" value={courseId} onChange={(event) => { setCourseId(event.target.value); setPointId(""); }}><option value="">选择路线</option>{courses.data?.map((course) => <option key={course.id} value={course.id}>{course.title}</option>)}</select>}
            {scopeType === "knowledge_point" && <select aria-label="选择检索步骤" value={pointId} onChange={(event) => setPointId(event.target.value)} disabled={!courseId}><option value="">选择步骤</option>{points.data?.map((point) => <option key={point.id} value={point.id}>{point.title}</option>)}</select>}
            {scopeType === "material" && <select aria-label="选择检索资料" value={materialIds[0] ?? ""} onChange={(event) => setMaterialIds(event.target.value ? [Number(event.target.value)] : [])}><option value="">选择资料</option>{usableMaterials.map((item) => <option key={item.id} value={item.id}>{item.original_filename}</option>)}</select>}
          </div>
          <textarea
            aria-label="向资料提问"
            placeholder="例如：MCP 的 Tools 与 Resources 有什么区别？"
            value={question}
            maxLength={2000}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void send();
              }
            }}
          />
          {sending ? (
            <button
              className="button button--secondary"
              onClick={() => controllerRef.current?.abort()}
            >
              <Square size={15} /> 停止
            </button>
          ) : (
            <button
              className="button button--primary"
              disabled={!question.trim() || (scopeType === "learning_goal" && !goalId) || (scopeType === "course" && !courseId) || (scopeType === "knowledge_point" && !pointId) || (scopeType === "material" && !materialIds.length)}
              onClick={() => void send()}
            >
              <Send size={16} /> 发送
            </button>
          )}
        </section>
      </main>

      <aside className="rag-source-panel">
        <header><BookOpenCheck size={18} /><h2>引用详情</h2></header>
        {selectedCitation ? (
          <div className="rag-source-detail">
            <span className="citation-chip">{selectedCitation.source_label}</span>
            <h3>{selectedCitation.original_filename}</h3>
            <dl>
              <div>
                <dt>位置</dt>
                <dd>
                  {selectedCitation.page_number
                    ? `第 ${selectedCitation.page_number} 页`
                    : selectedCitation.section_title ??
                      `片段 ${selectedCitation.chunk_index + 1}`}
                </dd>
              </div>
              <div>
                <dt>当前来源</dt>
                <dd>{selectedCitation.source_available ? "可用" : "已删除（快照）"}</dd>
              </div>
            </dl>
            <blockquote>{selectedCitation.content_excerpt}</blockquote>
            {!!selectedCitation.learning_context?.material_links?.length && <div className="citation-learning-context"><strong>学习归属</strong>{selectedCitation.learning_context.material_links.map((link) => <span key={`${link.target_type}-${link.target_id}`}>{link.target_title}</span>)}</div>}
            {selectedCitation.material_id && <Link className="text-link" to={`/materials/${selectedCitation.material_id}${selectedCitation.chunk_id ? `?chunk=${selectedCitation.chunk_id}` : ""}`}>打开资料上下文</Link>}
            <div className="rag-source-note-actions"><button className="button button--secondary" onClick={() => void saveCitation()}><NotebookPen size={15}/>只保存引用为新笔记</button><div className="inline-form"><select aria-label="选择已有笔记" value={targetNoteId} onChange={(event) => setTargetNoteId(event.target.value)}><option value="">添加到已有笔记</option>{(notes.data?.items ?? []).map((note) => <option key={note.id} value={note.id}>{note.title}</option>)}</select><button className="button button--secondary" disabled={!targetNoteId} onClick={() => void saveCitation(Number(targetNoteId))}>添加</button></div></div>
          </div>
        ) : (
          <p className="rag-source-empty">
            点击答案中的 S1、S2 等来源标签，查看对应资料片段。
          </p>
        )}
      </aside>
    </div>
  );
}
