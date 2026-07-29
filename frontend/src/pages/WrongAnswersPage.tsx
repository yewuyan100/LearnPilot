import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpenCheck, CheckCheck, EyeOff, Play, RotateCcw } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { wrongAnswersApi } from "../api/resources";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { useToast } from "../components/toast-context";
import { formatDateTime } from "../utils/format";

const statusLabel: Record<string, string> = {
  active: "待复习",
  reviewing: "复习中",
  resolved: "已掌握",
  dismissed: "已忽略",
};

export function WrongAnswersPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState<number[]>([]);
  const wrongs = useQuery({
    queryKey: ["wrong-answers", status],
    queryFn: () => wrongAnswersApi.list(status),
  });
  const update = useMutation({
    mutationFn: ({ id, value }: { id: number; value: "active" | "resolved" | "dismissed" }) =>
      wrongAnswersApi.update(id, value),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["wrong-answers"] }),
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const review = useMutation({
    mutationFn: () => wrongAnswersApi.review(selected),
    onSuccess: (attempt) => navigate(`/quiz-attempts/${attempt.id}`),
    onError: (error: Error) => showToast(error.message, "error"),
  });
  if (wrongs.isLoading) return <LoadingState label="正在加载错题本" />;
  if (wrongs.isError) {
    return <ErrorState message={(wrongs.error as Error).message} onRetry={() => wrongs.refetch()} />;
  }
  return (
    <div className="page wrong-answer-page">
      <header className="page-header page-header--split">
        <div>
          <span className="eyebrow">V4 · 错题闭环</span>
          <h1>错题本</h1>
          <p>这里的“已掌握”是你的复习状态，不代表算法掌握度。</p>
        </div>
        <button
          className="button button--primary"
          disabled={!selected.length || review.isPending}
          onClick={() => review.mutate()}
        >
          <Play size={16} />复习所选 {selected.length ? `(${selected.length})` : ""}
        </button>
      </header>
      <div className="toolbar wrong-filter">
        <label className="select-field">
          <span>状态</span>
          <select value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="">全部错题</option>
            <option value="active">待复习</option>
            <option value="reviewing">复习中</option>
            <option value="resolved">已掌握</option>
            <option value="dismissed">已忽略</option>
          </select>
        </label>
        <span>{wrongs.data?.total ?? 0} 条记录</span>
      </div>
      {!wrongs.data?.items.length ? (
        <EmptyState title="当前没有错题" description="完成学习活动后，错误、未作答或低分题会自动出现在这里。" />
      ) : (
        <div className="wrong-list">
          {wrongs.data.items.map((wrong) => (
            <article key={wrong.id} className="wrong-card">
              <header>
                <label>
                  <input
                    type="checkbox"
                    aria-label={`选择错题 ${wrong.id}`}
                    disabled={wrong.status === "dismissed"}
                    checked={selected.includes(wrong.id)}
                    onChange={(event) =>
                      setSelected((current) =>
                        event.target.checked
                          ? [...current, wrong.id]
                          : current.filter((id) => id !== wrong.id),
                      )
                    }
                  />
                  <span className={`status status--${wrong.status}`}>{statusLabel[wrong.status]}</span>
                </label>
                <small>{formatDateTime(wrong.updated_at)} · 已复习 {wrong.review_count} 次</small>
              </header>
              <h2>{wrong.stem}</h2>
              <p>{wrong.course_title ?? "未关联课程"}{wrong.knowledge_point_title ? ` · ${wrong.knowledge_point_title}` : ""}</p>
              <details className="wrong-details">
                <summary>查看答案、解析与来源</summary>
                <dl>
                  <div><dt>你的答案</dt><dd>{wrong.answer_text || wrong.answer?.map(String).join("、") || "未作答"}</dd></div>
                  <div><dt>参考答案</dt><dd>{wrong.reference_answer || wrong.correct_answer?.map(String).join("、")}</dd></div>
                  <div><dt>解析</dt><dd>{wrong.explanation}</dd></div>
                </dl>
                {wrong.sources.map((source) => (
                  <blockquote key={source.id}>
                    <BookOpenCheck size={15} /> {source.original_filename} · {source.content_excerpt}
                  </blockquote>
                ))}
              </details>
              <div className="wrong-card__actions">
                {wrong.status !== "resolved" && (
                  <button className="button button--secondary" onClick={() => update.mutate({ id: wrong.id, value: "resolved" })}>
                    <CheckCheck size={16} />标记已掌握
                  </button>
                )}
                {wrong.status !== "dismissed" ? (
                  <button className="button button--ghost" onClick={() => update.mutate({ id: wrong.id, value: "dismissed" })}>
                    <EyeOff size={16} />忽略
                  </button>
                ) : (
                  <button className="button button--ghost" onClick={() => update.mutate({ id: wrong.id, value: "active" })}>
                    <RotateCcw size={16} />恢复
                  </button>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
