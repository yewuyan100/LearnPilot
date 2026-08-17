import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CalendarDays, Flag, Plus } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { adaptiveApi, coursesApi, dashboardApi, goalsApi, nextActionApi } from "../api/resources";
import { Dialog } from "../components/Dialog";
import { GoalForm } from "../components/GoalForm";
import { GoalActions } from "../components/GoalActions";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { StudyPlanPanel } from "../components/StudyPlanPanel";
import { DashboardCard, SectionHeader } from "../components/Workspace";
import { formatDate, formatDateTime, statusLabel } from "../utils/format";

export function GoalsPage() {
  const [createOpen, setCreateOpen] = useState(false);
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const showPlanningTools = searchParams.get("advanced") === "planning";
  const goals = useQuery({ queryKey: ["goals"], queryFn: goalsApi.list });
  const courses = useQuery({ queryKey: ["courses"], queryFn: coursesApi.list });
  const today = useQuery({ queryKey: ["today"], queryFn: dashboardApi.today });
  const nextAction = useQuery({
    queryKey: ["next-learning-action", "items"],
    queryFn: () => nextActionApi.get(),
    enabled: today.isSuccess && Boolean(today.data?.current_goal),
    retry: false,
  });
  if (goals.isLoading || courses.isLoading || today.isLoading) return <LoadingState label="正在读取事项" />;
  if (goals.isError || courses.isError || today.isError) return <ErrorState message={((goals.error ?? courses.error ?? today.error) as Error).message} onRetry={() => void goals.refetch()} />;
  const goalItems = (goals.data ?? []).filter((goal) => goal.status === "active");
  const focusedGoal = goalItems[0];
  const supportingGoals = goalItems.slice(1);
  const getSignals = (goal: (typeof goalItems)[number]) => {
    const hasRoute = courses.data?.some((course) => course.learning_goal_id === goal.id) ?? false;
    const action = nextAction.data?.learning_goal_id === goal.id ? nextAction.data : null;
    return {
      action,
      next: action?.title ?? (hasRoute ? "继续推进已有路线" : "生成一条可执行路线"),
      pendingSuggestion: action?.action_type === "review_proposal" || action?.action_type === "replan_required",
    };
  };
  const focusedSignals = focusedGoal ? getSignals(focusedGoal) : null;
  return <div className="page composition-page items-page planning-portfolio">
    <header className="planning-portfolio__status" aria-label="规划状态和操作">
      <p><strong>进行中</strong><span>· {goalItems.length}</span></p>
      <button className="button button--primary" onClick={() => setCreateOpen(true)}><Plus size={16} />创建事项</button>
    </header>
    {!goalItems.length ? <EmptyState title="还没有事项" description="从一件你真正想推进的事开始。" action={<button className="button button--primary" onClick={() => setCreateOpen(true)}>创建事项</button>} /> : <section className="planning-portfolio__stage" aria-label="当前推进事项">
      {focusedGoal && focusedSignals && <article className="planning-focus">
        <GoalActions goal={focusedGoal}/>
        <div className="planning-focus__identity"><span className={`status status--${focusedGoal.status}`}>{statusLabel[focusedGoal.status] ?? focusedGoal.status}</span><h2><Link to={`/items/${focusedGoal.id}`}>{focusedGoal.title}</Link></h2><p>{focusedGoal.description || "尚未补充想达成的结果。"}</p></div>
        <div className="planning-focus__next"><span>下一步</span><strong>{focusedSignals.next}</strong><p>{focusedSignals.action?.reason ?? "沿着当前状态继续推进；打开事项可查看完整上下文。"}</p></div>
        <dl className="planning-focus__signals"><div><dt>最近变化</dt><dd>{formatDateTime(focusedGoal.updated_at)}</dd></div><div><dt>AI 建议</dt><dd>{focusedSignals.pendingSuggestion ? "有一条建议待你处理" : "暂无待处理建议"}</dd></div></dl>
        <Link className="planning-focus__open" to={`/items/${focusedGoal.id}`}>进入事项<ArrowRight size={15}/></Link>
      </article>}
      <aside className="planning-ledger" aria-label="其余推进事项">
        <header><h2>其余事项</h2><span>{supportingGoals.length} 项</span></header>
        {supportingGoals.length ? supportingGoals.map((goal) => {
          const signals = getSignals(goal);
          return <article className="planning-ledger__item" key={goal.id}>
            <GoalActions goal={goal}/>
            <div><span className={`status status--${goal.status}`}>{statusLabel[goal.status] ?? goal.status}</span><h3><Link to={`/items/${goal.id}`}>{goal.title}</Link></h3><p>{goal.description || "尚未补充想达成的结果。"}</p></div>
            <dl><div><dt>下一步</dt><dd>{signals.next}</dd></div><div><dt>最近变化</dt><dd>{formatDateTime(goal.updated_at)}</dd></div></dl>
            <Link className="planning-ledger__open" to={`/items/${goal.id}`} aria-label={`打开${goal.title}`}><ArrowRight size={16}/></Link>
          </article>;
        }) : <p className="inline-empty">暂时没有其他推进事项。</p>}
      </aside>
    </section>}
    {showPlanningTools ? <section className="items-advanced" aria-labelledby="items-advanced-title">
      <header><p className="page-kicker">高级功能</p><h2 id="items-advanced-title">计划工具</h2><p>为需要精细控制时间安排的用户保留。日常推进无需使用这里。</p></header>
      <StudyPlanPanel goals={goals.data ?? []} courses={courses.data ?? []} />
      <Link className="text-link" to="/items">收起高级功能</Link>
    </section> : <details className="items-more"><summary>更多</summary><p>需要手动安排时间时，可以打开高级计划工具。</p><Link className="text-link" to="/items?advanced=planning">打开计划工具</Link></details>}
    <Dialog open={createOpen} title="创建事项" onClose={() => setCreateOpen(false)}><GoalForm onCancel={() => setCreateOpen(false)} onCreated={(goal) => { setCreateOpen(false); navigate(`/items/${goal.id}`); }} /></Dialog>
  </div>;
}

export function CalendarPage() {
  const today = useQuery({ queryKey: ["today"], queryFn: dashboardApi.today });
  const reviews = useQuery({ queryKey: ["adaptive-reviews"], queryFn: adaptiveApi.reviews });
  if (today.isLoading || reviews.isLoading) return <LoadingState label="正在汇总近期安排" />;
  if (today.isError || reviews.isError) return <ErrorState message={((today.error ?? reviews.error) as Error).message} onRetry={() => void today.refetch()} />;
  const scheduled = (reviews.data ?? []).filter((review) => review.status === "pending" || review.status === "scheduled");
  return <div className="page"><header className="page-header"><p className="page-kicker">总览与计划</p><h1>日历</h1><p>展示当前接口可提供的今日任务与已安排复习，不生成不存在的日程。</p></header><section className="dashboard-grid dashboard-grid--primary"><DashboardCard title="今天" meta={formatDate(today.data!.date)}><div className="workspace-list">{today.data!.tasks.length ? today.data!.tasks.map((task) => <Link className="workspace-row" to="/today" key={task.id}><CalendarDays size={16}/><div><strong>{task.title}</strong><small>{task.estimated_minutes} 分钟 · {statusLabel[task.status] ?? task.status}</small></div></Link>) : <div className="inline-empty">今天尚无学习任务。</div>}</div></DashboardCard><DashboardCard title="已安排的复习" meta="依据现有复习日期排序"><div className="workspace-list">{scheduled.length ? scheduled.sort((a, b) => a.due_at.localeCompare(b.due_at)).map((review) => <Link className="workspace-row" to="/reviews" key={review.id}><Flag size={16}/><div><strong>{review.knowledge_point_title}</strong><small>{formatDate(review.due_at)} · {review.reason_summary}</small></div></Link>) : <div className="inline-empty">暂无已安排复习。</div>}</div></DashboardCard></section></div>;
}

export function ReflectionPage() {
  const progress = useQuery({ queryKey: ["progress"], queryFn: dashboardApi.progress });
  if (progress.isLoading) return <LoadingState label="正在读取今天的学习记录" />;
  if (progress.isError) return <ErrorState message={progress.error.message} onRetry={() => void progress.refetch()} />;
  return <div className="page"><header className="page-header"><p className="page-kicker">复盘</p><h1>今日复盘</h1><p>查看已有学习记录，带着真实情况决定下一步。</p></header><DashboardCard title="今天的可用记录" meta="不会自动生成或保存复盘内容"><div className="reflection-guide"><p>近七天已有 <strong>{progress.data!.sessions_last_7_days}</strong> 次学习会话。你可以回到今日学习完成任务，或到复习计划处理需要巩固的知识点。</p><div className="button-row"><Link className="button button--primary" to="/today">查看今日学习</Link><Link className="button button--secondary" to="/reviews">查看复习计划</Link></div></div></DashboardCard></div>;
}

export function SummaryPage() {
  const progress = useQuery({ queryKey: ["progress"], queryFn: dashboardApi.progress });
  if (progress.isLoading) return <LoadingState label="正在汇总学习进度" />;
  if (progress.isError) return <ErrorState message={progress.error.message} onRetry={() => void progress.refetch()} />;
  const data = progress.data!;
  return <div className="page"><header className="page-header"><p className="page-kicker">复盘</p><h1>周月总结</h1><p>基于已有任务、课程和学习会话展示当前概览；暂不虚构自动总结。</p></header><section className="dashboard-snapshot"><article><span>学习目标</span><strong>{data.goal_count}</strong><small>当前记录</small></article><article><span>进行中课程</span><strong>{data.active_course_count}</strong><small>来自课程数据</small></article><article><span>已完成知识点</span><strong>{data.completed_knowledge_point_count}</strong><small>共 {data.knowledge_point_count} 个</small></article><article><span>本周会话</span><strong>{data.sessions_last_7_days}</strong><small>最近七天</small></article></section><SectionHeader title="下一步" description="在成长进度中查看原始时间序列与最近学习记录。" action={<Link className="button button--secondary" to="/progress">打开成长进度</Link>} /></div>;
}
