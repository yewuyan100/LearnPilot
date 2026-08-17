import { useQueries, useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  BarChart3,
  BookOpenText,
  CheckCircle2,
  Clock3,
  FileText,
  Flag,
  FolderKanban,
  Lightbulb,
  ListTodo,
  NotebookPen,
  Play,
  Sparkles,
  Target,
} from "lucide-react";
import { type CSSProperties, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { adaptiveApi, coursesApi, dashboardApi, goalsApi, materialsApi, nextActionApi, notesApi } from "../api/resources";
import { Dialog } from "../components/Dialog";
import { GoalForm } from "../components/GoalForm";
import { ErrorState, LoadingState } from "../components/States";
import type { Course, KnowledgePoint } from "../types";
import { formatDateTime } from "../utils/format";

function firstAvailablePoint(points: KnowledgePoint[] | undefined, preferredId?: number | null) {
  if (!points?.length) return undefined;
  return points.find((point) => point.id === preferredId)
    ?? points.find((point) => point.status === "learning")
    ?? points.find((point) => point.status === "not_started");
}

function uniqueCourses(courses: Course[], preferredIds: Array<number | null | undefined>, limit: number) {
  const byId = new Map(courses.map((course) => [course.id, course]));
  const result: Course[] = [];
  const seen = new Set<number>();

  for (const id of preferredIds) {
    const course = id ? byId.get(id) : undefined;
    if (course && !seen.has(course.id)) {
      result.push(course);
      seen.add(course.id);
    }
  }

  for (const course of courses) {
    if (!seen.has(course.id)) {
      result.push(course);
      seen.add(course.id);
    }
  }

  return result.slice(0, limit);
}

function LearningPathIllustration() {
  return <svg className="learning-path-illustration" viewBox="0 0 260 190" aria-hidden="true">
    <defs>
      <linearGradient id="path-layer-a" x1="0" x2="1" y1="0" y2="1">
        <stop offset="0" stopColor="var(--color-path-layer-a)" />
        <stop offset="1" stopColor="var(--color-path-layer-b)" />
      </linearGradient>
      <linearGradient id="path-layer-b" x1="0" x2="1" y1="0" y2="1">
        <stop offset="0" stopColor="var(--color-path-layer-c)" />
        <stop offset="1" stopColor="var(--color-path-layer-d)" />
      </linearGradient>
    </defs>
    <path className="learning-path-illustration__shadow" d="M36 148 119 100l106 42-83 48Z" />
    <path fill="url(#path-layer-b)" d="M36 134 119 86l106 42-83 48Z" />
    <path className="learning-path-illustration__edge" d="m36 134 106 42 83-48v13l-83 48-106-42Z" />
    <path fill="url(#path-layer-a)" d="M36 100 119 52l106 42-83 48Z" />
    <path className="learning-path-illustration__edge learning-path-illustration__edge--middle" d="m36 100 106 42 83-48v13l-83 48-106-42Z" />
    <path fill="url(#path-layer-b)" d="M36 66 119 18l106 42-83 48Z" />
    <path className="learning-path-illustration__edge" d="m36 66 106 42 83-48v13l-83 48-106-42Z" />
    <path className="learning-path-illustration__route" d="M87 91c13 8 25 2 35 10 11 9 1 19 14 27 10 6 20 1 30 8" />
    <path className="learning-path-illustration__route" d="M119 51v35" />
    <circle className="learning-path-illustration__point" cx="119" cy="51" r="4" />
    <circle className="learning-path-illustration__point" cx="87" cy="91" r="4" />
    <circle className="learning-path-illustration__point" cx="166" cy="136" r="4" />
    <path className="learning-path-illustration__flag" d="M119 51V24l28 8-28 10" />
  </svg>;
}

type WorkspaceStep = { id: string; title: string; meta: string; href: string };
type WorkspaceEvent = { id: string; title: string; source: string; time: string; icon: "session" | "task" };

export function DashboardPage() {
  const [createOpen, setCreateOpen] = useState(false);
  const navigate = useNavigate();
  const today = useQuery({ queryKey: ["today"], queryFn: dashboardApi.today });
  const courses = useQuery({ queryKey: ["courses"], queryFn: coursesApi.list });
  const nextAction = useQuery({
    queryKey: ["next-learning-action", "workspace"],
    queryFn: () => nextActionApi.get(),
    enabled: today.isSuccess && courses.isSuccess && Boolean(today.data?.current_goal) && Boolean(courses.data?.length),
    retry: false,
  });
  const reviews = useQuery({
    queryKey: ["adaptive-reviews"],
    queryFn: adaptiveApi.reviews,
    retry: false,
  });
  const progress = useQuery({ queryKey: ["progress"], queryFn: dashboardApi.progress, retry: false });
  const goals = useQuery({ queryKey: ["goals"], queryFn: goalsApi.list, retry: false });
  const materials = useQuery({ queryKey: ["materials", "", ""], queryFn: () => materialsApi.list(), retry: false });
  const notes = useQuery({ queryKey: ["notes", "workspace-summary"], queryFn: () => notesApi.list({ pageSize: 100 }), retry: false });
  const recommendations = useQuery({
    queryKey: ["adaptive-recommendations", "pending"],
    queryFn: () => adaptiveApi.recommendations("pending"),
    retry: false,
  });

  const courseItems = courses.data ?? [];
  const nextTask = today.data?.tasks.find((task) => task.status !== "completed");
  const activeCourses = courseItems.filter((course) => course.status === "active");
  const pointCourses = uniqueCourses(
    [...activeCourses, ...courseItems.filter((course) => course.status !== "active")],
    [
      nextAction.data?.course_id,
      nextTask?.course_id,
      today.data?.recent_course?.id,
    ],
    4,
  );
  const pointQueries = useQueries({
    queries: pointCourses.map((course) => ({
      queryKey: ["course-points", course.id],
      queryFn: () => coursesApi.points(course.id),
      staleTime: 30_000,
    })),
  });

  if (today.isLoading || courses.isLoading) {
    return <LoadingState label="正在读取工作台状态" />;
  }

  if (today.isError || courses.isError) {
    const error = today.error ?? courses.error;
    return <ErrorState message={(error as Error).message} onRetry={() => {
      void today.refetch();
      void courses.refetch();
    }} />;
  }

  const data = today.data!;
  const action = nextAction.data;
  const pointsByCourse = new Map<number, KnowledgePoint[]>();
  pointCourses.forEach((course, index) => {
    const points = pointQueries[index]?.data;
    if (points) pointsByCourse.set(course.id, points);
  });

  const currentCourse = courseItems.find((course) => course.id === action?.course_id)
    ?? courseItems.find((course) => course.id === nextTask?.course_id)
    ?? courseItems.find((course) => course.id === data.recent_course?.id)
    ?? activeCourses[0]
    ?? courseItems[0];
  const currentCoursePoints = currentCourse ? pointsByCourse.get(currentCourse.id) : undefined;
  const currentPoint = firstAvailablePoint(
    currentCoursePoints,
    action?.knowledge_point_id ?? nextTask?.knowledge_point_id,
  );
  const currentPointQueryIndex = currentCourse
    ? pointCourses.findIndex((course) => course.id === currentCourse.id)
    : -1;
  const currentPointQuery = currentPointQueryIndex >= 0 ? pointQueries[currentPointQueryIndex] : undefined;
  const actionIsExecutable = Boolean(action?.cta_href);
  const hasExecutableNextStep = actionIsExecutable || Boolean(nextTask) || Boolean(currentPoint);
  const hasProject = courseItems.length > 0;
  const hasGoal = Boolean(data.current_goal);
  const mainIsResolving = hasProject
    && hasGoal
    && (nextAction.isLoading || Boolean(currentCourse && currentPointQuery?.isLoading));

  const currentPointTitle = action?.knowledge_point_title ?? currentPoint?.title;
  const estimatedMinutes = action?.estimated_minutes
    || nextTask?.estimated_minutes
    || currentPoint?.estimated_minutes
    || 0;
  const projectPointTotal = currentCoursePoints?.length ?? 0;

  let mainTitle = "创建你的第一个事项";
  let mainDescription = "告诉系统你想推进什么，创建后会直接进入事项并生成下一步建议。";
  let primaryLabel = "创建事项";
  let primaryHref = "";
  let PrimaryIcon = Flag;

  if (hasGoal && !hasProject) {
    mainTitle = `为「${data.current_goal!.title}」准备行动路线`;
    mainDescription = "事项已经建立。下一步可以补充资料，或让 AI 提出一条可审查的推进路线。";
    primaryLabel = "打开事项";
    primaryHref = `/items/${data.current_goal!.id}`;
  } else if (hasProject && hasGoal && mainIsResolving) {
    mainTitle = "正在读取下一步";
    mainDescription = "正在核对当前事项、行动路线和已安排内容。";
    primaryLabel = "";
    primaryHref = "";
  } else if (hasProject && hasGoal && hasExecutableNextStep) {
    mainTitle = currentPointTitle ?? nextTask?.title ?? action?.title ?? "继续当前学习";
    mainDescription = actionIsExecutable && action?.reason
      ? action.reason
      : nextTask
        ? "这是今天排在最前的未完成任务。"
        : "这是当前行动路线中尚未完成的一步。";
    primaryLabel = action?.cta_label || "继续推进";
    primaryHref = actionIsExecutable
      ? action!.cta_href
      : currentPoint
        ? "/knowledge-points/" + currentPoint.id
        : "/today";
    PrimaryIcon = Play;
  } else if (hasProject && hasGoal) {
    mainTitle = `为「${data.current_goal!.title}」选择下一步`;
    mainDescription = action?.reason || "当前没有可直接执行的步骤，请回到事项核对路线或调整安排。";
    primaryLabel = "查看事项";
    primaryHref = `/items/${data.current_goal!.id}`;
    PrimaryIcon = Flag;
  }

  const dueReviews = (reviews.data ?? []).filter((review) => {
    if (review.status !== "pending" && review.status !== "scheduled") return false;
    return review.overdue || review.due_at.slice(0, 10) <= data.date;
  });
  const completedTasks = data.tasks.filter((task) => task.status === "completed").length;
  const incompleteTasks = data.tasks.filter((task) => task.status !== "completed");
  const pointById = new Map<number, KnowledgePoint>();
  pointsByCourse.forEach((points) => {
    points.forEach((point) => pointById.set(point.id, point));
  });

  const completedPoints = currentCoursePoints?.filter((point) => point.status === "completed").length ?? 0;
  const focusProgress = projectPointTotal > 0
    ? Math.round((completedPoints / projectPointTotal) * 100)
    : data.tasks.length > 0
      ? Math.round((completedTasks / data.tasks.length) * 100)
      : 0;

  const nextSteps: WorkspaceStep[] = incompleteTasks.slice(0, 3).map((task) => ({
    id: `task-${task.id}`,
    title: task.title,
    meta: `${pointById.get(task.knowledge_point_id ?? -1)?.title ?? (task.task_type === "review" ? "复习" : "学习计划")} · ${task.estimated_minutes} 分钟`,
    href: "/today",
  }));
  if (nextSteps.length < 3 && currentCoursePoints) {
    for (const point of currentCoursePoints) {
      if (nextSteps.length >= 3) break;
      if (point.status === "completed" || point.id === currentPoint?.id) continue;
      nextSteps.push({ id: `point-${point.id}`, title: point.title, meta: `学习路径 · ${point.estimated_minutes} 分钟`, href: `/knowledge-points/${point.id}` });
    }
  }
  if (!nextSteps.length && action?.title && action.cta_href) {
    nextSteps.push({ id: "next-action", title: action.title, meta: action.reason || "来自当前学习状态", href: action.cta_href });
  }

  const pendingItems = [
    ...dueReviews.map((review) => ({
      id: `review-${review.id}`,
      title: review.knowledge_point_title,
      source: "复习计划",
      time: review.overdue ? "已到期" : formatDateTime(review.due_at),
      status: review.overdue ? "高优先级" : "待复习",
      href: "/review?tab=review",
    })),
    ...(recommendations.data ?? []).map((item) => ({
      id: `recommendation-${item.id}`,
      title: item.title,
      source: "AI 建议",
      time: formatDateTime(item.suggested_date),
      status: item.priority === "high" ? "高优先级" : "待确认",
      href: "/review?tab=plan",
    })),
    ...data.tasks.filter((task) => task.status === "blocked").map((task) => ({
      id: `blocked-${task.id}`,
      title: task.title,
      source: "学习计划",
      time: formatDateTime(task.updated_at),
      status: "受阻",
      href: "/today",
    })),
  ].slice(0, 3);

  const recentEvents: WorkspaceEvent[] = [];
  const seenSessions = new Set<number>();
  if (data.recent_session) {
    seenSessions.add(data.recent_session.id);
    recentEvents.push({ id: `session-${data.recent_session.id}`, title: "完成一次学习推进", source: "学习记录", time: data.recent_session.started_at, icon: "session" });
  }
  for (const session of progress.data?.recent_sessions ?? []) {
    if (seenSessions.has(session.id)) continue;
    seenSessions.add(session.id);
    recentEvents.push({ id: `session-${session.id}`, title: "完成一次学习推进", source: "学习记录", time: session.started_at, icon: "session" });
  }
  for (const task of data.tasks.filter((item) => item.status === "completed")) {
    recentEvents.push({ id: `completed-${task.id}`, title: task.title, source: "已完成", time: task.updated_at, icon: "task" });
  }
  recentEvents.sort((a, b) => b.time.localeCompare(a.time));

  const activeGoalCount = goals.isLoading || goals.isError ? null : (goals.data ?? []).filter((goal) => goal.status === "active").length;
  const materialCount = materials.isLoading || materials.isError ? null : (materials.data ?? []).filter((item) => !item.archived_at).length;
  const noteCount = notes.isLoading || notes.isError ? null : (notes.data?.total ?? 0);
  const knowledgeCount = materialCount === null || noteCount === null ? null : materialCount + noteCount;
  const unorganizedCount = materials.isLoading || materials.isError ? null : (materials.data ?? []).filter((item) =>
    !item.archived_at && (item.ingestion_status !== "completed" || item.indexing_status !== "completed")
  ).length;
  const recommendationCount = recommendations.isError ? 0 : (recommendations.data?.length ?? 0);
  const pendingCount = reviews.isLoading || recommendations.isLoading || reviews.isError || recommendations.isError ? null : data.pending_count + dueReviews.length + recommendationCount;
  const weeklySessions = progress.isLoading || progress.isError ? null : (progress.data?.sessions_last_7_days ?? 0);

  const sessionMap = new Map((progress.data?.daily_sessions ?? []).map((item) => [item.date, item.count]));
  const chartDays = Array.from({ length: 7 }, (_, index) => {
    const day = new Date();
    day.setHours(12, 0, 0, 0);
    day.setDate(day.getDate() - (6 - index));
    const key = `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, "0")}-${String(day.getDate()).padStart(2, "0")}`;
    return { key, label: new Intl.DateTimeFormat("zh-CN", { weekday: "short" }).format(day), count: sessionMap.get(key) ?? 0 };
  });
  const totalActivity = chartDays.reduce((total, day) => total + day.count, 0);
  const chartMax = Math.max(1, ...chartDays.map((item) => item.count));
  const aiSuggestion = recommendations.data?.[0];
  const pendingIsEmpty = pendingCount === 0 && pendingItems.length === 0;
  const recentProgressIsEmpty = recentEvents.length === 0;
  const learningInsightIsCompact = progress.isLoading || progress.isError || totalActivity === 0;
  const aiSuggestionIsEmpty = !aiSuggestion && !action;

  const summaryCards = [
    { key: "goals", label: "进行中的目标", value: activeGoalCount, unit: "个", meta: activeGoalCount ? "目标正在推进中" : "暂无进行中的目标", icon: Target },
    { key: "knowledge", label: "知识库条目", value: knowledgeCount, unit: "条", meta: knowledgeCount === null ? "暂时无法加载" : `资料 ${materialCount ?? 0} · 笔记 ${noteCount ?? 0}`, icon: BookOpenText },
    { key: "pending", label: "待处理事项", value: pendingCount, unit: "项", meta: pendingCount ? "需要查看或确认" : "当前没有待处理内容", icon: ListTodo },
    { key: "sessions", label: "本周学习记录", value: weeklySessions, unit: "次", meta: "最近 7 天真实学习会话", icon: BarChart3 },
  ] as const;

  return <div className="page dashboard-page learnpilot-workbench">
    <h1 className="sr-only">工作台</h1>
    <div className="workbench-grid">
      <div className="workbench-main">
        <section className="summary-grid" aria-label="学习概览">
          {summaryCards.map(({ key, label, value, unit, meta, icon: Icon }) => <article className={`summary-card summary-card--${key}`} key={key}>
            <div className="summary-card__icon"><Icon size={20} /></div>
            <div className="summary-card__body"><span>{label}</span><strong>{value === null ? "—" : value}<small>{unit}</small></strong><p>{meta}</p></div>
          </article>)}
        </section>

        <section className="workbench-main-grid">
          <article className="focus-panel workbench-panel" aria-labelledby="current-focus-title" aria-busy={mainIsResolving}>
            <header className="panel-heading"><div><Target size={18} /><h2 id="current-focus-title">当前重点</h2></div>{hasGoal && <Link to={`/items/${data.current_goal!.id}`}>查看全部 <ArrowRight size={14} /></Link>}</header>
            <div className="focus-panel__body">
              <div className="focus-panel__content">
                <span className="focus-status">{hasGoal ? "进行中" : "开始使用"}</span>
                <h3>{mainTitle}</h3>
                <p>{mainDescription}</p>
                <div className="focus-progress"><div><span>整体进度</span><strong>{focusProgress}%</strong></div><progress max="100" value={focusProgress}>{focusProgress}%</progress></div>
                <div className="focus-meta">
                  {data.current_goal?.target_date && <span><Clock3 size={14} />预计 {new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric" }).format(new Date(`${data.current_goal.target_date}T12:00:00`))} 完成</span>}
                  {action?.priority && <span><Flag size={14} />优先级 {action.priority}</span>}
                  {estimatedMinutes > 0 && <span><Clock3 size={14} />约 {estimatedMinutes} 分钟</span>}
                </div>
                {primaryLabel && (!hasGoal ? <button className="button button--primary focus-primary-action" onClick={() => setCreateOpen(true)}><PrimaryIcon size={16} />{primaryLabel}</button> : <Link className="button button--primary focus-primary-action" to={primaryHref}><PrimaryIcon size={16} />{primaryLabel}</Link>)}
              </div>
              <LearningPathIllustration />
            </div>
          </article>

          <section className="next-steps-panel workbench-panel" aria-labelledby="next-steps-title">
            <header className="panel-heading"><div><Clock3 size={18} /><h2 id="next-steps-title">下一步</h2></div></header>
            {nextSteps.length ? <ol className="next-steps-list">{nextSteps.map((step, index) => <li key={step.id}><span>{index + 1}</span><Link to={step.href}><strong>{step.title}</strong><small>{step.meta}</small></Link></li>)}</ol> : <p className="panel-empty">当前没有排在后面的行动。</p>}
            <Link className="panel-action" to="/items">查看全部计划 <ArrowRight size={14} /></Link>
          </section>

          <section id="pending" className={`pending-panel workbench-panel${pendingIsEmpty ? " pending-panel--empty" : ""}`} aria-labelledby="pending-title">
            <header className="panel-heading"><div><ListTodo size={18} /><h2 id="pending-title">待处理</h2></div><Link to="/review?tab=review">查看全部 <ArrowRight size={14} /></Link></header>
            {pendingItems.length ? <div className="pending-list">{pendingItems.map((item) => <Link to={item.href} key={item.id}><span className="pending-check" aria-hidden="true" /><span><strong>{item.title}</strong><small>{item.source}</small></span><time>{item.time}</time><em>{item.status}</em></Link>)}</div> : pendingIsEmpty ? <div className="compact-empty-state"><CheckCircle2 size={18} aria-hidden="true" /><span><strong>当前没有需要你处理的内容</strong><small>新的建议或确认项会出现在这里</small></span></div> : <p className="panel-empty">待处理内容正在同步。</p>}
          </section>

          <section className={`recent-progress-panel workbench-panel${recentProgressIsEmpty ? " recent-progress-panel--empty" : ""}`} aria-labelledby="recent-progress-title">
            <header className="panel-heading"><div><BarChart3 size={18} /><h2 id="recent-progress-title">最近进展</h2></div>{hasGoal && <Link to={`/items/${data.current_goal!.id}`}>查看所有记录 <ArrowRight size={14} /></Link>}</header>
            {recentEvents.length ? <div className="progress-event-list">{recentEvents.slice(0, 3).map((event) => <div key={event.id}>{event.icon === "task" ? <CheckCircle2 size={16} /> : <FileText size={16} />}<span><strong>{event.title}</strong><small>{event.source}</small></span><time>{formatDateTime(event.time)}</time></div>)}</div> : <div className="compact-empty-state"><BarChart3 size={18} aria-hidden="true" /><span><strong>还没有最近进展</strong><small>完成一次学习后，真实记录会出现在这里</small></span></div>}
          </section>
        </section>
      </div>

      <aside className="insight-rail" aria-label="学习洞察">
        <section className={`insight-card learning-insight-card${learningInsightIsCompact ? " learning-insight-card--compact" : ""}`} aria-labelledby="learning-insight-title">
          <header className="panel-heading"><div><Sparkles size={18} /><h2 id="learning-insight-title">学习洞察</h2></div></header>
          <div className="insight-card__subhead"><strong>学习活动</strong><span>过去 7 天</span></div>
          {progress.isLoading ? <p className="panel-empty">正在读取活动记录。</p> : progress.isError ? <p className="panel-empty">暂时无法加载活动记录。</p> : totalActivity === 0 ? <div className="activity-empty-state"><div className="activity-empty-state__baseline" aria-hidden="true" /><strong>还没有形成学习趋势</strong><p>完成一次学习后，这里会展示你的近 7 天活动变化。</p></div> : <><div className="activity-chart" aria-label={`过去 7 天共有 ${totalActivity} 次学习会话`}>{chartDays.map((day) => <div key={day.key}><span className="activity-chart__track"><i style={{ "--bar-scale": day.count / chartMax } as CSSProperties} /></span><small>{day.label}</small></div>)}</div><p className="insight-note"><Lightbulb size={17} /><span><strong>保持当前节奏</strong>过去 7 天已记录 {totalActivity} 次学习会话。</span></p></>}
        </section>

        <section className="insight-card knowledge-stats-card" aria-labelledby="knowledge-stats-title">
          <header className="panel-heading"><div><FolderKanban size={18} /><h2 id="knowledge-stats-title">知识库统计</h2></div></header>
          <dl><div><dt><FileText size={15} />资料</dt><dd>{materialCount ?? "—"}</dd></div><div><dt><NotebookPen size={15} />笔记</dt><dd>{noteCount ?? "—"}</dd></div><div><dt><ListTodo size={15} />待整理</dt><dd>{unorganizedCount ?? "—"}</dd></div></dl>
        </section>

        <section className={`insight-card ai-suggestion-card${aiSuggestionIsEmpty ? " ai-suggestion-card--empty" : ""}`} aria-labelledby="ai-suggestion-title">
          <header className="panel-heading"><div><Sparkles size={18} /><h2 id="ai-suggestion-title">AI 助手建议</h2></div></header>
          {aiSuggestion ? <><p>{aiSuggestion.title}</p><small>基于当前待确认建议</small></> : action ? <><p>{action.reason || action.title}</p><small>基于当前下一步</small></> : <div className="compact-empty-state"><Sparkles size={18} aria-hidden="true" /><span><strong>当前没有可解释的 AI 建议</strong><small>新的真实建议可用时，会出现在这里</small></span></div>}
          <Link className="ai-suggestion-action" to="/ai">向 AI 提问 <ArrowRight size={15} /></Link>
        </section>
      </aside>
    </div>

    <Dialog open={createOpen} title="创建事项" onClose={() => setCreateOpen(false)}>
      <GoalForm
        onCancel={() => setCreateOpen(false)}
        onCreated={(goal) => {
          setCreateOpen(false);
          navigate(`/items/${goal.id}`);
        }}
      />
    </Dialog>
  </div>;
}
