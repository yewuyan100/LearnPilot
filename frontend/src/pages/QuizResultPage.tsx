import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, BookOpenCheck, CheckCircle2, CircleX, MinusCircle } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import { attemptsApi } from "../api/resources";
import { ErrorState, LoadingState } from "../components/States";

export function QuizResultPage() {
  const { id } = useParams();
  const attemptId = Number(id);
  const navigate = useNavigate();
  const attempt = useQuery({
    queryKey: ["quiz-attempt", attemptId],
    queryFn: () => attemptsApi.get(attemptId),
  });
  if (attempt.isLoading) return <LoadingState label="正在加载批改结果" />;
  if (attempt.isError || !attempt.data) {
    return (
      <ErrorState
        message={(attempt.error as Error)?.message ?? "结果不存在"}
        onRetry={() => attempt.refetch()}
      />
    );
  }
  const result = attempt.data;
  return (
    <div className="page quiz-result">
      <button className="text-button" onClick={() => navigate("/activities")}>
        <ArrowLeft size={16} />返回学习活动
      </button>
      <header className="result-hero">
        <div>
          <span className="eyebrow">测验结果</span>
          <h1>{result.activity_title}</h1>
          <p>{result.status === "completed" ? "批改已完成，错题已自动进入错题本。" : "部分题目尚未完成批改。"}</p>
        </div>
        <div className="score-ring">
          <strong>{result.score_percentage ?? "—"}%</strong>
          <span>{result.earned_points ?? "—"} / {result.total_points ?? "—"} 分</span>
        </div>
      </header>
      <section className="result-metrics">
        <div><CheckCircle2 /><span>满分题</span><strong>{result.correct_count}</strong></div>
        <div><CircleX /><span>错误题</span><strong>{result.incorrect_count}</strong></div>
        <div><MinusCircle /><span>部分得分</span><strong>{result.partial_count}</strong></div>
      </section>
      {result.error_message && <p className="quiz-error">{result.error_message}</p>}
      <section className="result-answer-list">
        {result.answers.map((answer, index) => (
          <article key={answer.id} className="result-answer">
            <header>
              <span className="question-number">{index + 1}</span>
              <div>
                <span>{answer.question_type}</span>
                <strong>
                  {answer.earned_points === null
                    ? "暂未完成批改"
                    : `${answer.earned_points} / ${answer.max_points} 分`}
                </strong>
              </div>
            </header>
            <h2>{answer.stem}</h2>
            <dl>
              <div>
                <dt>你的答案</dt>
                <dd>{answer.answer_text || answer.answer?.map(String).join("、") || "未作答"}</dd>
              </div>
              <div>
                <dt>标准或参考答案</dt>
                <dd>{answer.reference_answer || answer.correct_answer?.map(String).join("、") || "—"}</dd>
              </div>
              <div><dt>评分反馈</dt><dd>{answer.feedback || "该题暂未完成批改，请稍后重试。"}</dd></div>
              <div><dt>解析</dt><dd>{answer.explanation || "—"}</dd></div>
            </dl>
            {answer.matched_rubric_items?.length ? (
              <p className="rubric-hit">已命中：{answer.matched_rubric_items.join("、")}</p>
            ) : null}
            {answer.missing_rubric_items?.length ? (
              <p className="rubric-miss">待补充：{answer.missing_rubric_items.join("、")}</p>
            ) : null}
            {answer.sources.map((source) => (
              <details key={source.id} className="source-disclosure">
                <summary>
                  <BookOpenCheck size={15} />
                  {source.source_label} · {source.original_filename}
                  {!source.source_available ? "（来源已删除，显示快照）" : ""}
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
