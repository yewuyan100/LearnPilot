import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  BookOpenCheck,
  FileSearch,
  MessageSquarePlus,
  Send,
  Square,
} from "lucide-react";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { materialsApi, ragApi } from "../api/resources";
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
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [question, setQuestion] = useState("");
  const [materialIds, setMaterialIds] = useState<number[]>([]);
  const [selectedCitation, setSelectedCitation] = useState<RagCitation | null>(null);
  const [streamText, setStreamText] = useState("");
  const [stage, setStage] = useState("");
  const [sending, setSending] = useState(false);
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
  const detail = useQuery({
    queryKey: ["rag-conversation", conversationId],
    queryFn: () => ragApi.get(conversationId!),
    enabled: conversationId !== null,
  });

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
        },
        controller.signal,
        (event, raw) => {
          const data = raw as StreamData;
          if (event === "accepted") setStage("正在查找相关资料");
          if (event === "retrieval") setStage("正在准备有依据的回答");
          if (event === "message_start") setStage("正在输出已校验答案");
          if (event === "delta") setStreamText((value) => value + (data.text ?? ""));
          if (event === "error") throw new Error(data.message ?? "资料问答失败");
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
            <h1>资料问答</h1>
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
              {statusQuery.data?.index_available ? "知识索引可用" : "知识索引不可用"}
            </strong>
            <small>
              {statusQuery.data?.llm_configured ? "回答模型已配置" : "回答模型尚未配置"}
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
                <span className="rag-refusal">资料依据不足 · 未生成推测性答案</span>
              )}
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
            <span>资料范围</span>
            <select
              aria-label="资料范围"
              value={materialIds[0] ?? ""}
              onChange={(event) =>
                setMaterialIds(
                  event.target.value ? [Number(event.target.value)] : [],
                )
              }
            >
              <option value="">全部已索引资料</option>
              {usableMaterials.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.original_filename}
                </option>
              ))}
            </select>
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
              disabled={!question.trim()}
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
              <div><dt>相关度</dt><dd>{selectedCitation.score.toFixed(3)}</dd></div>
              <div>
                <dt>当前来源</dt>
                <dd>{selectedCitation.source_available ? "可用" : "已删除（快照）"}</dd>
              </div>
            </dl>
            <blockquote>{selectedCitation.content_excerpt}</blockquote>
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
