import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, BookOpenCheck, FileText, Plus } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { courseArchitectureApi, goalsApi, materialsApi } from "../api/resources";
import { Dialog } from "../components/Dialog";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { useToast } from "../components/toast-context";
import type { Material } from "../types";

const statusLabels: Record<string, string> = {
  draft: "编辑中",
  generating: "分析中",
  review_required: "需要检查",
  ready: "可发布",
  publishing: "正在发布",
  published: "已发布",
  failed: "生成失败",
  archived: "已归档",
};

export function CourseArchitectureDraftsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [open, setOpen] = useState(false);
  const drafts = useQuery({ queryKey: ["course-architecture-drafts"], queryFn: () => courseArchitectureApi.list() });
  const goals = useQuery({ queryKey: ["goals"], queryFn: goalsApi.list });
  const materials = useQuery({ queryKey: ["materials", "", ""], queryFn: () => materialsApi.list() });
  const create = useMutation({
    mutationFn: courseArchitectureApi.create,
    onSuccess: async (draft) => {
      await queryClient.invalidateQueries({ queryKey: ["course-architecture-drafts"] });
      setOpen(false);
      navigate(`/course-architecture/drafts/${draft.id}`);
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });

  if (drafts.isLoading || goals.isLoading || materials.isLoading) return <LoadingState label="正在读取课程草案" />;
  if (drafts.isError || goals.isError || materials.isError) return <ErrorState message={(drafts.error ?? goals.error ?? materials.error)!.message} onRetry={() => drafts.refetch()} />;
  return <div className="page">
    <header className="page-header page-header--split">
      <div><span className="page-kicker">课程</span><h1>课程草案</h1><p>从已处理资料建立可追溯草案，检查并确认后再创建正式课程。</p></div>
      <button className="button button--primary" onClick={() => setOpen(true)}><Plus size={16}/>新建课程架构</button>
    </header>
    <nav className="page-tabs" aria-label="课程视图">
      <Link to="/courses">正式课程</Link><Link className="is-active" to="/course-architecture/drafts">课程草案</Link>
    </nav>
    {!drafts.data?.items.length ? <EmptyState title="还没有课程架构草案" description="选择一个目标和至少一份可用资料，先建立可编辑草案。" action={<button className="button button--primary" onClick={() => setOpen(true)}>新建课程架构</button>}/> :
      <section className="architecture-draft-list" aria-label="课程草案列表">
        {drafts.data.items.map((draft) => <Link to={`/course-architecture/drafts/${draft.id}`} key={draft.id} className="architecture-draft-card">
          <BookOpenCheck size={20}/><div><header><h2>{draft.title}</h2><span className={`status status--${draft.status}`}>{statusLabels[draft.status] ?? draft.status}</span></header><p>{draft.learning_goal_title}</p><small>{draft.material_count} 份资料 · {draft.course_count} 门候选课程 · {draft.knowledge_point_count} 个知识点</small></div><ArrowRight size={18}/>
        </Link>)}
      </section>}
    <Dialog open={open} title="新建课程架构" onClose={() => setOpen(false)}>
      <DraftCreateForm
        goals={goals.data ?? []}
        materials={materials.data ?? []}
        pending={create.isPending}
        onCancel={() => setOpen(false)}
        onSubmit={(value) => create.mutate(value)}
      />
    </Dialog>
  </div>;
}

function DraftCreateForm({ goals, materials, pending, onCancel, onSubmit }: {
  goals: Array<{ id: number; title: string }>;
  materials: Material[];
  pending: boolean;
  onCancel: () => void;
  onSubmit: (value: { learning_goal_id: number; material_ids: number[]; title?: string; description?: string }) => void;
}) {
  const [goalId, setGoalId] = useState(goals[0]?.id ?? 0);
  const [selected, setSelected] = useState<number[]>([]);
  const [title, setTitle] = useState("");
  const available = useMemo(() => materials.filter((item) => item.ingestion_status === "completed" && item.indexing_status === "completed" && item.chunk_count > 0 && !item.archived_at && item.deletion_status === "active"), [materials]);
  const unavailable = materials.filter((item) => !available.some((candidate) => candidate.id === item.id));
  return <form className="form-stack" onSubmit={(event: FormEvent) => { event.preventDefault(); onSubmit({ learning_goal_id: goalId, material_ids: selected, title: title.trim() || undefined }); }}>
    <label className="field"><span>学习目标</span><select aria-label="选择草案目标" required value={goalId} onChange={(event) => setGoalId(Number(event.target.value))}>{goals.map((goal) => <option key={goal.id} value={goal.id}>{goal.title}</option>)}</select></label>
    <label className="field"><span>草案名称（可选）</span><input value={title} maxLength={200} onChange={(event) => setTitle(event.target.value)} placeholder="默认使用目标名称"/></label>
    <fieldset className="draft-material-options"><legend>选择资料</legend>
      {available.map((material) => <label key={material.id}><input type="checkbox" checked={selected.includes(material.id)} onChange={(event) => setSelected(event.target.checked ? [...selected, material.id] : selected.filter((id) => id !== material.id))}/><FileText size={16}/><span><strong>{material.title || material.original_filename}</strong><small>已处理 · 已索引 · {material.chunk_count} 个片段</small></span></label>)}
      {!available.length && <p className="muted">当前没有可用于分析的资料，请先完成资料处理和索引。</p>}
      {unavailable.map((material) => <label className="is-disabled" key={material.id}><input type="checkbox" disabled/><FileText size={16}/><span><strong>{material.title || material.original_filename}</strong><small>暂不可用：需要完成处理、索引且不能归档</small></span></label>)}
    </fieldset>
    <div className="form-actions"><button type="button" className="button button--secondary" onClick={onCancel}>取消</button><button className="button button--primary" disabled={pending || !goalId || !selected.length}>{pending ? "正在创建" : "创建草案"}</button></div>
  </form>;
}
