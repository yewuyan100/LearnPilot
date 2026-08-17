import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CalendarDays, CheckCircle2, Clock3, History, RefreshCw, Send } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { studyPlansApi } from "../api/resources";
import type { Course, LearningGoal, StudyPlan, StudyPlanItem } from "../types";
import { Dialog } from "./Dialog";
import { ErrorState, LoadingState } from "./States";
import { useToast } from "./toast-context";
import { formatDate, formatDateTime, statusLabel } from "../utils/format";

const weekdayLabels = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];
const activityLabel: Record<string, string> = {
  learn: "学习",
  learning: "学习",
  practice: "练习",
  review: "复习",
  quick_verify: "快速验证",
};
const conflictLabel: Record<string, string> = {
  no_available_dates: "日期范围内没有可学习日",
  total_time_insufficient: "总学习时间不足",
  existing_task_on_unavailable_date: "现有任务落在不可学习日期",
  existing_tasks_over_capacity: "现有任务已经占满部分日期",
  daily_capacity_exhausted: "每日时间预算不足",
  prerequisite_order_violation: "现有任务与课程前置顺序冲突",
  unavailable_date_violation: "计划包含不可学习日期",
  duplicate_plan_items: "计划包含重复任务",
  knowledge_coverage_incomplete: "计划未覆盖全部必修知识点",
};
const suggestionLabel: Record<string, string> = {
  extend_target_date: "延长截止日期",
  increase_daily_minutes: "增加每日学习时间",
  reduce_scope: "减少本阶段课程范围",
  lower_intensity: "降低学习强度",
  change_available_weekdays: "增加可学习日期",
  reschedule_existing_tasks: "先调整冲突中的已有任务",
};

type PlanForm = {
  learningGoalId: number;
  courseId: number;
  startDate: string;
  targetDate: string;
  dailyMinutes: number;
  weekdays: number[];
  allowWeekends: boolean;
  intensity: "basic" | "standard" | "intensive";
  includeDueReviews: boolean;
  useLatestDiagnostic: boolean;
  useExistingMastery: boolean;
  reason: string;
};

export function StudyPlanPanel({ goals, courses }: { goals: LearningGoal[]; courses: Course[] }) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [plan, setPlan] = useState<StudyPlan | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const initialGoal = goals.find((goal) => goal.status === "active") ?? goals[0];
  const initialCourse = courses.find((course) => course.status === "active" && course.learning_goal_id === initialGoal?.id);
  const [form, setForm] = useState<PlanForm>(() => ({
    learningGoalId: initialGoal?.id ?? 0,
    courseId: initialCourse?.id ?? 0,
    startDate: localDate(new Date()),
    targetDate: initialGoal?.target_date ?? localDate(addDays(new Date(), 14)),
    dailyMinutes: initialGoal?.daily_minutes ?? 30,
    weekdays: [0, 1, 2, 3, 4],
    allowWeekends: false,
    intensity: "standard",
    includeDueReviews: true,
    useLatestDiagnostic: true,
    useExistingMastery: true,
    reason: "根据最新学习状态调整后续安排",
  }));
  const createRequest = useRef(crypto.randomUUID());
  const publishRequest = useRef(crypto.randomUUID());
  const replanRequest = useRef(crypto.randomUUID());
  const active = useQuery({ queryKey: ["study-plan-active"], queryFn: () => studyPlansApi.active() });
  const history = useQuery({
    queryKey: ["study-plan-history", plan?.id],
    queryFn: () => studyPlansApi.history(plan!.id),
    enabled: Boolean(plan?.id && historyOpen),
  });

  useEffect(() => {
    if (active.data && !plan) {
      setPlan(active.data);
      const parameters = active.data.latest_version.parameters;
      setForm((current) => ({
        ...current,
        learningGoalId: active.data!.learning_goal_id,
        courseId: active.data!.course_id,
        startDate: parameters.start_date,
        targetDate: parameters.target_date,
        dailyMinutes: parameters.daily_minutes,
        weekdays: parameters.available_weekdays,
        allowWeekends: parameters.allow_weekends,
        intensity: parameters.intensity,
        includeDueReviews: parameters.include_due_reviews,
        useLatestDiagnostic: parameters.use_latest_diagnostic,
        useExistingMastery: parameters.use_existing_mastery,
      }));
    }
  }, [active.data, plan]);

  const planPayload = () => ({
    request_id: createRequest.current,
    learning_goal_id: form.learningGoalId,
    course_id: form.courseId,
    start_date: form.startDate,
    target_date: form.targetDate,
    daily_minutes: form.dailyMinutes,
    available_weekdays: form.weekdays,
    allow_weekends: form.allowWeekends,
    intensity: form.intensity,
    include_due_reviews: form.includeDueReviews,
    use_latest_diagnostic: form.useLatestDiagnostic,
    use_existing_mastery: form.useExistingMastery,
  });
  const generated = useMutation({
    mutationFn: () => studyPlansApi.create(planPayload()),
    onSuccess: (value) => {
      setPlan(value);
      createRequest.current = crypto.randomUUID();
      showToast(value.status === "infeasible" ? "当前条件需要调整" : "计划草案已生成", value.status === "infeasible" ? "error" : "success");
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const publish = useMutation({
    mutationFn: () => studyPlansApi.publish(plan!.id, plan!.version, publishRequest.current),
    onSuccess: async (value) => {
      setPlan(value.plan);
      publishRequest.current = crypto.randomUUID();
      setConfirmOpen(false);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["study-plan-active"] }),
        queryClient.invalidateQueries({ queryKey: ["today"] }),
        queryClient.invalidateQueries({ queryKey: ["next-learning-action"] }),
      ]);
      showToast("计划已确认，执行任务已经就绪", "success");
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const replan = useMutation({
    mutationFn: () => studyPlansApi.replan(plan!.id, {
      request_id: replanRequest.current,
      expected_version: plan!.version,
      reason: form.reason,
      start_date: form.startDate,
      target_date: form.targetDate,
      daily_minutes: form.dailyMinutes,
      available_weekdays: form.weekdays,
      allow_weekends: form.allowWeekends,
      intensity: form.intensity,
      include_due_reviews: form.includeDueReviews,
      use_latest_diagnostic: form.useLatestDiagnostic,
      use_existing_mastery: form.useExistingMastery,
    }),
    onSuccess: (value) => {
      setPlan(value);
      replanRequest.current = crypto.randomUUID();
      setHistoryOpen(true);
      queryClient.invalidateQueries({ queryKey: ["study-plan-history", value.id] });
      showToast(value.latest_version.status === "infeasible" ? "新版本需要继续调整" : "新的计划版本已生成，请确认后生效", value.latest_version.status === "infeasible" ? "error" : "success");
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const validCourses = courses.filter((course) => course.status === "active" && course.learning_goal_id === form.learningGoalId);
  const canGenerate = form.learningGoalId > 0 && form.courseId > 0 && form.weekdays.length > 0 && form.targetDate > form.startDate;

  if (active.isLoading) return <LoadingState label="正在读取学习计划" />;
  if (active.isError) return <ErrorState message={active.error.message} onRetry={() => active.refetch()} />;

  return (
    <section className="study-plan-panel" aria-label="个性化学习计划">
      <header className="section-heading"><div><span className="page-kicker">诊断驱动计划</span><h2>个性化学习计划</h2><p>最终日期、顺序和每日容量由确定性规则检查；确认前不会改动今日任务。</p></div>{plan && <div className="plan-header-status"><span className={`status status--${plan.latest_version.status}`}>{plan.latest_version.status === "ready" ? "草案可确认" : statusLabel[plan.latest_version.status] ?? plan.latest_version.status}</span><button className="button button--quiet" onClick={() => setHistoryOpen((value) => !value)}><History size={16} />版本 {plan.current_version_number}</button></div>}</header>
      <form className="plan-setup" onSubmit={(event: FormEvent) => { event.preventDefault(); if (canGenerate) generated.mutate(); }}>
        <div className="plan-form-grid">
          <label className="field"><span>学习目标</span><select value={form.learningGoalId} onChange={(event) => {
            const goalId = Number(event.target.value);
            const goal = goals.find((item) => item.id === goalId);
            const course = courses.find((item) => item.learning_goal_id === goalId && item.status === "active");
            setForm((current) => ({ ...current, learningGoalId: goalId, courseId: course?.id ?? 0, dailyMinutes: goal?.daily_minutes ?? current.dailyMinutes, targetDate: goal?.target_date ?? current.targetDate }));
          }}>{goals.filter((goal) => goal.status !== "archived").map((goal) => <option key={goal.id} value={goal.id}>{goal.title}</option>)}</select></label>
          <label className="field"><span>正式课程</span><select value={form.courseId} onChange={(event) => setForm({ ...form, courseId: Number(event.target.value) })}><option value={0}>请选择课程</option>{validCourses.map((course) => <option key={course.id} value={course.id}>{course.title}</option>)}</select></label>
          <label className="field"><span>开始日期</span><input type="date" value={form.startDate} onChange={(event) => setForm({ ...form, startDate: event.target.value })} /></label>
          <label className="field"><span>截止日期</span><input type="date" min={form.startDate} value={form.targetDate} onChange={(event) => setForm({ ...form, targetDate: event.target.value })} /></label>
          <label className="field"><span>每日学习时间</span><div className="input-suffix"><input aria-label="每日学习时间" type="number" min={5} max={720} value={form.dailyMinutes} onChange={(event) => setForm({ ...form, dailyMinutes: Number(event.target.value) })} /><span>分钟</span></div></label>
          <label className="field"><span>学习强度</span><select value={form.intensity} onChange={(event) => setForm({ ...form, intensity: event.target.value as PlanForm["intensity"] })}><option value="basic">轻量巩固</option><option value="standard">标准推进</option><option value="intensive">强化练习</option></select></label>
        </div>
        <fieldset className="weekday-picker"><legend>每周可学习日期</legend><div>{weekdayLabels.map((label, day) => <label key={label} className={form.weekdays.includes(day) ? "is-selected" : ""}><input type="checkbox" checked={form.weekdays.includes(day)} onChange={() => {
          const weekdays = form.weekdays.includes(day) ? form.weekdays.filter((item) => item !== day) : [...form.weekdays, day].sort();
          setForm({ ...form, weekdays, allowWeekends: weekdays.some((item) => item >= 5) });
        }} /><span>{label}</span></label>)}</div></fieldset>
        <div className="plan-options"><label><input type="checkbox" checked={form.includeDueReviews} onChange={(event) => setForm({ ...form, includeDueReviews: event.target.checked })} />纳入到期复习</label><label><input type="checkbox" checked={form.useLatestDiagnostic} onChange={(event) => setForm({ ...form, useLatestDiagnostic: event.target.checked })} />使用最近诊断</label><label><input type="checkbox" checked={form.useExistingMastery} onChange={(event) => setForm({ ...form, useExistingMastery: event.target.checked })} />使用现有掌握记录</label></div>
        {plan && <label className="field plan-reason"><span>调整原因</span><input value={form.reason} minLength={3} maxLength={2000} onChange={(event) => setForm({ ...form, reason: event.target.value })} /></label>}
        <div className="form-actions"><span>{!form.weekdays.length ? "请至少选择一个学习日。" : form.targetDate <= form.startDate ? "截止日期必须晚于开始日期。" : "生成后先预览，确认时才会进入今日任务。"}</span>{plan ? <button className="button button--secondary" type="button" disabled={!canGenerate || replan.isPending} onClick={() => replan.mutate()}><RefreshCw size={16} />{replan.isPending ? "正在调整…" : "按新条件生成版本"}</button> : <button className="button button--primary" type="submit" disabled={!canGenerate || generated.isPending}><CalendarDays size={16} />{generated.isPending ? "正在排程…" : "生成计划草案"}</button>}</div>
      </form>

      {(generated.isPending || replan.isPending) && <div className="generation-progress" role="status"><div><strong>正在计算可执行计划</strong><small>检查前置关系、技能缺口、到期复习、现有任务和每日容量。</small></div><progress /></div>}
      {plan && <PlanPreview plan={plan} onPublish={() => setConfirmOpen(true)} publishPending={publish.isPending} />}
      {historyOpen && plan && <section className="plan-history"><header><h3>版本历史</h3><span>旧版本只读保留</span></header>{history.isLoading ? <LoadingState label="正在读取版本" /> : history.isError ? <ErrorState message={history.error.message} onRetry={() => history.refetch()} /> : <div>{history.data?.items.map((version) => <article key={version.id}><span className={`status status--${version.status}`}>{statusLabel[version.status] ?? version.status}</span><div><strong>版本 {version.version_number} · {version.reason}</strong><small>{formatDateTime(version.created_at)} · {version.items.length} 项 · {version.required_minutes} 分钟</small></div></article>)}</div>}</section>}
      {plan && <Dialog open={confirmOpen} title="确认学习计划" onClose={() => setConfirmOpen(false)}><div className="plan-confirm"><p>确认后，系统会创建或关联 {plan.latest_version.items.length} 项执行任务。已完成任务不会被覆盖，中途失败会完整回滚。</p><dl><div><dt>学习周期</dt><dd>{formatDate(plan.latest_version.parameters.start_date)} 至 {formatDate(plan.latest_version.parameters.target_date)}</dd></div><div><dt>计划时间</dt><dd>{plan.latest_version.required_minutes} 分钟</dd></div><div><dt>每日上限</dt><dd>{plan.latest_version.parameters.daily_minutes} 分钟</dd></div></dl><div className="form-actions"><button className="button button--secondary" onClick={() => setConfirmOpen(false)}>继续查看</button><button className="button button--primary" disabled={publish.isPending} onClick={() => publish.mutate()}><Send size={16} />{publish.isPending ? "正在确认…" : "确认并激活"}</button></div></div></Dialog>}
    </section>
  );
}

function PlanPreview({ plan, onPublish, publishPending }: { plan: StudyPlan; onPublish: () => void; publishPending: boolean }) {
  const version = plan.latest_version;
  if (version.status === "infeasible") return <section className="plan-infeasible"><header><AlertTriangle size={22} /><div><h3>当前条件无法形成完整计划</h3><p>系统没有强行塞入超出时间预算的任务。调整后可生成新版本。</p></div></header><div className="plan-capacity"><div><span>所需时间</span><strong>{version.required_minutes} 分钟</strong></div><div><span>可用时间</span><strong>{version.available_minutes} 分钟</strong></div><div><span>时间缺口</span><strong>{version.gap_minutes} 分钟</strong></div></div><div className="conflict-list">{version.conflicts.map((conflict, index) => <article key={index}><AlertTriangle size={16} /><span>{conflictLabel[String(conflict.code)] ?? "当前条件存在排程冲突"}</span></article>)}</div><div className="suggestion-list"><strong>可以这样调整</strong>{version.suggestions.map((suggestion, index) => <span key={index}>{suggestionLabel[String(suggestion.action)] ?? String(suggestion.message ?? "调整计划条件")}</span>)}</div></section>;
  const days = groupByDate(version.items);
  const quality = version.quality_report;
  return <section className="plan-preview"><header><div><span className="page-kicker">计划预览</span><h3>{plan.course_title}</h3><p>{formatDate(version.parameters.start_date)} 至 {formatDate(version.parameters.target_date)} · 共 {version.required_minutes} 分钟</p></div>{version.status === "ready" && <button className="button button--primary" disabled={publishPending} onClick={onPublish}><CheckCircle2 size={16} />确认计划</button>}{version.status === "active" && <span className="status status--active">当前生效版本</span>}</header><div className="plan-quality" aria-label="计划质量检查"><div><span>前置顺序</span><strong>{percent(quality.prerequisite_constraint_rate)}</strong></div><div><span>时间预算</span><strong>{percent(quality.time_budget_constraint_rate)}</strong></div><div><span>可学习日期</span><strong>{percent(quality.available_date_constraint_rate)}</strong></div><div><span>重复任务</span><strong>{quality.duplicate_task_count ?? 0}</strong></div><div><span>未覆盖知识点</span><strong>{quality.uncovered_required_knowledge_point_ids?.length ?? 0}</strong></div></div><div className="plan-days">{Object.entries(days).map(([day, items]) => <article className="plan-day" key={day}><header><div><CalendarDays size={17} /><strong>{formatDate(day)}</strong></div><span>{items.reduce((sum, item) => sum + item.estimated_minutes, 0)} 分钟</span></header><div>{items.map((item) => <PlanItemRow key={item.id} item={item} />)}</div></article>)}</div></section>;
}

function PlanItemRow({ item }: { item: StudyPlanItem }) {
  return <div className="plan-item"><span className="plan-item__type">{activityLabel[item.activity_type] ?? "学习"}</span><div><strong>{item.title}</strong><p>{item.scheduling_reason}</p><small>{item.course_title}{item.knowledge_point_title ? ` · ${item.knowledge_point_title}` : ""}{item.prerequisite_ids.length ? ` · 需先完成 ${item.prerequisite_ids.length} 个前置知识点` : ""}</small></div><span className="plan-item__time"><Clock3 size={14} />{item.estimated_minutes} 分钟</span></div>;
}

function groupByDate(items: StudyPlanItem[]) {
  return items.reduce<Record<string, StudyPlanItem[]>>((groups, item) => {
    (groups[item.scheduled_date] ??= []).push(item);
    return groups;
  }, {});
}

function percent(value?: number) {
  return `${Math.round((value ?? 0) * 100)}%`;
}

function addDays(value: Date, days: number) {
  const next = new Date(value);
  next.setDate(next.getDate() + days);
  return next;
}

function localDate(value: Date) {
  const local = new Date(value.getTime() - value.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}
