import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  BookOpenCheck,
  Play,
  Send,
  Trash2,
} from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import { activitiesApi } from "../api/resources";
import { ErrorState, LoadingState } from "../components/States";
import { useToast } from "../components/toast-context";

const typeLabel: Record<string, string> = {
  single_choice: "单选题",
  multiple_choice: "多选题",
  true_false: "判断题",
  short_answer: "简答题",
};

export function ActivityBuilderPage() {
  const { id } = useParams();
  const activityId = Number(id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const activity = useQuery({
    queryKey: ["learning-activity", activityId],
    queryFn: () => activitiesApi.get(activityId),
    enabled: Number.isFinite(activityId),
  });
  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["learning-activity", activityId] }),
      queryClient.invalidateQueries({ queryKey: ["learning-activities"] }),
    ]);
  };
  const remove = useMutation({
    mutationFn: (questionId: number) =>
      activitiesApi.deleteQuestion(activityId, questionId),
    onSuccess: refresh,
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const reorder = useMutation({
    mutationFn: (questionIds: number[]) =>
      activitiesApi.reorder(activityId, questionIds),
    onSuccess: refresh,
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const publish = useMutation({
    mutationFn: () => activitiesApi.publish(activityId),
    onSuccess: async () => {
      await refresh();
      showToast("活动已发布，题目内容现已固定", "success");
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const start = useMutation({
    mutationFn: () => activitiesApi.start(activityId),
    onSuccess: (attempt) => navigate(`/quiz-attempts/${attempt.id}`),
    onError: (error: Error) => showToast(error.message, "error"),
  });

  if (activity.isLoading) return <LoadingState label="正在加载活动草稿" />;
  if (activity.isError || !activity.data) {
    return (
      <ErrorState
        message={(activity.error as Error)?.message ?? "活动不存在"}
        onRetry={() => activity.refetch()}
      />
    );
  }

  const move = (index: number, direction: -1 | 1) => {
    const ids = activity.data.questions.map((question) => question.id);
    const target = index + direction;
    if (target < 0 || target >= ids.length) return;
    [ids[index], ids[target]] = [ids[target], ids[index]];
    reorder.mutate(ids);
  };
  const isDraft = activity.data.status === "draft";

  return (
    <div className="page activity-builder">
      <button className="text-button" onClick={() => navigate("/activities")}>
        <ArrowLeft size={16} />返回学习活动
      </button>
      <header className="page-header page-header--split">
        <div>
          <span className="eyebrow">{isDraft ? "草稿预览" : "已发布活动"}</span>
          <h1>{activity.data.title}</h1>
          <p>{activity.data.description || "暂无活动说明"}</p>
        </div>
        <div className="button-group">
          {isDraft ? (
            <button
              className="button button--primary"
              disabled={publish.isPending || !activity.data.questions.length}
              onClick={() => {
                if (
                  window.confirm(
                    "发布后题目内容将固定，后续答题记录会基于当前版本保存。",
                  )
                ) {
                  publish.mutate();
                }
              }}
            >
              <Send size={16} />发布活动
            </button>
          ) : activity.data.status === "published" ? (
            <button
              className="button button--primary"
              disabled={start.isPending}
              onClick={() => start.mutate()}
            >
              <Play size={16} />{start.isPending ? "正在开始…" : "开始测验"}
            </button>
          ) : null}
        </div>
      </header>

      <section className="activity-summary">
        <div><span>题目</span><strong>{activity.data.question_count}</strong></div>
        <div><span>总分</span><strong>{activity.data.total_points}</strong></div>
        <div><span>完成次数</span><strong>{activity.data.completed_attempt_count}</strong></div>
        <div><span>来源策略</span><strong>真实 Chunk</strong></div>
      </section>

      {activity.data.validation_warnings.length > 0 && (
        <aside className="activity-warning">
          <strong>校验提示</strong>
          {activity.data.validation_warnings.map((warning) => (
            <p key={warning}>{warning}</p>
          ))}
        </aside>
      )}

      <section className="question-preview-list">
        {activity.data.questions.map((question, index) => (
          <article key={question.id} className="question-card">
            <header>
              <div>
                <span className="question-number">{question.question_index}</span>
                <span className="status">{typeLabel[question.question_type]}</span>
                <span className="muted">{question.difficulty} · {question.points} 分</span>
              </div>
              {isDraft && (
                <div className="question-card__actions">
                  <button
                    className="icon-button"
                    aria-label={`上移第 ${question.question_index} 题`}
                    disabled={index === 0 || reorder.isPending}
                    onClick={() => move(index, -1)}
                  ><ArrowUp size={16} /></button>
                  <button
                    className="icon-button"
                    aria-label={`下移第 ${question.question_index} 题`}
                    disabled={index === activity.data.questions.length - 1 || reorder.isPending}
                    onClick={() => move(index, 1)}
                  ><ArrowDown size={16} /></button>
                  <button
                    className="icon-button icon-button--danger"
                    aria-label={`删除第 ${question.question_index} 题`}
                    disabled={remove.isPending}
                    onClick={() => remove.mutate(question.id)}
                  ><Trash2 size={16} /></button>
                </div>
              )}
            </header>
            <h2>{question.stem}</h2>
            {question.options && (
              <ol className="question-options">
                {question.options.map((option) => (
                  <li key={option.id}>
                    <strong>{option.id}</strong><span>{option.text}</span>
                  </li>
                ))}
              </ol>
            )}
            {isDraft && (
              <div className="question-answer-panel">
                <div>
                  <span>标准答案</span>
                  <strong>
                    {question.correct_answer?.map(String).join("、") ??
                      question.reference_answer}
                  </strong>
                </div>
                <div>
                  <span>解析</span>
                  <p>{question.explanation}</p>
                </div>
                {question.grading_rubric && (
                  <div>
                    <span>评分标准</span>
                    <ul>
                      {question.grading_rubric.map((item) => (
                        <li key={item.criterion}>
                          {item.criterion} · {item.points} 分 · {item.required_concepts.join("、")}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
            {isDraft && question.sources.map((source) => (
              <details key={source.id} className="source-disclosure">
                <summary>
                  <BookOpenCheck size={15} />
                  {source.source_label} · {source.original_filename}
                </summary>
                <p>{source.content_excerpt}</p>
              </details>
            ))}
          </article>
        ))}
      </section>
    </div>
  );
}
