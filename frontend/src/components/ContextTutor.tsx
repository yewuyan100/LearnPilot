import { Bot, Send, Sparkles } from "lucide-react";
import { useState } from "react";
import { useLocation } from "react-router-dom";
import { ApiError } from "../api/client";
import { agentApi, learningRuntimeApi } from "../api/resources";
import type { LearningSurfaceContext, TutorAnswer } from "../types";
import { SafeMarkdown } from "./SafeMarkdown";

interface TutorExchange {
  id: string;
  question: string;
  answer: TutorAnswer;
}

interface ContextTutorProps {
  surfaceContext: LearningSurfaceContext;
  locationLabel: string;
  title?: string;
  inputLabel?: string;
  conversationTitle?: string;
  disabled?: boolean;
}

export function ContextTutor({
  surfaceContext,
  locationLabel,
  title = "就当前学习内容提问",
  inputLabel = "向当前学习内容的导师提问",
  conversationTitle = "情境化学习辅导",
  disabled = false,
}: ContextTutorProps) {
  const location = useLocation();
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [contextVersion, setContextVersion] = useState<string | null>(null);
  const [exchanges, setExchanges] = useState<TutorExchange[]>([]);
  const hasLearningPosition = Boolean(
    surfaceContext.course_id && surfaceContext.knowledge_point_id,
  );

  const ask = async () => {
    const question = input.trim();
    if (!question || busy || disabled || !hasLearningPosition) return;
    setBusy(true);
    setError(null);
    try {
      let activeConversationId = conversationId;
      if (activeConversationId === null) {
        const conversation = await agentApi.create(conversationTitle);
        activeConversationId = conversation.id;
        setConversationId(conversation.id);
      }
      const response = await learningRuntimeApi.run({
        request_id: crypto.randomUUID(),
        actor_key: "local-owner",
        input: question,
        conversation_id: activeConversationId,
        channel: "learning_session",
        surface_context: {
          ...surfaceContext,
          source_path: `${location.pathname}${location.search}`,
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Shanghai",
        },
        expected_context_version: contextVersion,
      });
      if (response.selected_agent !== "tutor" || !response.tutor_answer) {
        throw new Error("当前问题未进入学习辅导流程，请换一种方式描述你的疑问。");
      }
      setContextVersion(response.context_version);
      setExchanges((items) => [
        ...items,
        { id: response.run_id, question, answer: response.tutor_answer! },
      ]);
      setInput("");
    } catch (caught) {
      if (
        caught instanceof ApiError
        && ["context_mismatch", "context_version_conflict", "context_invalid"].includes(caught.code)
      ) {
        setError("当前学习内容已变化，请重新选择学习位置。");
      } else {
        setError(caught instanceof Error ? caught.message : "学习辅导暂时不可用，请稍后重试。");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="tutor-card" aria-labelledby="context-tutor-title">
      <header className="tutor-card__head">
        <div>
          <Sparkles size={18} />
          <div><span>情境化学习辅导</span><h2 id="context-tutor-title">{title}</h2></div>
        </div>
        <small>{locationLabel}</small>
      </header>
      <p className="tutor-card__intro">
        辅导会自动使用当前课节、知识点、会话和真实引用资料；回答不会生成掌握度证据。
      </p>
      {exchanges.length > 0 && (
        <div className="tutor-thread" aria-live="polite">
          {exchanges.map((exchange) => (
            <article className="tutor-exchange" key={exchange.id}>
              <div className="tutor-question"><strong>你</strong><p>{exchange.question}</p></div>
              <div className="tutor-answer">
                <strong><Bot size={16} />学习导师</strong>
                <SafeMarkdown content={exchange.answer.answer_markdown} />
                {exchange.answer.citations.length > 0 && (
                  <div className="tutor-sources" aria-label="回答引用">
                    {exchange.answer.citations.map((source) => (
                      <details key={`${exchange.id}-${source.source_label}`}>
                        <summary><span className="citation-chip">{source.source_label}</span>{source.original_filename}</summary>
                        <p>{source.content_excerpt}</p>
                      </details>
                    ))}
                  </div>
                )}
                {exchange.answer.follow_up_check && (
                  <p className="tutor-check"><strong>理解检查：</strong>{exchange.answer.follow_up_check}</p>
                )}
                {exchange.answer.limitations.length > 0 && (
                  <p className="tutor-limit">回答边界：{exchange.answer.limitations.join("；")}</p>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
      {error && <div className="notice notice--warning" role="alert">{error}</div>}
      <form className="tutor-composer" onSubmit={(event) => { event.preventDefault(); void ask(); }}>
        <textarea
          aria-label={inputLabel}
          rows={3}
          value={input}
          onChange={(event) => setInput(event.target.value)}
          disabled={disabled || busy || !hasLearningPosition}
          placeholder="例如：为什么这里要这样做？请结合当前资料举个例子。"
        />
        <button
          className="button button--primary"
          disabled={disabled || busy || !input.trim() || !hasLearningPosition}
        >
          <Send size={16} />{busy ? "正在讲解" : "提问"}
        </button>
      </form>
      {!hasLearningPosition && (
        <p className="tutor-limit">当前页面缺少课程或知识点上下文，暂时不能使用情境化辅导。</p>
      )}
    </section>
  );
}
