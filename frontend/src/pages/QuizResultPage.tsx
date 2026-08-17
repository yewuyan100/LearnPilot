import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, BookOpenCheck, CheckCircle2, CircleX, MinusCircle } from "lucide-react";
import { Link, useLocation, useParams } from "react-router-dom";
import { activitiesApi, attemptsApi, masteryApi, nextActionApi } from "../api/resources";
import { ErrorState, LoadingState } from "../components/States";
import { parseQuizNavigation } from "../utils/quizNavigation";

const questionTypeLabel: Record<string, string> = {
  single_choice: "单选题",
  multiple_choice: "多选题",
  true_false: "判断题",
  short_answer: "简答题",
};

const masteryLevelLabel: Record<string, string> = {
  unassessed: "还需要更多练习",
  beginner: "正在建立基础",
  developing: "正在逐步稳定",
  proficient: "已经能够运用",
  strong: "掌握得很稳固",
};

export function QuizResultPage() {
  const attemptId = Number(useParams().id);
  const location = useLocation();
  const navigation = parseQuizNavigation(location.search);
  const attempt = useQuery({
    queryKey: ["quiz-attempt", attemptId],
    queryFn: () => attemptsApi.get(attemptId),
    enabled: Number.isFinite(attemptId),
  });
  const activity = useQuery({
    queryKey: ["learning-activity", attempt.data?.activity_id],
    queryFn: () => activitiesApi.get(attempt.data!.activity_id),
    enabled: Boolean(attempt.data?.activity_id),
  });
  const mastery = useQuery({
    queryKey: ["mastery", activity.data?.knowledge_point_id],
    queryFn: () => masteryApi.get(activity.data!.knowledge_point_id!),
    enabled: Boolean(activity.data?.knowledge_point_id),
    retry: false,
  });
  const nextAction = useQuery({
    queryKey: ["next-learning-action", "after-quiz", attemptId],
    queryFn: () => nextActionApi.get(),
    enabled: attempt.data?.status === "completed" && Boolean(navigation.goalId),
    retry: false,
  });

  if (attempt.isLoading) return <LoadingState label="正在加载反馈" />;
  if (attempt.isError || !attempt.data) {
    return <ErrorState message={(attempt.error as Error)?.message ?? "结果不存在"} onRetry={() => attempt.refetch()} />;
  }

  const result = attempt.data;
  const itemId = navigation.goalId;
  const needsWork = result.answers.filter((answer) => (
    answer.is_correct === false
    || Boolean(answer.missing_rubric_items?.length)
    || answer.earned_points === 0
  ));
  const action = nextAction.data?.learning_goal_id === itemId ? nextAction.data : null;
  const nextHref = action?.cta_href || navigation.returnHref;
  const nextLabel = action?.action_type === "review_proposal"
    ? "查看调整建议"
    : action?.cta_label || "继续下一步";

  return <div className="page quiz-result">
    <Link className="text-link" to={navigation.returnHref}><ArrowLeft size={16}/>{navigation.returnLabel}</Link>
    <header className="result-hero">
      <div><span>这次表现</span><h1>{result.activity_title}</h1><p>{result.status === "completed" ? "反馈已经更新到当前事项，接下来可以继续推进或先加强薄弱处。" : "部分内容还在批改中，请稍后刷新。"}</p></div>
      <div className="score-ring"><strong>{result.score_percentage ?? "—"}%</strong><span>{result.earned_points ?? "—"} / {result.total_points ?? "—"} 分</span></div>
    </header>

    <section className="result-metrics" aria-label="本次结果摘要">
      <div><CheckCircle2/><span>完成得好</span><strong>{result.correct_count}</strong></div>
      <div><CircleX/><span>需要加强</span><strong>{result.incorrect_count}</strong></div>
      <div><MinusCircle/><span>已有思路</span><strong>{result.partial_count}</strong></div>
    </section>

    <div className="result-follow-through">
      <section aria-labelledby="result-strengthen-title">
        <h2 id="result-strengthen-title">需要加强</h2>
        {needsWork.length ? <ul>{needsWork.slice(0, 4).map((answer) => <li key={answer.id}><strong>{answer.stem}</strong><span>{answer.feedback || answer.missing_rubric_items?.join("、") || "回看解析后再试一次"}</span></li>)}</ul> : <p>这次没有明显薄弱项，可以继续下一步。</p>}
        {mastery.data && <p className="result-mastery-summary">当前判断：{masteryLevelLabel[mastery.data.mastery_level] ?? "正在积累练习记录"}</p>}
      </section>
      <section aria-labelledby="result-next-title">
        <h2 id="result-next-title">下一步</h2>
        <strong>{action?.title ?? "回到学习上下文继续推进"}</strong>
        <p>{action?.reason ?? "这次练习已经记入反馈，可以回到刚才的学习上下文继续。"}</p>
        <div className="button-row"><Link className="button button--primary" to={nextHref}>{nextLabel}<ArrowRight size={16}/></Link>{itemId && nextHref !== `/items/${itemId}` && <Link className="button button--secondary" to={`/items/${itemId}`}>返回事项</Link>}</div>
      </section>
    </div>

    {result.error_message && <p className="quiz-error">{result.error_message}</p>}
    <section className="result-answer-list" aria-label="逐题反馈">
      {result.answers.map((answer, index) => <article key={answer.id} className="result-answer">
        <header><span className="question-number">{index + 1}</span><div><span>{questionTypeLabel[answer.question_type] ?? "练习题"}</span><strong>{answer.earned_points === null ? "暂未完成批改" : `${answer.earned_points} / ${answer.max_points} 分`}</strong></div></header>
        <h2>{answer.stem}</h2>
        <dl><div><dt>你的答案</dt><dd>{answer.answer_text || answer.answer?.map(String).join("、") || "未作答"}</dd></div><div><dt>参考答案</dt><dd>{answer.reference_answer || answer.correct_answer?.map(String).join("、") || "—"}</dd></div><div><dt>反馈</dt><dd>{answer.feedback || "该题暂未完成批改，请稍后重试。"}</dd></div><div><dt>解析</dt><dd>{answer.explanation || "—"}</dd></div></dl>
        {answer.matched_rubric_items?.length ? <p className="rubric-hit">做到了：{answer.matched_rubric_items.join("、")}</p> : null}
        {answer.missing_rubric_items?.length ? <p className="rubric-miss">可以补充：{answer.missing_rubric_items.join("、")}</p> : null}
        {answer.sources.map((source) => <details key={source.id} className="source-disclosure"><summary><BookOpenCheck size={15}/>{source.source_label} · {source.original_filename}{!source.source_available ? "（来源已删除，显示快照）" : ""}</summary><p>{source.content_excerpt}</p></details>)}
      </article>)}
    </section>
  </div>;
}
