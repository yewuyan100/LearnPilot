import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, ArrowRight, BarChart3, BookOpen, CheckCircle2, ClipboardCheck, Clock3, FileText, FolderOpen, MessageSquareText, NotebookPen, Plus, Settings2, Trash2 } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { activitiesApi, coursesApi, dashboardApi, goalsApi, masteryApi, materialLearningApi } from "../api/resources";
import { Dialog } from "../components/Dialog";
import { EffectiveMaterials } from "../components/EffectiveMaterials";
import { TargetMaterialPicker } from "../components/TargetMaterialPicker";
import { CourseDiagnosticPanel } from "../components/CourseDiagnosticPanel";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { useToast } from "../components/toast-context";
import { statusLabel } from "../utils/format";
import type { KnowledgePoint, KnowledgePointImpact } from "../types";

export function CoursesPage() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const courses = useQuery({ queryKey: ["courses"], queryFn: coursesApi.list });
  const goals = useQuery({ queryKey: ["goals"], queryFn: goalsApi.list });
  const activities = useQuery({ queryKey: ["learning-activities"], queryFn: () => activitiesApi.list() });
  const today = useQuery({ queryKey: ["today"], queryFn: dashboardApi.today });
  const mastery = useQuery({ queryKey: ["mastery"], queryFn: masteryApi.list });
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<"path" | "ai" | "materials" | "activities" | "diagnostic">("path");
  const [courseOpen, setCourseOpen] = useState(false);
  const [pointOpen, setPointOpen] = useState(false);
  const [lifecyclePoint, setLifecyclePoint] = useState<KnowledgePoint | null>(null);
  const [lifecycleReason, setLifecycleReason] = useState("课程内容已调整，不再安排该知识点");
  const [lifecycleImpact, setLifecycleImpact] = useState<KnowledgePointImpact | null>(null);
  const [lifecycleRequestId, setLifecycleRequestId] = useState(() => crypto.randomUUID());
  const [materialOpen, setMaterialOpen] = useState(false);
  const points = useQuery({
    queryKey: ["knowledge-points", selectedId],
    queryFn: () => coursesApi.points(selectedId!),
    enabled: selectedId !== null,
  });
  const effectiveMaterials = useQuery({
    queryKey: ["effective-materials", "course", selectedId],
    queryFn: () => materialLearningApi.courseMaterials(selectedId!),
    enabled: selectedId !== null,
  });
  useEffect(() => {
    if (!selectedId && courses.data?.length) setSelectedId(courses.data[0].id);
  }, [courses.data, selectedId]);

  const courseMutation = useMutation({
    mutationFn: (data: unknown) => coursesApi.create(data),
    onSuccess: async (course) => {
      await queryClient.invalidateQueries({ queryKey: ["courses"] });
      setSelectedId(course.id);
      setCourseOpen(false);
      showToast("课程已创建", "success");
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const pointMutation = useMutation({
    mutationFn: (data: unknown) => coursesApi.createPoint(selectedId!, data),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["knowledge-points", selectedId] });
      await queryClient.invalidateQueries({ queryKey: ["courses"] });
      setPointOpen(false);
      showToast("知识点已添加", "success");
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const updatePoint = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) => coursesApi.updatePoint(id, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["knowledge-points", selectedId] });
      queryClient.invalidateQueries({ queryKey: ["progress"] });
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const removeCourse = useMutation({
    mutationFn: coursesApi.remove,
    onSuccess: async () => {
      setSelectedId(null);
      await queryClient.invalidateQueries({ queryKey: ["courses"] });
      showToast("课程及关联知识点已删除", "success");
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const inspectPointLifecycle = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) => coursesApi.inspectPoint(id, {
      action: "archive",
      lifecycle_reason: reason,
    }),
    onSuccess: setLifecycleImpact,
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const archivePoint = useMutation({
    mutationFn: ({ point, impact, reason, requestId }: { point: KnowledgePoint; impact: KnowledgePointImpact; reason: string; requestId: string }) => coursesApi.archivePoint(point.id, {
      action: "archive",
      lifecycle_reason: reason,
      request_id: requestId,
      expected_version: point.version,
      impact_hash: impact.impact_hash,
      confirmed: true,
    }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["knowledge-points", selectedId] }),
        queryClient.invalidateQueries({ queryKey: ["courses"] }),
        queryClient.invalidateQueries({ queryKey: ["today"] }),
        queryClient.invalidateQueries({ queryKey: ["next-learning-action"] }),
        queryClient.invalidateQueries({ queryKey: ["study-plans"] }),
      ]);
      setLifecyclePoint(null);
      setLifecycleImpact(null);
      showToast("知识点已归档，受影响的计划、任务和会话已停止执行", "success");
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });

  const openArchiveDialog = (point: KnowledgePoint) => {
    const reason = "课程内容已调整，不再安排该知识点";
    setLifecyclePoint(point);
    setLifecycleReason(reason);
    setLifecycleImpact(null);
    setLifecycleRequestId(crypto.randomUUID());
    inspectPointLifecycle.mutate({ id: point.id, reason });
  };

  if (courses.isLoading || goals.isLoading || activities.isLoading) return <LoadingState label="正在读取课程结构" />;
  if (courses.isError || activities.isError) return <ErrorState message={(courses.error ?? activities.error)!.message} onRetry={() => courses.refetch()} />;
  const selected = courses.data?.find((course) => course.id === selectedId);
  const relatedActivities = activities.data?.items.filter((activity) => activity.course_id === selectedId) ?? [];
  const courseTasks = (today.data?.tasks ?? []).filter((task) => task.course_id === selectedId);
  const courseMastery = (mastery.data?.items ?? []).filter((item) => item.course_id === selectedId);
  const completedPoints = points.data?.filter((point) => point.status === "completed").length ?? 0;
  const projectProgress = points.data?.length ? Math.round((completedPoints / points.data.length) * 100) : 0;
  const workspaceTabs = [
    { id: "path", label: "学习路径" },
    { id: "ai", label: "AI 辅导" },
    { id: "materials", label: "课程资料" },
    { id: "activities", label: "测验练习" },
    { id: "diagnostic", label: "诊断与计划" },
  ] as const;

  return (
    <div className="page project-page">
      <header className="page-header page-header--split">
        <div><h1>学习项目</h1><p>让资料、学习路径、练习和辅导保持在同一个项目上下文中。</p></div>
        <button className="button button--primary" disabled={!goals.data?.length} onClick={() => setCourseOpen(true)}>
          <Plus size={16} />新建项目
        </button>
      </header>
      <nav className="page-tabs" aria-label="学习项目视图"><Link className="is-active" to="/courses">学习项目</Link><Link to="/course-architecture/drafts">课程草案</Link></nav>
      {!goals.data?.length && (
        <div className="notice notice--warning">请先在今日学习页创建学习目标，再创建课程。</div>
      )}
      {!courses.data?.length ? (
        <EmptyState title="还没有课程" description="课程负责组织同一目标下的一组知识点。" action={
          goals.data?.length ? <button className="button button--primary" onClick={() => setCourseOpen(true)}>新建课程</button> : undefined
        } />
      ) : (
        selected && <section className="project-workspace">
          <header className="project-workspace__header">
            <div className="project-workspace__title"><span className={`status status--${selected.status}`}>{statusLabel[selected.status]}</span><div><span>正在学习</span><h2>{selected.title}</h2><p>{selected.description || `所属目标：${selected.learning_goal_title}`}</p></div></div>
            <div className="project-workspace__progress"><div><span>项目进度</span><strong>{projectProgress}%</strong></div><progress max={100} value={projectProgress} aria-label={`${selected.title} 项目进度`} /><small>{completedPoints}/{points.data?.length ?? 0} 个知识点已完成</small></div>
            <div className="project-workspace__actions"><Link className="button button--secondary" to="/goals"><Settings2 size={16}/>项目设置</Link><button className="icon-button icon-button--danger" aria-label={`删除项目 ${selected.title}`} title="删除项目" onClick={() => { if (window.confirm(`确认删除课程“${selected.title}”及其知识点？`)) removeCourse.mutate(selected.id); }}><Trash2 size={17}/></button></div>
          </header>

          <div className="project-workspace__body">
            <aside className="project-context-panel" aria-label="资料与目录">
              <section className="project-switcher">
                <h3>学习项目</h3>
                {courses.data.map((course) => <button key={course.id} className={course.id === selectedId ? "is-active" : ""} onClick={() => { setSelectedId(course.id); setActiveTab("path"); }}><BookOpen size={16}/><span><strong>{course.title}</strong><small>{course.knowledge_point_count} 个知识点</small></span></button>)}
              </section>
              <section className="project-sources">
                <header><h3>资料与目录</h3><button className="icon-button" aria-label="添加课程资料" title="添加课程资料" onClick={() => setMaterialOpen(true)}><Plus size={16}/></button></header>
                {effectiveMaterials.isLoading ? <LoadingState label="正在读取资料"/> : effectiveMaterials.data?.length ? <div className="project-source-list">{effectiveMaterials.data.slice(0, 4).map((item) => <Link key={item.material_id} to={`/materials/${item.material_id}`}><FileText size={17}/><span><strong>{item.material_title || item.original_filename}</strong><small>{item.indexing_status === "completed" ? "解析完成" : "等待处理"}</small></span></Link>)}</div> : <div className="project-panel-empty"><FolderOpen size={18}/><span>还没有关联资料</span><button onClick={() => setMaterialOpen(true)}>添加资料</button></div>}
                <div className="project-outline"><h3>课程目录</h3>{points.data?.length ? points.data.map((point) => <Link key={point.id} to={`/knowledge-points/${point.id}`} className={point.status === "learning" ? "is-current" : ""}><span>{point.status === "completed" ? <CheckCircle2 size={14}/> : point.order_index}</span><strong>{point.title}</strong></Link>) : <p>添加知识点后，这里会形成学习路径。</p>}</div>
              </section>
            </aside>

            <main className="project-learning-panel">
              <nav className="workspace-tabs" role="tablist" aria-label="项目学习视图">{workspaceTabs.map((tab) => <button key={tab.id} role="tab" aria-selected={activeTab === tab.id} className={activeTab === tab.id ? "is-active" : ""} onClick={() => setActiveTab(tab.id)} onKeyDown={(event) => { if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return; const tabs = Array.from(event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]') ?? []); const index = tabs.indexOf(event.currentTarget); const nextIndex = event.key === "ArrowRight" ? (index + 1) % tabs.length : (index - 1 + tabs.length) % tabs.length; tabs[nextIndex]?.focus(); tabs[nextIndex]?.click(); }}>{tab.label}</button>)}</nav>
              <div className="workspace-tab-panel" role="tabpanel">
                {activeTab === "path" && <section className="learning-path-panel"><header><div><h3>学习路径</h3><p>按顺序推进知识点，状态会同步到掌握与复习视图。</p></div><button className="button button--secondary" onClick={() => setPointOpen(true)}><Plus size={16}/>添加知识点</button></header>{points.isLoading ? <LoadingState/> : points.data?.length ? <ol className="knowledge-list">{points.data.map((point) => <li key={point.id}><span className="knowledge-list__index">{String(point.order_index).padStart(2, "0")}</span><div className="knowledge-list__body"><div><h3><Link to={`/knowledge-points/${point.id}`}>{point.title}</Link></h3><p>{point.description || "暂无描述"}</p></div><div className="knowledge-list__meta"><Link className="icon-button" aria-label={`为 ${point.title} 记录笔记`} to={`/notes?new=1&entity_type=knowledge_point&entity_id=${point.id}`}><NotebookPen size={16}/></Link><span><Clock3 size={14}/>{point.estimated_minutes} 分钟</span><select aria-label={`修改 ${point.title} 状态`} value={point.status} onChange={(event) => updatePoint.mutate({ id: point.id, status: event.target.value })}><option value="not_started">未开始</option><option value="learning">学习中</option><option value="completed">已完成</option><option value="locked">已锁定</option></select><button className="icon-button icon-button--danger" aria-label={`归档 ${point.title}`} title="查看影响并归档" onClick={() => openArchiveDialog(point)}><Archive size={16}/></button></div></div></li>)}</ol> : <EmptyState title="这个项目还没有知识点" description="按学习顺序添加第一个知识点。" action={<button className="button button--primary" onClick={() => setPointOpen(true)}>添加知识点</button>}/>}</section>}
                {activeTab === "ai" && <section className="project-ai-panel"><div className="project-ai-panel__mark"><MessageSquareText size={22}/></div><div><h3>围绕「{selected.title}」提问</h3><p>{effectiveMaterials.data?.length ? `当前项目已有 ${effectiveMaterials.data.length} 份有效资料，可限定资料范围进行问答并核对引用。` : "先关联课程资料，再开始可追溯的资料问答。"}</p><div className="button-row"><Link className="button button--primary" to={`/knowledge?tab=qa&scope=course&course_id=${selected.id}`}>打开资料问答</Link><Link className="button button--secondary" to="/support">学习支持</Link></div></div></section>}
                {activeTab === "materials" && <section className="course-related"><header><div><h3>课程资料</h3><p>这里只显示与当前项目直接或继承关联的真实资料。</p></div><div className="button-row"><button className="button button--secondary" onClick={() => setMaterialOpen(true)}><FileText size={16}/>添加现有资料</button><Link className="button button--secondary" to={`/knowledge?tab=qa&scope=course&course_id=${selected.id}`}><MessageSquareText size={16}/>资料问答</Link></div></header>{effectiveMaterials.isLoading ? <LoadingState label="正在读取课程资料"/> : effectiveMaterials.isError ? <ErrorState message={effectiveMaterials.error.message}/> : <EffectiveMaterials items={effectiveMaterials.data ?? []} emptyText="从知识收件箱或这里添加资料；目标级资料会标记为继承资料。"/>}</section>}
                {activeTab === "activities" && <section className="course-related"><header><div><h3>测验练习</h3><p>使用当前项目有效资料生成并完成学习活动。</p></div><Link className="button button--secondary" to={`/activities?course_id=${selected.id}`}>生成练习 <ArrowRight size={14}/></Link></header>{relatedActivities.length ? <div className="workspace-list">{relatedActivities.slice(0, 6).map((activity) => <Link className="workspace-row" key={activity.id} to={`/activities/${activity.id}`}><ClipboardCheck size={16}/><div><strong>{activity.title}</strong><small>{statusLabel[activity.status] ?? activity.status} · {activity.question_count} 题 · 已完成 {activity.completed_attempt_count} 次</small></div><ArrowRight size={16}/></Link>)}</div> : <div className="inline-empty"><ClipboardCheck size={20}/><span>当前项目还没有关联练习。</span></div>}</section>}
                {activeTab === "diagnostic" && <CourseDiagnosticPanel course={selected}/>}
              </div>
            </main>

            <aside className="project-assistant-panel" aria-label="项目学习辅助">
              <section><header><h3>学习工具</h3></header><div className="project-tool-grid"><button onClick={() => setActiveTab("ai")}><MessageSquareText size={18}/><span>AI 辅导</span></button><button onClick={() => setActiveTab("materials")}><FileText size={18}/><span>课程资料</span></button><button onClick={() => setActiveTab("activities")}><ClipboardCheck size={18}/><span>测验练习</span></button><Link to={`/notes?new=1&entity_type=course&entity_id=${selected.id}`}><NotebookPen size={18}/><span>学习笔记</span></Link><button onClick={() => setActiveTab("diagnostic")}><BarChart3 size={18}/><span>掌握分析</span></button><Link to="/goals"><Settings2 size={18}/><span>学习计划</span></Link></div></section>
              <section><header><h3>今日任务</h3><Link to="/today">查看全部</Link></header>{courseTasks.length ? <div className="project-task-list">{courseTasks.slice(0, 4).map((task) => <Link to="/today" key={task.id}><span className={`task-check task-check--${task.status}`}>{task.status === "completed" ? <CheckCircle2 size={15}/> : <span/>}</span><strong>{task.title}</strong></Link>)}</div> : <p className="project-assistant-empty">当前项目今天没有安排任务。</p>}</section>
              <section><header><h3>掌握概览</h3><Link to="/review?tab=mastery">查看详情</Link></header>{courseMastery.length ? <div className="project-mastery-list">{courseMastery.slice(0, 4).map((item) => <Link key={item.knowledge_point_id} to={`/mastery/${item.knowledge_point_id}`}><div><strong>{item.knowledge_point_title}</strong><span>{item.mastery_score === null ? "待评估" : `${Math.round(item.mastery_score)}%`}</span></div><progress max={100} value={item.mastery_score ?? 0}/></Link>)}</div> : <p className="project-assistant-empty">完成练习后显示真实掌握情况。</p>}</section>
            </aside>
          </div>
        </section>
      )}
      <Dialog open={courseOpen} title="新建课程" onClose={() => setCourseOpen(false)}>
        <CourseForm goals={goals.data ?? []} pending={courseMutation.isPending} onCancel={() => setCourseOpen(false)} onSubmit={(data) => courseMutation.mutate(data)} />
      </Dialog>
      <Dialog open={pointOpen} title="添加知识点" onClose={() => setPointOpen(false)}>
        <PointForm orderIndex={(points.data?.length ?? 0) + 1} pending={pointMutation.isPending} onCancel={() => setPointOpen(false)} onSubmit={(data) => pointMutation.mutate(data)} />
      </Dialog>
      <Dialog open={Boolean(lifecyclePoint)} title={`归档知识点${lifecyclePoint ? ` · ${lifecyclePoint.title}` : ""}`} onClose={() => { setLifecyclePoint(null); setLifecycleImpact(null); }}>
        <div className="form-stack">
          <p>归档不会删除历史学习事实，也不会把历史记录静默改挂到其他知识点。</p>
          <label className="field"><span>归档原因</span><textarea value={lifecycleReason} onChange={(event) => { setLifecycleReason(event.target.value); setLifecycleImpact(null); setLifecycleRequestId(crypto.randomUUID()); }} /></label>
          {inspectPointLifecycle.isPending ? <LoadingState label="正在检查影响"/> : lifecycleImpact ? <div className="notice notice--warning"><strong>确认以下执行影响</strong><p>学习计划 {lifecycleImpact.study_plan_version_ids.length} 个版本 · 今日任务 {lifecycleImpact.actionable_daily_task_ids.length} 项 · 活跃会话 {lifecycleImpact.active_learning_session_ids.length} 个</p><p>历史活动 {lifecycleImpact.activity_ids.length} 项 · 掌握记录 {lifecycleImpact.mastery_ids.length} 项 · 复习安排 {lifecycleImpact.review_schedule_ids.length} 项（历史关联保留）</p></div> : <p className="muted">原因变化后需要重新检查影响。</p>}
          <div className="form-actions"><button type="button" className="button button--secondary" onClick={() => { setLifecyclePoint(null); setLifecycleImpact(null); }}>取消</button>{lifecycleImpact ? <button type="button" className="button button--primary" disabled={archivePoint.isPending} onClick={() => lifecyclePoint && archivePoint.mutate({ point: lifecyclePoint, impact: lifecycleImpact, reason: lifecycleReason, requestId: lifecycleRequestId })}>{archivePoint.isPending ? "正在归档" : "确认归档并停止受影响执行"}</button> : <button type="button" className="button button--primary" disabled={!lifecyclePoint || lifecycleReason.trim().length < 3 || inspectPointLifecycle.isPending} onClick={() => lifecyclePoint && inspectPointLifecycle.mutate({ id: lifecyclePoint.id, reason: lifecycleReason })}>检查影响</button>}</div>
        </div>
      </Dialog>
      {selected && (
        <TargetMaterialPicker
          open={materialOpen}
          targetType="course"
          targetId={selected.id}
          targetTitle={selected.title}
          onClose={() => setMaterialOpen(false)}
        />
      )}
    </div>
  );
}

function CourseForm({ goals, pending, onCancel, onSubmit }: { goals: Array<{ id: number; title: string }>; pending: boolean; onCancel: () => void; onSubmit: (data: unknown) => void }) {
  const [form, setForm] = useState({ learning_goal_id: goals[0]?.id ?? 0, title: "", description: "", status: "active" });
  return <form className="form-stack" onSubmit={(event: FormEvent) => { event.preventDefault(); onSubmit(form); }}>
    <label className="field"><span>所属目标</span><select required value={form.learning_goal_id} onChange={(e) => setForm({ ...form, learning_goal_id: Number(e.target.value) })}>{goals.map((goal) => <option key={goal.id} value={goal.id}>{goal.title}</option>)}</select></label>
    <label className="field"><span>课程名称</span><input required maxLength={200} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="例如：MCP 基础" /></label>
    <label className="field"><span>课程描述</span><textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
    <div className="form-actions"><button className="button button--secondary" type="button" onClick={onCancel}>取消</button><button className="button button--primary" disabled={pending} type="submit">{pending ? "正在创建" : "创建课程"}</button></div>
  </form>;
}

function PointForm({ orderIndex, pending, onCancel, onSubmit }: { orderIndex: number; pending: boolean; onCancel: () => void; onSubmit: (data: unknown) => void }) {
  const [form, setForm] = useState({ title: "", description: "", order_index: orderIndex, estimated_minutes: 20, status: "not_started" });
  return <form className="form-stack" onSubmit={(event: FormEvent) => { event.preventDefault(); onSubmit(form); }}>
    <label className="field"><span>知识点名称</span><input required maxLength={200} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></label>
    <label className="field"><span>说明</span><textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
    <div className="form-grid">
      <label className="field"><span>顺序</span><input type="number" min={0} value={form.order_index} onChange={(e) => setForm({ ...form, order_index: Number(e.target.value) })} /></label>
      <label className="field"><span>预计分钟</span><input type="number" min={1} value={form.estimated_minutes} onChange={(e) => setForm({ ...form, estimated_minutes: Number(e.target.value) })} /></label>
    </div>
    <div className="form-actions"><button className="button button--secondary" type="button" onClick={onCancel}>取消</button><button className="button button--primary" disabled={pending} type="submit">{pending ? "正在添加" : "添加知识点"}</button></div>
  </form>;
}
