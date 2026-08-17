import { useMutation, useQueries, useQuery } from "@tanstack/react-query";
import { ArrowRight, FilePlus2, MessageSquareText, Route } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { activitiesApi, coursesApi, curriculumApi, dashboardApi, goalsApi, masteryApi, materialLearningApi, nextActionApi, notesApi, wrongAnswersApi } from "../api/resources";
import { EffectiveMaterials } from "../components/EffectiveMaterials";
import { GoalActions } from "../components/GoalActions";
import { ErrorState, LoadingState } from "../components/States";
import { TargetMaterialPicker } from "../components/TargetMaterialPicker";
import { useToast } from "../components/toast-context";
import { formatDate, formatDateTime, statusLabel } from "../utils/format";
import { quizOriginSearch } from "../utils/quizNavigation";
import { NotFoundPage } from "./NotFoundPage";

const goalDetailViews = [
  { id: "overview", label: "概览" },
  { id: "route", label: "路线" },
  { id: "content", label: "内容" },
  { id: "feedback", label: "反馈" },
  { id: "history", label: "记录" },
] as const;

type GoalDetailView = typeof goalDetailViews[number]["id"];

function isGoalDetailView(value: string | null): value is GoalDetailView {
  return goalDetailViews.some((view) => view.id === value);
}

export function GoalDetailPage() {
  const id = Number(useParams().id);
  const validId = Number.isInteger(id) && id > 0;
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedView = searchParams.get("view");
  const activeView: GoalDetailView = isGoalDetailView(requestedView) ? requestedView : "overview";
  const { showToast } = useToast();
  const [materialOpen, setMaterialOpen] = useState(false);
  const goal = useQuery({ queryKey: ["goal", id], queryFn: () => goalsApi.get(id), enabled: validId });
  const courses = useQuery({ queryKey: ["courses"], queryFn: coursesApi.list, enabled: validId });
  const materials = useQuery({ queryKey: ["effective-materials", "learning_goal", id], queryFn: () => materialLearningApi.goalMaterials(id), enabled: validId });
  const today = useQuery({ queryKey: ["today"], queryFn: dashboardApi.today, enabled: validId });
  const notes = useQuery({ queryKey: ["notes", "item", id], queryFn: () => notesApi.list({ entityType: "learning_goal", entityId: id, pageSize: 3 }), enabled: validId });
  const weakPoints = useQuery({ queryKey: ["mastery", "weak-points", "item", id], queryFn: masteryApi.weakPoints, enabled: validId, retry: false });
  const mastery = useQuery({ queryKey: ["mastery", "item", id], queryFn: masteryApi.list, enabled: validId, retry: false });
  const activities = useQuery({ queryKey: ["learning-activities", "item", id], queryFn: () => activitiesApi.list(), enabled: validId, retry: false });
  const wrongAnswers = useQuery({ queryKey: ["wrong-answers", "item", id], queryFn: () => wrongAnswersApi.list(), enabled: validId, retry: false });
  const reviews = useQuery({ queryKey: ["review-items", "item", id], queryFn: dashboardApi.reviews, enabled: validId, retry: false });
  const nextAction = useQuery({
    queryKey: ["next-learning-action", "item", id],
    queryFn: () => nextActionApi.get(),
    enabled: validId && today.isSuccess && today.data?.current_goal?.id === id,
    retry: false,
  });
  const relatedCourses = (courses.data ?? []).filter((course) => course.learning_goal_id === id);
  const pointQueries = useQueries({
    queries: relatedCourses.map((course) => ({
      queryKey: ["course-points", course.id],
      queryFn: () => coursesApi.points(course.id),
      staleTime: 30_000,
    })),
  });
  const generate = useMutation({
    mutationFn: () => curriculumApi.generate(id),
    onSuccess: (proposal) => navigate(`/curriculum-proposals/${proposal.proposal_id}`),
    onError: (error: Error) => showToast(error.message, "error"),
  });
  if (!validId) return <div className="page"><NotFoundPage /></div>;
  if (goal.isLoading || courses.isLoading || materials.isLoading || today.isLoading) return <div className="page"><LoadingState label="正在读取事项"/></div>;
  if (goal.isError || courses.isError || materials.isError || today.isError) return <div className="page"><ErrorState message={(goal.error ?? courses.error ?? materials.error ?? today.error)!.message}/></div>;

  const routeSteps = pointQueries.flatMap((query) => query.data ?? []);
  const currentStep = routeSteps.find((point) => point.id === nextAction.data?.knowledge_point_id)
    ?? routeSteps.find((point) => point.status === "learning")
    ?? routeSteps.find((point) => point.status === "not_started");
  const action = nextAction.data?.learning_goal_id === id ? nextAction.data : null;
  const relatedCourseIds = new Set(relatedCourses.map((course) => course.id));
  const strengthening = (weakPoints.data ?? []).filter((point) => relatedCourseIds.has(point.course_id)).slice(0, 4);
  const doingWell = (mastery.data?.items ?? []).filter((point) => relatedCourseIds.has(point.course_id) && (point.mastery_level === "proficient" || point.mastery_level === "strong")).slice(0, 4);
  const recentPractice = (activities.data?.items ?? []).filter((activity) => activity.course_id && relatedCourseIds.has(activity.course_id) && activity.completed_attempt_count > 0).sort((a, b) => b.updated_at.localeCompare(a.updated_at)).slice(0, 3);
  const activeWrong = (wrongAnswers.data?.items ?? []).filter((answer) => answer.course_id && relatedCourseIds.has(answer.course_id) && answer.status === "active");
  const dueReviews = (reviews.data?.knowledge_points ?? []).filter((point) => relatedCourseIds.has(point.course_id)).slice(0, 4);
  const item = goal.data!;
  const todayTasks = today.data?.tasks ?? [];
  const recentSession = today.data?.recent_session?.learning_goal_id === id
    ? today.data.recent_session
    : null;
  const recentCompleted = todayTasks.filter((task) => task.learning_goal_id === id && task.status === "completed").slice(0, 3);
  const openView = (view: GoalDetailView) => {
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set("view", view);
    setSearchParams(nextParams);
  };

  return <div className="page composition-page item-detail-page goal-workspace">
    <header className="goal-context-header">
      <div className="goal-context-header__identity"><div className="goal-title-line"><span className={`status status--${item.status}`}>{statusLabel[item.status] ?? item.status}</span><GoalActions goal={item} returnToPlanning/></div><h1>{item.title}</h1><p>{item.description || "尚未补充想达成的结果。"}</p></div>
      <aside className="goal-context-header__controls">
        <nav className="item-detail-tabs" aria-label={`${item.title} 视图`}>
          {goalDetailViews.map((view) => <button key={view.id} type="button" className={activeView === view.id ? "is-active" : ""} aria-current={activeView === view.id ? "page" : undefined} onClick={() => openView(view.id)}>{view.label}</button>)}
        </nav>
        <div className="goal-context-header__actions"><button className="button button--secondary" onClick={() => setMaterialOpen(true)}><FilePlus2 size={16}/>关联资料</button><Link className="button button--secondary" to={`/knowledge?tab=qa&scope=learning_goal&learning_goal_id=${id}`}><MessageSquareText size={16}/>基于资料提问</Link><Link className="goal-ai-action" to={`/ai?goal_id=${id}`}>AI 协作<ArrowRight size={15}/></Link></div>
      </aside>
      <dl className="item-facts"><div><dt>希望完成</dt><dd>{formatDate(item.target_date)}</dd></div><div><dt>每天投入</dt><dd>{item.daily_minutes} 分钟</dd></div><div><dt>当前基础</dt><dd>{item.current_level || "尚未填写"}</dd></div></dl>
    </header>

    <div className="item-detail-view" data-goal-view={activeView}>
    {activeView === "overview" && <section className="item-next-step" aria-labelledby="item-next-step-title">
      <div><span>下一步</span><h2 id="item-next-step-title">{action?.title ?? (currentStep?.title || "生成一条可执行路线")}</h2><p>{action?.reason ?? (currentStep ? "这是当前路线中等待继续的一步。" : "AI 会根据事项、时间和已关联资料给出可审查的路线建议。")}</p></div>
      {action?.cta_href ? <Link className="button button--primary" to={action.cta_href}>{action.cta_label}<ArrowRight size={16}/></Link> : currentStep ? <Link className="button button--primary" to={`/knowledge-points/${currentStep.id}`}>继续推进<ArrowRight size={16}/></Link> : <button className="button button--primary" disabled={generate.isPending} onClick={() => generate.mutate()}><Route size={16}/>{generate.isPending ? "正在准备" : "生成路线建议"}</button>}
    </section>}

    {activeView === "route" && <section className="item-section" aria-labelledby="item-route-title">
      <header className="section-heading"><div><h2 id="item-route-title">行动路线</h2><p>{relatedCourses.length ? "查看当前阶段和接下来可推进的步骤。" : "路线尚未建立；可以先关联资料，再生成建议。"}</p></div></header>
      {relatedCourses.length ? <div className="item-route-list">{relatedCourses.map((course, index) => {
        const steps = pointQueries[index]?.data ?? [];
        const next = steps.find((point) => point.status === "learning") ?? steps.find((point) => point.status === "not_started");
        return <article key={course.id}><div><span>{course.status === "active" ? "正在推进" : statusLabel[course.status] ?? course.status}</span><h3>{course.title}</h3></div><p>{next ? `当前阶段：${next.title}` : "这条路线当前没有待执行步骤。"}</p><ol>{steps.slice(0, 4).map((step) => <li key={step.id} className={step.id === next?.id ? "is-current" : ""}>{step.title}</li>)}</ol></article>;
      })}</div> : <div className="route-empty-state"><Route size={18}/><div><strong>还没有行动路线</strong><p>关联资料后再生成建议；这里不会用示例节点填满空间。</p></div>{!generate.isPending && <button className="text-button" onClick={() => generate.mutate()}>生成路线建议<ArrowRight size={14}/></button>}</div>}
    </section>}

    {activeView === "content" && <section className="item-section item-knowledge-summary" aria-labelledby="item-knowledge-title">
      <header className="section-heading"><div><h2 id="item-knowledge-title">关联内容</h2><p>资料和笔记为路线、提问与后续整理提供上下文。</p></div><Link className="text-link" to={`/knowledge?tab=notes&new=1&entity_type=learning_goal&entity_id=${id}`}>记录笔记</Link></header>
      <div className="item-knowledge-columns"><div className="item-material-context"><h3>关联资料</h3><EffectiveMaterials items={materials.data ?? []} emptyText="尚未关联资料。路线建议会明确标记为未核对。"/></div><div className="item-note-context"><h3>最近笔记</h3>{notes.data?.items?.length ? <ul>{notes.data.items.map((note) => <li key={note.id}><Link to={`/knowledge?tab=notes&note=${note.id}`}>{note.title}</Link><small>{formatDateTime(note.updated_at)}</small></li>)}</ul> : <p className="inline-empty">还没有与此事项关联的笔记。</p>}</div></div>
    </section>}

    {activeView === "feedback" && <section className="item-section item-feedback" aria-label="学习反馈">
      <div className="item-feedback-grid">
        <div className="item-feedback-surface item-feedback-surface--recent"><h3>最近练习</h3>{recentPractice.length ? recentPractice.map((practice) => <Link key={practice.id} to={`/activities/${practice.id}${quizOriginSearch({ kind: "goal", goalId: id })}`}><strong>{practice.title}</strong><small>{practice.completed_attempt_count} 次完成</small></Link>) : <p className="inline-empty">完成内容后的理解检查会出现在这里。</p>}</div>
        <div className="item-feedback-surface item-feedback-surface--strengthen"><h3>需要加强</h3>{strengthening.length ? strengthening.map((point) => <p key={point.knowledge_point_id}>{point.knowledge_point_title}</p>) : activeWrong.length ? <p>{activeWrong.length} 道练习题值得回看</p> : <p className="inline-empty">当前没有明显需要加强的内容。</p>}</div>
        <div className="item-feedback-surface item-feedback-surface--steady"><h3>做得不错</h3>{doingWell.length ? doingWell.map((point) => <p key={point.knowledge_point_id}>{point.knowledge_point_title}</p>) : <p className="inline-empty">继续练习后，这里会记录已经稳定的内容。</p>}</div>
        <div className="item-feedback-surface item-feedback-surface--review"><h3>待复习</h3>{dueReviews.length ? dueReviews.map((point) => <p key={point.id}>{point.title}</p>) : <p className="inline-empty">当前没有到期复习。</p>}</div>
      </div>
    </section>}

    {activeView === "history" && <section className="item-section item-review" aria-labelledby="item-review-title">
      <header className="section-heading"><div><h2 id="item-review-title">回顾</h2><p>关注最近推进、发生的变化，以及值得记录的想法。</p></div><Link className="text-link" to={`/knowledge?tab=notes&new=1&note_type=reflection&entity_type=learning_goal&entity_id=${id}`}>记录一次回顾</Link></header>
      <div className="item-review-ledger"><div className="item-review-primary"><h3>最近推进</h3>{recentSession && <p>{formatDateTime(recentSession.started_at)} 开始了一次推进</p>}{recentCompleted.map((task) => <p key={task.id}>已完成：{task.title}</p>)}{!recentSession && !recentCompleted.length && <p className="inline-empty">还没有新的推进记录。</p>}</div><div><h3>有什么变化</h3><p>{strengthening.length ? `发现 ${strengthening.length} 处需要加强的内容。` : doingWell.length ? `${doingWell.length} 个步骤已经比较稳定。` : "完成练习后，这里会汇总真实变化。"}</p></div><div><h3>AI 建议</h3><p>{action?.reason ?? "当前没有等待处理的建议。"}</p>{action?.action_type === "review_proposal" && <Link className="text-link" to={action.cta_href}>查看调整建议</Link>}</div></div>
    </section>}
    </div>

    <details className="item-advanced"><summary>更多 · 高级功能</summary><p>保留手动路线编辑、结构历史、完整安排、判断依据和练习编辑能力，默认不进入主流程。</p><div className="button-row"><Link className="button button--secondary" to="/courses">高级路线编辑</Link><Link className="button button--secondary" to="/course-architecture/drafts">路线草案与历史</Link><Link className="button button--secondary" to="/items?advanced=planning">完整安排设置</Link><Link className="button button--secondary" to="/review?tab=mastery">查看判断依据</Link><Link className="button button--secondary" to="/activities">练习编辑</Link><Link className="button button--secondary" to="/growth">完整回顾</Link></div></details>
    <TargetMaterialPicker open={materialOpen} targetType="learning_goal" targetId={id} targetTitle={item.title} onClose={() => setMaterialOpen(false)}/>
  </div>;
}
