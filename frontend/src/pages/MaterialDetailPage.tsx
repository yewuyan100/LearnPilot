import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArchiveRestore, ChevronLeft, ChevronRight, FileSearch, FolderInput, MessageSquareText, NotebookPen } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { activitiesApi, materialsApi, materialLearningApi, notesApi } from "../api/resources";
import { MaterialLinkDialog } from "../components/MaterialLinkDialog";
import { materialRelationLabel } from "../components/material-link-labels";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { useToast } from "../components/toast-context";
import { formatDateTime } from "../utils/format";
import { NotFoundPage } from "./NotFoundPage";

const materialDetailViews = [
  { id: "content", label: "内容" },
  { id: "learning", label: "学习与关联" },
] as const;

const materialChunkPageSize = 10;

type MaterialDetailView = typeof materialDetailViews[number]["id"];

function isMaterialDetailView(value: string | null): value is MaterialDetailView {
  return materialDetailViews.some((view) => view.id === value);
}

function MaterialContentPagination({
  page,
  pages,
  total,
  position,
  onPageChange,
}: {
  page: number;
  pages: number;
  total: number;
  position: "顶部" | "底部";
  onPageChange: (page: number) => void;
}) {
  return <nav className="material-content-pagination" aria-label={`资料内容分页（${position}）`}>
    <span>第 {page}/{Math.max(pages, 1)} 页 · 共 {total} 个内容片段</span>
    <div className="button-row">
      <button
        className="button button--secondary"
        type="button"
        aria-label="上一页资料内容"
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
      ><ChevronLeft size={16}/>上一页</button>
      <button
        className="button button--secondary"
        type="button"
        aria-label="下一页资料内容"
        disabled={page >= pages}
        onClick={() => onPageChange(page + 1)}
      >下一页<ChevronRight size={16}/></button>
    </div>
  </nav>;
}

export function MaterialDetailPage() {
  const id = Number(useParams().id);
  const validId = Number.isInteger(id) && id > 0;
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedView = searchParams.get("view");
  const activeView: MaterialDetailView = isMaterialDetailView(requestedView) ? requestedView : "content";
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [linkOpen, setLinkOpen] = useState(false);
  const [chunkPage, setChunkPage] = useState(1);

  useEffect(() => setChunkPage(1), [id]);

  const material = useQuery({ queryKey: ["material", id], queryFn: () => materialsApi.get(id), enabled: validId });
  const links = useQuery({ queryKey: ["material-learning-links", String(id)], queryFn: () => materialLearningApi.list(id), enabled: validId });
  const notes = useQuery({ queryKey: ["notes", "material", id], queryFn: () => notesApi.list({ entityType: "material", entityId: id }), enabled: validId });
  const activities = useQuery({ queryKey: ["learning-activities"], queryFn: () => activitiesApi.list(), enabled: validId });
  const contentAvailable = material.data?.ingestion_status === "completed" && material.data.chunk_count > 0;
  const chunks = useQuery({
    queryKey: ["material-chunks", id, chunkPage],
    queryFn: () => materialsApi.chunks(id, chunkPage, materialChunkPageSize),
    enabled: validId && activeView === "content" && contentAvailable,
  });
  const unarchive = useMutation({
    mutationFn: () => materialsApi.unarchive(id),
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ["material"] }); await queryClient.invalidateQueries({ queryKey: ["materials"] }); showToast("资料已回到收件箱", "success"); },
    onError: (error: Error) => showToast(error.message, "error"),
  });

  if (!validId) return <div className="page"><NotFoundPage /></div>;
  if (material.isLoading) return <div className="page"><LoadingState label="正在读取资料详情"/></div>;
  if (material.isError) return <div className="page"><ErrorState message={material.error.message}/></div>;

  const item = material.data!;
  const relatedActivities = (activities.data?.items ?? []).filter((activity) => {
    return (activity.source_scope.material_ids as number[] | undefined)?.includes(id);
  });
  const ingestionFailed = item.ingestion_status === "failed";
  const ingestionProcessing = item.ingestion_status === "processing";
  const contentState = ingestionFailed ? "处理失败" : ingestionProcessing ? "正在整理" : item.ingestion_status === "completed" ? "已导入" : "等待处理";
  const questionState = item.indexing_status === "completed" ? "可用于问答" : item.indexing_status === "failed" ? "暂不可用" : item.indexing_status === "indexing" ? "正在准备" : "等待索引";
  const orderedChunks = [...(chunks.data?.items ?? [])].sort((left, right) => left.chunk_index - right.chunk_index);
  const openView = (view: MaterialDetailView) => {
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set("view", view);
    setSearchParams(nextParams);
  };

  return <div className="page material-detail-page">
    <header className="page-header page-header--split material-detail-header">
      <div><h1>{item.title || item.original_filename}</h1><p>{item.original_filename}</p></div>
      <div className="button-row"><button className="button button--primary" onClick={() => setLinkOpen(true)}><FolderInput size={16}/>管理关联</button><Link className="button button--secondary" to={`/knowledge?tab=notes&new=1&note_type=material&entity_type=material&entity_id=${id}`}><NotebookPen size={16}/>记录笔记</Link>{item.archived_at && <button className="button button--secondary" onClick={() => unarchive.mutate()}><ArchiveRestore size={16}/>移出归档</button>}</div>
    </header>

    <dl className="material-metadata" aria-label="资料状态">
      <div><dt>资料内容</dt><dd>{contentState}</dd></div>
      <div><dt>资料问答</dt><dd>{questionState}</dd></div>
      <div><dt>提取内容</dt><dd>{item.chunk_count ? `${item.chunk_count} 个片段` : "暂无片段"}</dd></div>
      <div><dt>导入时间</dt><dd>{formatDateTime(item.created_at)}</dd></div>
    </dl>

    <nav className="page-tabs material-detail-tabs" aria-label={`${item.title || item.original_filename} 视图`}>
      {materialDetailViews.map((view) => <button
        key={view.id}
        type="button"
        className={activeView === view.id ? "is-active" : ""}
        aria-current={activeView === view.id ? "page" : undefined}
        onClick={() => openView(view.id)}
      >{view.label}</button>)}
    </nav>

    {activeView === "content" && <section className="material-content-view" data-material-view="content" aria-labelledby="material-content-title">
      <header className="material-content-heading">
        <div><h2 id="material-content-title">资料内容</h2><p>以下为提取文本，按资料顺序显示。</p></div>
        {chunks.data && chunks.data.pages > 0 && <MaterialContentPagination page={chunks.data.page} pages={chunks.data.pages} total={chunks.data.total} position="顶部" onPageChange={setChunkPage}/>}
      </header>
      {ingestionProcessing ? <LoadingState label="资料正在准备，完成后会显示提取内容"/> : ingestionFailed ? <EmptyState title="资料内容处理失败" description={item.error_message || "请稍后重新处理资料，再查看提取内容。"}/> : item.ingestion_status !== "completed" ? <EmptyState title="资料内容尚未准备好" description="完成资料处理后，这里会显示真实提取内容。"/> : item.chunk_count <= 0 ? <EmptyState title="当前资料暂无可显示内容" description="资料已完成处理，但没有返回可阅读的提取文本。"/> : chunks.isLoading ? <LoadingState label="正在读取资料内容"/> : chunks.isError ? <ErrorState message={`内容暂时无法读取：${chunks.error.message}`} onRetry={() => chunks.refetch()}/> : !orderedChunks.length ? <EmptyState title="当前资料暂无可显示内容" description="当前分页没有返回可阅读的提取文本。"/> : <>
        <div className="material-content-list">
          {orderedChunks.map((chunk) => <article className="material-content-chunk" data-chunk-index={chunk.chunk_index} key={chunk.id}>
            {(chunk.page_number !== null || chunk.section_title) && <header>
              {chunk.page_number !== null && <span>第 {chunk.page_number} 页</span>}
              {chunk.section_title && <strong>{chunk.section_title}</strong>}
            </header>}
            <p>{chunk.content}</p>
          </article>)}
        </div>
        {chunks.data && chunks.data.pages > 0 && <MaterialContentPagination page={chunks.data.page} pages={chunks.data.pages} total={chunks.data.total} position="底部" onPageChange={setChunkPage}/>}
      </>}
    </section>}

    {activeView === "learning" && <div className="material-learning-view" data-material-view="learning">
      <section className="section-card"><header className="section-heading"><div><h2>关联事项</h2><p>展示你确认的直接关系；路线和步骤关系只作为事项内的内容上下文。</p></div></header>{links.isLoading ? <LoadingState label="正在读取资料关联"/> : links.isError ? <ErrorState message={links.error.message} onRetry={() => links.refetch()}/> : links.data?.length ? <div className="ownership-list">{links.data.map((link) => <article key={link.id}><div><strong>{link.target_title}</strong><p>{link.target_type === "learning_goal" ? "事项" : link.target_type === "course" ? "路线" : "步骤"}</p></div><span>{materialRelationLabel[link.relation_type]}</span></article>)}</div> : <EmptyState title="尚未关联事项" description="从待整理或这里选择一件事项、路线或步骤。" action={<button className="button button--primary" onClick={() => setLinkOpen(true)}>建立关联</button>}/>}</section>
      <div className="detail-columns"><section className="section-card"><header className="section-heading"><div><h2>基于内容核对</h2><p>限定到这份资料提问，不会加入范围外来源。</p></div></header><div className="button-row"><Link className="button button--secondary" to={`/knowledge?tab=qa&scope=material&material_id=${id}`}><MessageSquareText size={16}/>限定此资料提问</Link><Link className="text-link" to={`/ai?material_id=${id}`}>带着资料进入 AI 协作</Link></div></section><section className="section-card"><header className="section-heading"><div><h2>练习与反馈</h2><p>由这份资料参与准备的真实练习。</p></div></header>{activities.isLoading ? <LoadingState label="正在读取相关练习"/> : activities.isError ? <ErrorState message={activities.error.message} onRetry={() => activities.refetch()}/> : relatedActivities.length ? relatedActivities.map((activity) => <Link className="workspace-row" key={activity.id} to={`/activities/${activity.id}`}><FileSearch size={16}/><div><strong>{activity.title}</strong><small>{activity.question_count} 题</small></div></Link>) : <p className="muted">暂无由这份资料准备的练习。</p>}</section></div>
      <section className="section-card"><header className="section-heading"><div><h2>相关笔记</h2><p>关联到这份资料的记录和摘录。</p></div></header>{notes.isLoading ? <LoadingState label="正在读取相关笔记"/> : notes.isError ? <ErrorState message={notes.error.message} onRetry={() => notes.refetch()}/> : notes.data?.items.length ? notes.data.items.slice(0, 5).map((note) => <Link className="workspace-row" key={note.id} to={`/knowledge?tab=notes&note=${note.id}`}><NotebookPen size={16}/><div><strong>{note.title}</strong><small>{formatDateTime(note.updated_at)}</small></div></Link>) : <p className="muted">还没有关联笔记。</p>}</section>
      <details className="material-technical-details"><summary>技术信息</summary><dl><div><dt>内容处理</dt><dd>{item.ingestion_status}</dd></div><div><dt>检索准备</dt><dd>{item.indexing_status}</dd></div><div><dt>内容片段</dt><dd>{item.chunk_count}</dd></div><div><dt>可检索片段</dt><dd>{item.indexed_chunk_count}</dd></div><div><dt>处理完成</dt><dd>{formatDateTime(item.processed_at)}</dd></div><div><dt>检索更新</dt><dd>{formatDateTime(item.indexed_at)}</dd></div></dl></details>
    </div>}

    <MaterialLinkDialog open={linkOpen} materialIds={[id]} onClose={() => setLinkOpen(false)}/>
  </div>;
}
