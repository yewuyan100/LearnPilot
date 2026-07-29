import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, Clock3, Plus, Trash2 } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { coursesApi, goalsApi } from "../api/resources";
import { Dialog } from "../components/Dialog";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { useToast } from "../components/toast-context";
import { statusLabel } from "../utils/format";

export function CoursesPage() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const courses = useQuery({ queryKey: ["courses"], queryFn: coursesApi.list });
  const goals = useQuery({ queryKey: ["goals"], queryFn: goalsApi.list });
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [courseOpen, setCourseOpen] = useState(false);
  const [pointOpen, setPointOpen] = useState(false);
  const points = useQuery({
    queryKey: ["knowledge-points", selectedId],
    queryFn: () => coursesApi.points(selectedId!),
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
  const removePoint = useMutation({
    mutationFn: coursesApi.removePoint,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["knowledge-points", selectedId] });
      queryClient.invalidateQueries({ queryKey: ["courses"] });
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });

  if (courses.isLoading || goals.isLoading) return <LoadingState label="正在读取课程结构" />;
  if (courses.isError) return <ErrorState message={courses.error.message} onRetry={() => courses.refetch()} />;
  const selected = courses.data?.find((course) => course.id === selectedId);

  return (
    <div className="page">
      <header className="page-header page-header--split">
        <div><h1>课程</h1><p>手动组织课程与知识点，保持学习路径清楚可控。</p></div>
        <button className="button button--primary" disabled={!goals.data?.length} onClick={() => setCourseOpen(true)}>
          <Plus size={16} />新建课程
        </button>
      </header>
      {!goals.data?.length && (
        <div className="notice notice--warning">请先在今日学习页创建学习目标，再创建课程。</div>
      )}
      {!courses.data?.length ? (
        <EmptyState title="还没有课程" description="课程负责组织同一目标下的一组知识点。" action={
          goals.data?.length ? <button className="button button--primary" onClick={() => setCourseOpen(true)}>新建课程</button> : undefined
        } />
      ) : (
        <div className="course-workbench">
          <aside className="course-list" aria-label="课程列表">
            {courses.data.map((course) => (
              <button
                key={course.id}
                className={`course-list__item ${course.id === selectedId ? "course-list__item--active" : ""}`}
                onClick={() => setSelectedId(course.id)}
              >
                <BookOpen size={18} />
                <span><strong>{course.title}</strong><small>{course.knowledge_point_count} 个知识点 · {statusLabel[course.status]}</small></span>
              </button>
            ))}
          </aside>
          <section className="course-detail">
            {selected && (
              <>
                <header className="course-detail__header">
                  <div>
                    <span className={`status status--${selected.status}`}>{statusLabel[selected.status]}</span>
                    <h2>{selected.title}</h2>
                    <p>{selected.description || "尚未填写课程描述"}</p>
                    <small>所属目标：{selected.learning_goal_title}</small>
                  </div>
                  <div className="button-row">
                    <button className="button button--secondary" onClick={() => setPointOpen(true)}><Plus size={16} />添加知识点</button>
                    <button
                      className="button button--danger"
                      onClick={() => {
                        if (window.confirm(`确认删除课程“${selected.title}”及其知识点？`)) removeCourse.mutate(selected.id);
                      }}
                    ><Trash2 size={16} />删除</button>
                  </div>
                </header>
                {points.isLoading ? <LoadingState /> : points.data?.length ? (
                  <ol className="knowledge-list">
                    {points.data.map((point) => (
                      <li key={point.id}>
                        <span className="knowledge-list__index">{String(point.order_index).padStart(2, "0")}</span>
                        <div className="knowledge-list__body">
                          <div><h3>{point.title}</h3><p>{point.description || "暂无描述"}</p></div>
                          <div className="knowledge-list__meta">
                            <span><Clock3 size={14} /> {point.estimated_minutes} 分钟</span>
                            <select
                              aria-label={`修改 ${point.title} 状态`}
                              value={point.status}
                              onChange={(event) => updatePoint.mutate({ id: point.id, status: event.target.value })}
                            >
                              <option value="not_started">未开始</option>
                              <option value="learning">学习中</option>
                              <option value="completed">已完成</option>
                              <option value="locked">已锁定</option>
                            </select>
                            <button
                              className="icon-button icon-button--danger"
                              aria-label={`删除 ${point.title}`}
                              onClick={() => {
                                if (window.confirm(`确认删除知识点“${point.title}”？`)) removePoint.mutate(point.id);
                              }}
                            ><Trash2 size={16} /></button>
                          </div>
                        </div>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <EmptyState title="这个课程还没有知识点" description="按学习顺序添加第一个知识点。" action={
                    <button className="button button--primary" onClick={() => setPointOpen(true)}>添加知识点</button>
                  } />
                )}
              </>
            )}
          </section>
        </div>
      )}
      <Dialog open={courseOpen} title="新建课程" onClose={() => setCourseOpen(false)}>
        <CourseForm goals={goals.data ?? []} pending={courseMutation.isPending} onCancel={() => setCourseOpen(false)} onSubmit={(data) => courseMutation.mutate(data)} />
      </Dialog>
      <Dialog open={pointOpen} title="添加知识点" onClose={() => setPointOpen(false)}>
        <PointForm orderIndex={(points.data?.length ?? 0) + 1} pending={pointMutation.isPending} onCancel={() => setPointOpen(false)} onSubmit={(data) => pointMutation.mutate(data)} />
      </Dialog>
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
