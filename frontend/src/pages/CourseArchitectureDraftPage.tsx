import { useMutation, useQuery, useQueryClient, type UseMutationResult } from "@tanstack/react-query";
import { ArrowDown, ArrowLeft, ArrowUp, BookOpen, CheckCircle2, FileText, GitBranch, Lock, LockOpen, Merge, Plus, RefreshCw, Send, Square, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { courseArchitectureApi, materialsApi } from "../api/resources";
import { Dialog } from "../components/Dialog";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { useToast } from "../components/toast-context";
import type { CourseArchitectureDraft, DraftCourse, DraftKnowledgePoint } from "../types";

const statusLabels: Record<string, string> = { draft: "编辑中", generating: "分析中", review_required: "需要检查", ready: "可发布", publishing: "正在发布", published: "已发布", failed: "生成失败", archived: "已归档" };

export function CourseArchitectureDraftPage() {
  const id = Number(useParams().id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [courseId, setCourseId] = useState<number | null>(null);
  const [pointId, setPointId] = useState<number | null>(null);
  const [courseOpen, setCourseOpen] = useState(false);
  const [pointOpen, setPointOpen] = useState(false);
  const [sourceOpen, setSourceOpen] = useState(false);
  const [publishOpen, setPublishOpen] = useState(false);
  const [publishedIds, setPublishedIds] = useState<number[]>([]);
  const [generationPending, setGenerationPending] = useState(false);
  const draftQuery = useQuery({
    queryKey: ["course-architecture-draft", id],
    queryFn: () => courseArchitectureApi.get(id),
    enabled: Number.isFinite(id),
    refetchInterval: (query) => generationPending || query.state.data?.generation_status === "running" ? 800 : false,
  });
  const draft = draftQuery.data;
  useEffect(() => { if (draft?.courses.length && !draft.courses.some((item) => item.id === courseId)) setCourseId(draft.courses[0].id); }, [courseId, draft]);
  const selectedCourse = draft?.courses.find((item) => item.id === courseId) ?? null;
  useEffect(() => { if (selectedCourse?.knowledge_points.length && !selectedCourse.knowledge_points.some((item) => item.id === pointId)) setPointId(selectedCourse.knowledge_points[0].id); }, [pointId, selectedCourse]);
  const selectedPoint = selectedCourse?.knowledge_points.find((item) => item.id === pointId) ?? null;
  const allPoints = useMemo(() => draft?.courses.flatMap((course) => course.knowledge_points.map((point) => ({ ...point, courseTitle: course.title }))) ?? [], [draft]);
  const refresh = async (value: CourseArchitectureDraft, message?: string) => {
    queryClient.setQueryData(["course-architecture-draft", id], value);
    await queryClient.invalidateQueries({ queryKey: ["course-architecture-drafts"] });
    if (message) showToast(message, "success");
  };
  const action = useMutation({
    mutationFn: (run: () => Promise<CourseArchitectureDraft>) => run(),
    onSuccess: (value) => refresh(value),
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const publish = useMutation({
    mutationFn: () => courseArchitectureApi.publish(id, draft!.version, crypto.randomUUID()),
    onSuccess: async (result) => { setPublishedIds(result.course_ids); setPublishOpen(false); await draftQuery.refetch(); await queryClient.invalidateQueries({ queryKey: ["courses"] }); showToast("课程架构已发布", "success"); },
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const createVersion = useMutation({
    mutationFn: () => courseArchitectureApi.createVersion(id),
    onSuccess: async (value) => {
      await queryClient.invalidateQueries({ queryKey: ["course-architecture-drafts"] });
      navigate(`/course-architecture/drafts/${value.id}`);
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const cancelGeneration = useMutation({
    mutationFn: () => courseArchitectureApi.cancel(id, draft!.version),
    onSuccess: (value) => refresh(value, "正在停止资料分析"),
    onError: (error: Error) => showToast(error.message, "error"),
  });

  if (draftQuery.isLoading) return <LoadingState label="正在读取课程架构草案"/>;
  if (draftQuery.isError || !draft) return <ErrorState message={draftQuery.error?.message ?? "草案不存在"} onRetry={() => draftQuery.refetch()}/>;
  const readOnly = draft.status === "published" || draft.status === "archived" || draft.status === "publishing";
  const sourceCount = allPoints.reduce((sum, point) => sum + point.sources.length, 0);
  const formalCourseIds = publishedIds.length ? publishedIds : draft.courses.flatMap((course) => course.published_course_id ? [course.published_course_id] : []);
  return <div className="page architecture-page">
    <Link className="text-link" to="/course-architecture/drafts"><ArrowLeft size={15}/>返回课程草案</Link>
    <header className="page-header architecture-header">
      <div><span className="page-kicker">{draft.learning_goal_title}</span><h1>{draft.title}</h1><p>{draft.description || "检查课程、知识点、真实来源和前置关系后再发布。"}</p></div>
      <div className="architecture-header__actions"><span className={`status status--${draft.status}`}>{statusLabels[draft.status] ?? draft.status}</span>{draft.status === "published" && <button className="button button--secondary" disabled={createVersion.isPending} onClick={() => createVersion.mutate()}><RefreshCw size={16}/>创建新版本</button>}{draft.generation_status === "running" ? <button className="button button--secondary" disabled={cancelGeneration.isPending} onClick={() => cancelGeneration.mutate()}><Square size={15}/>停止分析</button> : <button className="button button--secondary" disabled={readOnly || action.isPending} onClick={() => { setGenerationPending(true); action.mutate(() => courseArchitectureApi.generate(id, draft.version, crypto.randomUUID()), { onSettled: () => setGenerationPending(false) }); }}><RefreshCw size={16}/>{draft.generation_status === "failed" ? "重新生成" : "分析资料"}</button>}<button className="button button--secondary" disabled={readOnly || action.isPending || draft.generation_status === "running"} onClick={() => action.mutate(() => courseArchitectureApi.validate(id, draft.version))}><CheckCircle2 size={16}/>检查质量</button><button className="button button--primary" disabled={draft.status !== "ready"} onClick={() => setPublishOpen(true)}><Send size={16}/>确认发布</button></div>
    </header>
    <section className="architecture-scope" aria-label="草案资料范围"><strong>资料范围</strong>{draft.materials.map((material) => <Link key={material.id} className={material.stale ? "is-invalid" : ""} to={`/materials/${material.material_id}`}><FileText size={15}/>{material.material_title}<small>{material.stale ? "资料已变化" : `${material.current_chunk_count} 个片段`}</small></Link>)}{draft.generation_mode === "curriculum_goal_only" && !draft.materials.length && <span className="muted">Goal-only · 未经资料验证</span>}</section>
    {draft.generation_status === "running" || draft.generation_progress.stage ? <section className="generation-progress" aria-label="生成进度"><div><strong>{draft.generation_progress.events?.at(-1)?.message ?? "正在分析资料结构"}</strong><small>{draft.generation_progress.completed_batches ?? 0} / {draft.generation_progress.total_batches ?? 0} 批</small></div><progress max={draft.generation_progress.total_batches ?? 1} value={draft.generation_progress.completed_batches ?? 0}/></section> : null}
    {draft.last_error_message && <div className="notice notice--warning">{draft.last_error_message}</div>}
    {formalCourseIds.length > 0 && <div className="notice notice--success">发布完成。{formalCourseIds.map((course) => <Link key={course} to="/courses">查看正式课程 #{course}</Link>)}</div>}
    <div className="architecture-workbench">
      <aside className="architecture-courses">
        <header><div><span>草案课程</span><strong>{draft.courses.length}</strong></div>{!readOnly && <button className="icon-button" aria-label="新增草案课程" onClick={() => setCourseOpen(true)}><Plus size={17}/></button>}</header>
        {draft.courses.map((course, index) => <button key={course.id} className={course.id === courseId ? "is-active" : ""} onClick={() => { setCourseId(course.id); setPointId(course.knowledge_points[0]?.id ?? null); }}><BookOpen size={17}/><span><strong>{course.title}</strong><small>{course.knowledge_points.length} 个知识点</small></span>{!readOnly && <span className="order-buttons"><i role="button" aria-label={`上移课程 ${course.title}`} onClick={(event) => { event.stopPropagation(); reorderCourses(draft, index, -1, action); }}><ArrowUp size={13}/></i><i role="button" aria-label={`下移课程 ${course.title}`} onClick={(event) => { event.stopPropagation(); reorderCourses(draft, index, 1, action); }}><ArrowDown size={13}/></i></span>}</button>)}
        {!draft.courses.length && <p className="muted">尚未建立课程候选。</p>}
      </aside>
      <main className="architecture-points">
        {selectedCourse ? <><header><div><h2>{selectedCourse.title}</h2><p>{selectedCourse.description || "尚未填写课程说明"}</p></div>{!readOnly && <div className="button-row"><button className="button button--quiet" onClick={() => editCourse(draft, selectedCourse, action)}>编辑课程</button><button className="button button--secondary" onClick={() => setPointOpen(true)}><Plus size={15}/>新增知识点</button></div>}</header>
          <ol>{selectedCourse.knowledge_points.map((point, index) => <li key={point.id} className={point.id === pointId ? "is-active" : ""} onClick={() => setPointId(point.id)}><span>{String(index + 1).padStart(2, "0")}</span><div><strong>{point.title}</strong><small>{point.sources.length ? `${point.sources.length} 条真实来源` : draft.generation_mode === "curriculum_goal_only" ? "未经资料验证" : "缺少来源"} · {point.origin === "generated" ? "资料生成" : point.origin === "curriculum" ? "课程提案" : "手动添加"}</small></div>{point.is_locked ? <Lock size={15}/> : null}{!readOnly && <span className="order-buttons"><button aria-label={`上移知识点 ${point.title}`} onClick={(event) => { event.stopPropagation(); reorderPoints(draft, selectedCourse, index, -1, action); }}><ArrowUp size={13}/></button><button aria-label={`下移知识点 ${point.title}`} onClick={(event) => { event.stopPropagation(); reorderPoints(draft, selectedCourse, index, 1, action); }}><ArrowDown size={13}/></button></span>}</li>)}</ol>
          {!selectedCourse.knowledge_points.length && <EmptyState title="这门草案课程还没有知识点" description="可以手动添加，或运行资料分析。"/>}</> : <EmptyState title="还没有草案课程" description="手动新增课程，或运行资料分析生成候选。"/>}
      </main>
      <aside className="architecture-inspector">
        <section><header><span>质量报告</span><strong className={draft.quality_report.blocker_count ? "is-invalid" : ""}>{draft.quality_report.blocker_count ?? 0} 个阻塞</strong></header><div className="quality-metrics"><span>来源覆盖<strong>{draft.quality_report.source_coverage ?? 0}%</strong></span><span>提醒<strong>{draft.quality_report.warning_count ?? 0}</strong></span></div>{draft.quality_report.issues?.slice(0, 6).map((issue) => <p className={`quality-issue quality-issue--${issue.severity}`} key={`${issue.code}-${issue.course_id}-${issue.knowledge_point_id}`}>{issue.message}</p>) ?? <p className="muted">运行质量检查后显示结果。</p>}</section>
        {selectedPoint && <PointInspector draft={draft} course={selectedCourse!} point={selectedPoint} allPoints={allPoints} readOnly={readOnly} action={action} onSource={() => setSourceOpen(true)}/>}
        <section><header><span>前置关系</span><GitBranch size={16}/></header>{draft.prerequisites.map((edge) => <article className="prerequisite-row" key={edge.id}><span>{edge.prerequisite_title}</span><ArrowRightMini/><span>{edge.dependent_title}</span>{!readOnly && <button aria-label="删除前置关系" onClick={() => action.mutate(() => courseArchitectureApi.removePrerequisite(id, edge.id, draft.version))}><Trash2 size={13}/></button>}</article>)}{!draft.prerequisites.length && <p className="muted">尚未建立前置关系。</p>}{!readOnly && allPoints.length > 1 && <PrerequisiteForm draft={draft} points={allPoints} action={action}/>}</section>
      </aside>
    </div>
    <Dialog open={courseOpen} title="新增草案课程" onClose={() => setCourseOpen(false)}><SimpleCreateForm label="课程名称" pending={action.isPending} onCancel={() => setCourseOpen(false)} onSubmit={(title) => action.mutate(() => courseArchitectureApi.addCourse(id, { version: draft.version, title, order_index: draft.courses.length }), { onSuccess: () => setCourseOpen(false) })}/></Dialog>
    <Dialog open={pointOpen} title="新增草案知识点" onClose={() => setPointOpen(false)}>{selectedCourse && <SimpleCreateForm label="知识点名称" pending={action.isPending} onCancel={() => setPointOpen(false)} onSubmit={(title) => action.mutate(() => courseArchitectureApi.addPoint(id, { version: draft.version, draft_course_id: selectedCourse.id, title, order_index: selectedCourse.knowledge_points.length }), { onSuccess: () => setPointOpen(false) })}/>}</Dialog>
    <Dialog open={sourceOpen} title="添加真实来源" onClose={() => setSourceOpen(false)}>{selectedPoint && <SourceForm draft={draft} point={selectedPoint} pending={action.isPending} onCancel={() => setSourceOpen(false)} onSubmit={(materialId, chunkId) => action.mutate(() => courseArchitectureApi.addSource(id, selectedPoint.id, { version: draft.version, material_id: materialId, material_chunk_id: chunkId, source_role: "primary" }), { onSuccess: () => setSourceOpen(false) })}/>}</Dialog>
    <Dialog open={publishOpen} title="确认发布课程架构" onClose={() => setPublishOpen(false)}><div className="publish-confirm"><p>将为“{draft.learning_goal_title}”创建以下正式数据：</p><dl><div><dt>课程</dt><dd>{draft.courses.length}</dd></div><div><dt>知识点</dt><dd>{allPoints.length}</dd></div><div><dt>资料关联</dt><dd>{new Set(draft.courses.flatMap((course) => course.knowledge_points.flatMap((point) => point.sources.map((source) => `${course.id}-${source.material_id}`)))).size}</dd></div><div><dt>来源片段</dt><dd>{sourceCount}</dd></div><div><dt>前置关系</dt><dd>{draft.prerequisites.length}</dd></div></dl><p className="muted">发布后草案只读；失败不会留下半套课程。</p><div className="form-actions"><button className="button button--secondary" onClick={() => setPublishOpen(false)}>取消</button><button className="button button--primary" disabled={publish.isPending} onClick={() => publish.mutate()}>{publish.isPending ? "正在发布" : "确认发布"}</button></div></div></Dialog>
  </div>;
}

type DraftAction = UseMutationResult<CourseArchitectureDraft, Error, () => Promise<CourseArchitectureDraft>>;

function PointInspector({ draft, course, point, allPoints, readOnly, action, onSource }: { draft: CourseArchitectureDraft; course: DraftCourse; point: DraftKnowledgePoint; allPoints: Array<DraftKnowledgePoint & { courseTitle: string }>; readOnly: boolean; action: DraftAction; onSource: () => void }) {
  const [moveTarget, setMoveTarget] = useState(course.id);
  const [mergeTarget, setMergeTarget] = useState("");
  return <section><header><span>知识点详情</span>{point.is_locked ? <Lock size={16}/> : <LockOpen size={16}/>}</header><h3>{point.title}</h3><p>{point.description || "尚未填写说明"}</p><div className="source-chip-list">{point.sources.map((source) => <Link key={source.id} to={source.context_url}><FileText size={14}/><span>{source.material_title}<small>{source.source_locator}</small>{source.quoted_text && <p>{source.quoted_text}</p>}</span></Link>)}</div>{!point.sources.length && <p className={draft.generation_mode === "curriculum_goal_only" ? "muted" : "is-invalid"}>{draft.generation_mode === "curriculum_goal_only" ? "该知识点尚未经过资料验证，请人工审查。" : "发布前需要添加真实资料片段。"}</p>}{!readOnly && <div className="inspector-actions"><button className="button button--secondary" onClick={onSource}>添加来源</button><button className="button button--quiet" onClick={() => editPoint(draft, point, action)}>编辑</button><button className="button button--quiet" onClick={() => action.mutate(() => courseArchitectureApi.updatePoint(draft.id, point.id, { version: draft.version, is_locked: !point.is_locked }))}>{point.is_locked ? "解除锁定" : "锁定"}</button><label>移动到<select value={moveTarget} onChange={(event) => setMoveTarget(Number(event.target.value))}>{draft.courses.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label><button className="button button--quiet" disabled={moveTarget === course.id} onClick={() => action.mutate(() => courseArchitectureApi.movePoint(draft.id, { version: draft.version, knowledge_point_id: point.id, target_course_id: moveTarget, order_index: 0 }))}>移动</button><label>合并<select value={mergeTarget} onChange={(event) => setMergeTarget(event.target.value)}><option value="">选择知识点</option>{allPoints.filter((item) => item.draft_course_id === course.id && item.id !== point.id).map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label><button className="button button--quiet" disabled={!mergeTarget} onClick={() => action.mutate(() => courseArchitectureApi.mergePoints(draft.id, { version: draft.version, keep_knowledge_point_id: point.id, merge_knowledge_point_ids: [Number(mergeTarget)] }))}><Merge size={14}/>合并</button><button className="button button--danger" onClick={() => { if (window.confirm(`删除知识点“${point.title}”？`)) action.mutate(() => courseArchitectureApi.removePoint(draft.id, point.id, draft.version)); }}><Trash2 size={14}/>删除</button></div>}</section>;
}

function SimpleCreateForm({ label, pending, onCancel, onSubmit }: { label: string; pending: boolean; onCancel: () => void; onSubmit: (title: string) => void }) { const [title, setTitle] = useState(""); return <form className="form-stack" onSubmit={(event: FormEvent) => { event.preventDefault(); onSubmit(title); }}><label className="field"><span>{label}</span><input autoFocus required value={title} onChange={(event) => setTitle(event.target.value)}/></label><div className="form-actions"><button type="button" className="button button--secondary" onClick={onCancel}>取消</button><button className="button button--primary" disabled={pending || !title.trim()}>添加</button></div></form>; }

function SourceForm({ draft, point, pending, onCancel, onSubmit }: { draft: CourseArchitectureDraft; point: DraftKnowledgePoint; pending: boolean; onCancel: () => void; onSubmit: (materialId: number, chunkId: number) => void }) { const [materialId, setMaterialId] = useState(draft.materials[0]?.material_id ?? 0); const [chunkId, setChunkId] = useState(0); const chunks = useQuery({ queryKey: ["draft-source-chunks", materialId], queryFn: () => materialsApi.chunks(materialId, 1, 20), enabled: Boolean(materialId) }); const chunkItems = Array.isArray(chunks.data?.items) ? chunks.data.items : []; useEffect(() => { const items = chunks.data?.items; setChunkId(Array.isArray(items) ? items[0]?.id ?? 0 : 0); }, [chunks.data]); return <form className="form-stack" onSubmit={(event) => { event.preventDefault(); onSubmit(materialId, chunkId); }}><p>为“{point.title}”选择草案范围内的真实资料片段。</p><label className="field"><span>资料</span><select value={materialId} onChange={(event) => setMaterialId(Number(event.target.value))}>{draft.materials.map((material) => <option value={material.material_id} key={material.id}>{material.material_title}</option>)}</select></label><label className="field"><span>资料片段</span><select aria-label="选择来源片段" value={chunkId} onChange={(event) => setChunkId(Number(event.target.value))}>{chunkItems.map((chunk) => <option value={chunk.id} key={chunk.id}>{chunk.section_title || `片段 ${chunk.chunk_index + 1}`} · {chunk.content.slice(0, 60)}</option>)}</select></label><div className="form-actions"><button type="button" className="button button--secondary" onClick={onCancel}>取消</button><button className="button button--primary" disabled={pending || !chunkId}>添加来源</button></div></form>; }

function PrerequisiteForm({ draft, points, action }: { draft: CourseArchitectureDraft; points: Array<DraftKnowledgePoint & { courseTitle: string }>; action: DraftAction }) { const [source, setSource] = useState(points[0]?.id ?? 0); const [target, setTarget] = useState(points[1]?.id ?? 0); return <div className="prerequisite-form"><select aria-label="前置知识点" value={source} onChange={(event) => setSource(Number(event.target.value))}>{points.map((point) => <option value={point.id} key={point.id}>{point.courseTitle} · {point.title}</option>)}</select><select aria-label="后续知识点" value={target} onChange={(event) => setTarget(Number(event.target.value))}>{points.map((point) => <option value={point.id} key={point.id}>{point.courseTitle} · {point.title}</option>)}</select><button className="button button--secondary" disabled={!source || !target || source === target} onClick={() => action.mutate(() => courseArchitectureApi.addPrerequisite(draft.id, { version: draft.version, prerequisite_knowledge_point_id: source, dependent_knowledge_point_id: target }))}>添加关系</button></div>; }

function reorderCourses(draft: CourseArchitectureDraft, index: number, direction: number, action: DraftAction) { const target = index + direction; if (target < 0 || target >= draft.courses.length) return; const rows = [...draft.courses]; [rows[index], rows[target]] = [rows[target], rows[index]]; action.mutate(() => courseArchitectureApi.reorderCourses(draft.id, draft.version, rows.map((item, order_index) => ({ id: item.id, order_index })))); }
function reorderPoints(draft: CourseArchitectureDraft, course: DraftCourse, index: number, direction: number, action: DraftAction) { const target = index + direction; if (target < 0 || target >= course.knowledge_points.length) return; const rows = [...course.knowledge_points]; [rows[index], rows[target]] = [rows[target], rows[index]]; action.mutate(() => courseArchitectureApi.reorderPoints(draft.id, draft.version, rows.map((item, order_index) => ({ id: item.id, order_index })))); }
function editCourse(draft: CourseArchitectureDraft, course: DraftCourse, action: DraftAction) { const title = window.prompt("课程名称", course.title); if (title?.trim()) action.mutate(() => courseArchitectureApi.updateCourse(draft.id, course.id, { version: draft.version, title: title.trim(), is_locked: true })); }
function editPoint(draft: CourseArchitectureDraft, point: DraftKnowledgePoint, action: DraftAction) { const title = window.prompt("知识点名称", point.title); if (title?.trim()) action.mutate(() => courseArchitectureApi.updatePoint(draft.id, point.id, { version: draft.version, title: title.trim(), is_locked: true })); }
function ArrowRightMini() { return <span aria-hidden="true">→</span>; }
