import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpenCheck, FilePlus2, MessageSquareText, NotebookPen, Search, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { activitiesApi, coursesApi, knowledgePointSourcesApi, materialLearningApi, notesApi } from "../api/resources";
import { Dialog } from "../components/Dialog";
import { EffectiveMaterials } from "../components/EffectiveMaterials";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { TargetMaterialPicker } from "../components/TargetMaterialPicker";
import { useToast } from "../components/toast-context";
import type { EffectiveMaterial, SourceChunk } from "../types";
import { formatDateTime } from "../utils/format";

export function KnowledgePointDetailPage() {
  const id = Number(useParams().id);
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [materialOpen, setMaterialOpen] = useState(false);
  const [sourceOpen, setSourceOpen] = useState(false);
  const point = useQuery({ queryKey: ["knowledge-point", id], queryFn: () => coursesApi.getPoint(id), enabled: Number.isFinite(id) });
  const course = useQuery({ queryKey: ["course-for-point", point.data?.course_id], queryFn: () => coursesApi.get(point.data!.course_id), enabled: !!point.data });
  const materials = useQuery({ queryKey: ["effective-materials", "knowledge_point", id], queryFn: () => materialLearningApi.pointMaterials(id), enabled: Number.isFinite(id) });
  const sources = useQuery({ queryKey: ["knowledge-point-sources", id], queryFn: () => knowledgePointSourcesApi.list(id), enabled: Number.isFinite(id) });
  const notes = useQuery({ queryKey: ["notes", "knowledge_point", id], queryFn: () => notesApi.list({ entityType: "knowledge_point", entityId: id }), enabled: Number.isFinite(id) });
  const activities = useQuery({ queryKey: ["learning-activities"], queryFn: () => activitiesApi.list(), enabled: Number.isFinite(id) });
  const removeSource = useMutation({
    mutationFn: (sourceId: number) => knowledgePointSourcesApi.remove(id, sourceId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["knowledge-point-sources", id] }),
    onError: (error: Error) => showToast(error.message, "error"),
  });
  if (point.isLoading || course.isLoading || materials.isLoading || sources.isLoading || notes.isLoading || activities.isLoading) return <div className="page"><LoadingState label="正在读取知识点详情"/></div>;
  if (point.isError || materials.isError || sources.isError) return <div className="page"><ErrorState message={(point.error ?? materials.error ?? sources.error)!.message}/></div>;
  const relatedActivities = (activities.data?.items ?? []).filter((item) => item.knowledge_point_id === id);
  return <div className="page knowledge-point-detail">
    <header className="page-header page-header--split"><div><p className="page-kicker">{course.data?.title ?? "课程知识点"}</p><h1>{point.data!.title}</h1><p>{point.data!.description || "尚未填写知识点说明。"}</p></div><div className="button-row"><Link className="button button--primary" to={`/knowledge?tab=qa&scope=knowledge_point&knowledge_point_id=${id}`}><MessageSquareText size={16}/>限定范围问答</Link><Link className="button button--secondary" to={`/notes?new=1&note_type=knowledge_point&entity_type=knowledge_point&entity_id=${id}`}><NotebookPen size={16}/>创建知识点笔记</Link></div></header>
    <section className="section-card"><header className="section-heading"><div><h2>关联资料</h2><p>直接资料与从课程、目标继承的资料会明确区分。</p></div><button className="button button--secondary" onClick={() => setMaterialOpen(true)}><FilePlus2 size={16}/>添加现有资料</button></header><EffectiveMaterials items={materials.data ?? []} emptyText="先把资料关联到此知识点、所属课程或学习目标。"/></section>
    <section className="section-card"><header className="section-heading"><div><h2>来源片段</h2><p>保存可回到原始资料片段的来源，不复制整份资料。</p></div><button className="button button--secondary" disabled={!materials.data?.length} onClick={() => setSourceOpen(true)}><Search size={16}/>从资料选择片段</button></header>{sources.data?.length ? <div className="source-evidence-list">{sources.data.map((source) => <article key={source.id}><div><strong>{source.material_title}</strong><small>{source.source_locator || "资料来源"}</small><p>{source.quoted_text || "整份资料作为来源"}</p></div><div><Link className="text-link" to={source.context_url}>打开资料上下文</Link><button className="icon-button icon-button--danger" aria-label={`删除来源 ${source.id}`} onClick={() => removeSource.mutate(source.id)}><Trash2 size={16}/></button></div></article>)}</div> : <EmptyState title="还没有来源片段" description="在有效资料中搜索并选择一个具体片段，建立可追溯来源。"/>}</section>
    <div className="detail-columns"><section className="section-card"><header className="section-heading"><div><h2>相关活动</h2><p>与此知识点关联的真实学习活动。</p></div></header>{relatedActivities.length ? relatedActivities.slice(0, 5).map((activity) => <Link className="workspace-row" key={activity.id} to={`/activities/${activity.id}`}><BookOpenCheck size={16}/><div><strong>{activity.title}</strong><small>{activity.question_count} 题</small></div></Link>) : <p className="muted">还没有相关活动。</p>}</section><section className="section-card"><header className="section-heading"><div><h2>相关笔记</h2><p>知识点学习过程中保存的记录。</p></div></header>{notes.data?.items.length ? notes.data.items.slice(0, 5).map((note) => <Link className="workspace-row" key={note.id} to={`/notes?id=${note.id}`}><NotebookPen size={16}/><div><strong>{note.title}</strong><small>{formatDateTime(note.updated_at)}</small></div></Link>) : <p className="muted">还没有相关笔记。</p>}</section></div>
    <TargetMaterialPicker open={materialOpen} targetType="knowledge_point" targetId={id} targetTitle={point.data!.title} onClose={() => setMaterialOpen(false)}/>
    <SourcePicker open={sourceOpen} pointId={id} materials={materials.data ?? []} onClose={() => setSourceOpen(false)}/>
  </div>;
}

function SourcePicker({ open, pointId, materials, onClose }: { open: boolean; pointId: number; materials: EffectiveMaterial[]; onClose: () => void }) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [materialId, setMaterialId] = useState("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<SourceChunk | null>(null);
  const chunks = useQuery({ queryKey: ["source-chunks", pointId, materialId, search], queryFn: () => knowledgePointSourcesApi.chunks(pointId, Number(materialId), search), enabled: open && !!materialId });
  const save = useMutation({
    mutationFn: () => knowledgePointSourcesApi.create(pointId, { material_id: Number(materialId), material_chunk_id: selected!.id, source_type: "chunk", source_locator: selected!.source_locator, quoted_text: selected!.content }),
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ["knowledge-point-sources", pointId] }); showToast("来源片段已保存", "success"); setSelected(null); onClose(); },
    onError: (error: Error) => showToast(error.message, "error"),
  });
  return <Dialog open={open} title="从关联资料添加来源" onClose={onClose}><div className="source-picker"><div className="form-grid"><label className="field"><span>资料</span><select aria-label="来源资料" value={materialId} onChange={(event) => { setMaterialId(event.target.value); setSelected(null); }}><option value="">选择关联资料</option>{materials.map((item) => <option key={item.material_id} value={item.material_id}>{item.material_title}</option>)}</select></label><label className="field"><span>搜索片段</span><input aria-label="搜索来源片段" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="章节或正文关键词"/></label></div>{chunks.isLoading ? <LoadingState label="正在搜索片段"/> : <div className="source-picker__results">{chunks.data?.items.map((chunk) => <button key={chunk.id} className={selected?.id === chunk.id ? "is-selected" : ""} onClick={() => setSelected(chunk)}><strong>{chunk.source_locator}</strong><p>{chunk.content}</p></button>)}{materialId && !chunks.data?.items.length && <p className="muted">没有找到匹配片段。</p>}</div>}<div className="form-actions"><button className="button button--secondary" onClick={onClose}>取消</button><button className="button button--primary" disabled={!selected || save.isPending} onClick={() => save.mutate()}>添加来源</button></div></div></Dialog>;
}
