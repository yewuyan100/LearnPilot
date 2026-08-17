import { useQuery } from "@tanstack/react-query";
import { ArrowRight, FileText, Inbox, NotebookPen } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { materialsApi, notesApi } from "../api/resources";
import { ErrorState, LoadingState } from "../components/States";
import { formatDateTime } from "../utils/format";
import { InboxPage } from "./InboxPage";
import { MaterialsPage } from "./MaterialsPage";
import { NotesPage } from "./NotesPage";
import { RagPage } from "./RagPage";

type KnowledgeTab = "overview" | "inbox" | "notes" | "materials" | "qa";

function KnowledgeOverview({ openTab }: { openTab: (tab: KnowledgeTab) => void }) {
  const materials = useQuery({ queryKey: ["materials", "", ""], queryFn: () => materialsApi.list() });
  const notes = useQuery({ queryKey: ["notes", "knowledge-overview"], queryFn: () => notesApi.list({ pageSize: 100 }) });
  if (materials.isLoading || notes.isLoading) return <LoadingState label="正在整理最近内容"/>;
  if (materials.isError || notes.isError) return <ErrorState message={(materials.error ?? notes.error)!.message}/>;

  const materialItems = materials.data ?? [];
  const noteItems = notes.data?.items ?? [];
  const recent = [
    ...materialItems.map((item) => ({
      key: `material-${item.id}`,
      kind: "资料",
      title: item.title || item.original_filename,
      detail: item.original_filename,
      at: item.updated_at,
      href: `/materials/${item.id}`,
    })),
    ...noteItems.map((item) => ({
      key: `note-${item.id}`,
      kind: item.links.some((link) => link.entity_type === "rag_message") ? "AI 整理" : "笔记",
      title: item.title,
      detail: item.links[0]?.entity_title || item.tags.slice(0, 2).join("、") || "尚未关联事项",
      at: item.updated_at,
      href: `/knowledge?tab=notes&note=${item.id}`,
    })),
  ].sort((a, b) => b.at.localeCompare(a.at)).slice(0, 8);
  const pending = materialItems.filter((item) => (
    !item.archived_at && (
      item.ingestion_status !== "completed"
      || item.indexing_status !== "completed"
      || item.deletion_status === "failed"
    )
  )).length;
  const ready = materialItems.filter((item) => item.ingestion_status === "completed" && item.indexing_status === "completed").length;

  return <div className="knowledge-overview">
    <section className="knowledge-status-runway" aria-label="知识库状态">
      <section><header><Inbox size={18}/><h2>待整理</h2></header><strong>{pending ? `${pending} 条需要处理` : "当前没有待处理内容"}</strong><p>处理、归类和失败重试统一留在收件箱。</p><button className="text-link" onClick={() => openTab("inbox")}>打开收件箱<ArrowRight size={14}/></button></section>
      <section><header><NotebookPen size={18}/><h2>笔记与摘录</h2></header><strong>{noteItems.length} 条记录</strong><p>包括自己的理解、资料摘录和已保存的 AI 回答。</p><button className="text-link" onClick={() => openTab("notes")}>继续整理<ArrowRight size={14}/></button></section>
      <section><header><FileText size={18}/><h2>资料与来源</h2></header><strong>{ready} 份可使用</strong><p>来源可关联事项，也可限定范围进行核对。</p><button className="text-link" onClick={() => openTab("materials")}>查看来源<ArrowRight size={14}/></button></section>
    </section>
    <section className="knowledge-recent" aria-labelledby="knowledge-recent-title">
      <header className="section-heading"><div><h2 id="knowledge-recent-title">最近内容</h2><p>最近上传、记录和从资料问答中保存的真实内容。</p></div></header>
      {recent.length ? <div className="knowledge-recent-list">{recent.map((item) => <Link key={item.key} to={item.href}><span>{item.kind}</span><div><strong>{item.title}</strong><small>{item.detail}</small></div><time>{formatDateTime(item.at)}</time><ArrowRight size={15}/></Link>)}</div> : <p className="inline-empty">还没有资料或笔记。可以先导入一份来源，或记录一条想法。</p>}
    </section>
  </div>;
}

export function KnowledgeHubPage() {
  const [params, setParams] = useSearchParams();
  const requested = params.get("tab") as KnowledgeTab | null;
  const active: KnowledgeTab = ["inbox", "notes", "materials", "qa"].includes(requested ?? "") ? requested! : "overview";
  const openTab = (tab: KnowledgeTab) => setParams({ tab });

  return <div className="page composition-page integrated-page knowledge-hub-page">
    <header className="knowledge-viewbar">
      <nav aria-label="知识库视图">
        <button className={active === "overview" ? "is-active" : ""} onClick={() => openTab("overview")}>最近内容</button>
        <button className={active === "inbox" ? "is-active" : ""} onClick={() => openTab("inbox")}>待整理</button>
        <button className={active === "notes" ? "is-active" : ""} onClick={() => openTab("notes")}>笔记与摘录</button>
        <button className={active === "materials" ? "is-active" : ""} onClick={() => openTab("materials")}>资料与来源</button>
        <button className={active === "qa" ? "is-active" : ""} onClick={() => openTab("qa")}>基于资料核对</button>
      </nav>
      <select aria-label="选择知识库视图" value={active} onChange={(event) => openTab(event.target.value as KnowledgeTab)}>
        <option value="overview">最近内容</option><option value="inbox">待整理</option><option value="notes">笔记与摘录</option><option value="materials">资料与来源</option><option value="qa">基于资料核对</option>
      </select>
    </header>
    <div className="integrated-content" data-knowledge-view={active}>
      {active === "overview" && <KnowledgeOverview openTab={openTab}/>}
      {active === "inbox" && <InboxPage embedded/>}
      {active === "notes" && <NotesPage embedded/>}
      {active === "materials" && <MaterialsPage embedded/>}
      {active === "qa" && <RagPage/>}
    </div>
  </div>;
}
