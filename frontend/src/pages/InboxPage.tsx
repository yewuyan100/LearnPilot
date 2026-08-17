import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, FileInput, FileText, FolderInput, NotebookPen, RefreshCw, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { materialsApi, materialLearningApi } from "../api/resources";
import { MaterialLinkDialog } from "../components/MaterialLinkDialog";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { useToast } from "../components/toast-context";
import { formatDateTime } from "../utils/format";

export function InboxPage({ embedded = false }: { embedded?: boolean }) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [linkIds, setLinkIds] = useState<number[]>([]);
  const materials = useQuery({ queryKey: ["materials", "", ""], queryFn: () => materialsApi.list() });
  const links = useQuery({ queryKey: ["material-learning-links"], queryFn: () => materialLearningApi.all() });
  const refresh = async () => Promise.all([
    queryClient.invalidateQueries({ queryKey: ["materials"] }),
    queryClient.invalidateQueries({ queryKey: ["material-learning-links"] }),
  ]);
  const processMaterial = useMutation({
    mutationFn: materialsApi.process,
    onSuccess: async () => { await refresh(); showToast("资料已完成处理和索引", "success"); },
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const archive = useMutation({
    mutationFn: materialsApi.archiveBulk,
    onSuccess: async (result) => { setSelectedIds([]); await refresh(); showToast(`${result.archived_ids.length} 条资料已归档`, "success"); },
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const remove = useMutation({
    mutationFn: materialsApi.remove,
    onSuccess: async () => { await refresh(); showToast("资料已删除，索引和学习关系已同步更新", "success"); },
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const retryDelete = useMutation({
    mutationFn: materialsApi.retryDelete,
    onSuccess: refresh,
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const linksByMaterial = useMemo(() => {
    const map = new Map<number, typeof links.data>();
    for (const link of links.data ?? []) map.set(link.material_id, [...(map.get(link.material_id) ?? []), link]);
    return map;
  }, [links]);

  if (materials.isLoading || links.isLoading) return <div className={embedded ? "inbox-page--embedded" : "page"}><LoadingState label="正在整理知识收件箱" /></div>;
  if (materials.isError || links.isError) return <div className={embedded ? "inbox-page--embedded" : "page"}><ErrorState message={(materials.error ?? links.error)!.message} onRetry={() => { materials.refetch(); links.refetch(); }} /></div>;
  const items = [...(materials.data ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at));
  const pending = items.filter((item) => item.ingestion_status !== "completed" && !item.archived_at).length;
  const failed = items.filter((item) => item.ingestion_status === "failed" || item.indexing_status === "failed" || item.deletion_status === "failed").length;
  const unclassified = items.filter((item) => !item.archived_at && item.ingestion_status === "completed" && item.indexing_status === "completed" && !(linksByMaterial.get(item.id)?.length)).length;
  const classified = items.filter((item) => !item.archived_at && !!linksByMaterial.get(item.id)?.length).length;

  return <div className={embedded ? "inbox-page inbox-page--embedded" : "page inbox-page"}>
    {!embedded && <header className="page-header page-header--split"><div><h1>知识收件箱</h1><p>处理本地资料，并确认它与哪件事项、哪一步有关。</p></div><Link className="button button--action" to="/knowledge?tab=materials"><FileInput size={16}/>导入资料</Link></header>}
    {embedded && <header className="embedded-section-heading"><div><h2>待整理</h2><p>处理新资料，并确认它与哪件事项、哪一步有关。</p></div><Link className="button button--action" to="/knowledge?tab=materials"><FileInput size={16}/>导入资料</Link></header>}
    <section className="inbox-summary" aria-label="收件箱摘要"><article><span>待处理</span><strong>{pending}</strong></article><article><span>待归类</span><strong>{unclassified}</strong></article><article><span>处理失败</span><strong>{failed}</strong></article><article><span>已归类</span><strong>{classified}</strong></article><p>{embedded ? "这里目前只包含你导入的真实本地资料；尚未接入外部内容来源。" : "当前收件箱只包含真实本地上传资料；未接入外部网页、GitHub、飞书或自主搜索来源。"}</p></section>
    {!!selectedIds.length && <section className="inbox-batch-bar" aria-label="批量操作"><strong>已选择 {selectedIds.length} 条</strong><button className="button button--secondary" onClick={() => setLinkIds(selectedIds)}><FolderInput size={16}/>批量归类</button><button className="button button--secondary" disabled={archive.isPending} onClick={() => { if (window.confirm(`确认归档选中的 ${selectedIds.length} 条资料？`)) archive.mutate(selectedIds); }}><Archive size={16}/>批量归档</button><button className="text-button" onClick={() => setSelectedIds([])}>取消选择</button></section>}
    {!items.length ? <EmptyState title="收件箱还是空的" description="导入第一份 PDF、Markdown 或文本资料后，它会先出现在这里。" action={<Link className="button button--primary" to="/knowledge?tab=materials">前往导入资料</Link>} /> : <section className="inbox-list" aria-label="知识收件箱条目">{items.map((item) => {
      const directLinks = linksByMaterial.get(item.id) ?? [];
      const ready = item.ingestion_status === "completed" && item.indexing_status === "completed";
      const itemFailed = item.ingestion_status === "failed" || item.indexing_status === "failed" || item.deletion_status === "failed";
      const processing = item.ingestion_status === "processing" || item.indexing_status === "indexing" || item.deletion_status === "pending";
      const state = item.archived_at ? "archived" : item.deletion_status === "failed" ? "delete_failed" : itemFailed ? "failed" : processing ? "processing" : !ready ? "pending" : directLinks.length ? "classified" : "unclassified";
      const label = { archived: "已归档", delete_failed: "删除失败", failed: "处理失败", processing: "正在整理", pending: "需要处理", classified: "已归类", unclassified: "待归类" }[state];
      return <article className="inbox-item" key={item.id}><label className="inbox-select"><input aria-label={`选择 ${item.original_filename}`} type="checkbox" checked={selectedIds.includes(item.id)} onChange={(event) => setSelectedIds((current) => event.target.checked ? [...current, item.id] : current.filter((id) => id !== item.id))}/></label><span className="file-icon"><FileText size={19}/></span><div><div className="inbox-item__meta"><span>{item.source_type.toUpperCase()}</span><span>{formatDateTime(item.created_at)}</span></div><h2><Link to={`/materials/${item.id}`}>{item.title || item.original_filename}</Link></h2><p>{item.original_filename}</p><div className="tag-list">{directLinks.slice(0, 3).map((link) => <span key={link.id}>{link.target_title}</span>)}</div></div><span className={`status status--${state}`}>{label}</span><div className="inbox-item__actions">{!ready && !item.archived_at && <button className="button button--quiet" disabled={processMaterial.isPending} onClick={() => processMaterial.mutate(item.id)}><RefreshCw size={16}/>处理</button>}{item.deletion_status === "failed" && <button className="button button--quiet" onClick={() => retryDelete.mutate(item.id)}>重试删除</button>}<button className="button button--quiet" disabled={!ready || !!item.archived_at} onClick={() => setLinkIds([item.id])}><FolderInput size={16}/>{directLinks.length ? "修改归属" : "归类"}</button><Link className="button button--quiet" to={`/notes?new=1&note_type=material&entity_type=material&entity_id=${item.id}`}><NotebookPen size={16}/>记录笔记</Link>{!item.archived_at && <button className="icon-button" aria-label={`归档 ${item.original_filename}`} onClick={() => archive.mutate([item.id])}><Archive size={16}/></button>}<button className="icon-button icon-button--danger" aria-label={`删除 ${item.original_filename}`} onClick={() => { if (window.confirm(`确认删除“${item.original_filename}”？`)) remove.mutate(item.id); }}><Trash2 size={16}/></button></div></article>;
    })}</section>}
    <MaterialLinkDialog open={linkIds.length > 0} materialIds={linkIds} onClose={() => setLinkIds([])} />
  </div>;
}
