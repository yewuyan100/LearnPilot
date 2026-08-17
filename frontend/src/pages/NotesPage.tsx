import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  BookOpen,
  Check,
  Eye,
  FileText,
  Link2,
  NotebookPen,
  Pin,
  Plus,
  Save,
  Search,
  Unlink,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  activitiesApi,
  coursesApi,
  dashboardApi,
  goalsApi,
  materialsApi,
  notesApi,
  sessionsApi,
} from "../api/resources";
import { SafeMarkdown } from "../components/SafeMarkdown";
import { ActionMenu } from "../components/ActionMenu";
import { Dialog } from "../components/Dialog";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { useToast } from "../components/toast-context";
import type { Note, NoteType } from "../types";
import { formatDateTime } from "../utils/format";


const typeLabels: Record<NoteType, string> = {
  quick: "快速记录",
  study: "学习笔记",
  course: "路线笔记",
  knowledge_point: "步骤笔记",
  material: "资料摘录",
  reflection: "成长复盘",
};

type Draft = {
  title: string;
  content: string;
  noteType: NoteType;
  pinned: boolean;
  tags: string;
};

const emptyDraft: Draft = {
  title: "",
  content: "",
  noteType: "quick",
  pinned: false,
  tags: "",
};

function toDraft(note: Note): Draft {
  return {
    title: note.title === "未命名笔记" ? "" : note.title,
    content: note.content_markdown,
    noteType: note.note_type,
    pinned: note.is_pinned,
    tags: note.tags.join(", "),
  };
}

export function NotesPage({ embedded = false }: { embedded?: boolean }) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [params, setParams] = useSearchParams();
  const setNotebookParams = useCallback((values: Record<string, string>, options?: { replace?: boolean }) => {
    setParams(embedded ? { tab: "notes", ...values } : values, options);
  }, [embedded, setParams]);
  const [search, setSearch] = useState("");
  const [type, setType] = useState("");
  const [tag, setTag] = useState("");
  const [pinnedOnly, setPinnedOnly] = useState(false);
  const [archived, setArchived] = useState(false);
  const [preview, setPreview] = useState(false);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [dirty, setDirty] = useState(false);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "failed">("idle");
  const [linkType, setLinkType] = useState("course");
  const [linkId, setLinkId] = useState("");
  const [sourceMaterialId, setSourceMaterialId] = useState("");
  const [sourceQuote, setSourceQuote] = useState("");
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [managementBusy, setManagementBusy] = useState(false);
  const [managementError, setManagementError] = useState("");
  const creating = params.get("new") === "1";
  const selectedId = Number(params.get("note")) || null;
  const contextType = params.get("entity_type");
  const contextId = Number(params.get("entity_id")) || null;
  const requestedType = params.get("note_type") as NoteType | null;

  const notes = useQuery({
    queryKey: ["notes", search, type, tag, pinnedOnly, archived],
    queryFn: () => notesApi.list({
      q: search,
      noteType: type,
      tag,
      pinned: pinnedOnly ? true : undefined,
      archived,
    }),
  });
  const goals = useQuery({ queryKey: ["goals"], queryFn: goalsApi.list });
  const courses = useQuery({ queryKey: ["courses"], queryFn: coursesApi.list });
  const materials = useQuery({ queryKey: ["materials", "", ""], queryFn: () => materialsApi.list() });
  const activities = useQuery({ queryKey: ["learning-activities"], queryFn: () => activitiesApi.list() });
  const sessions = useQuery({ queryKey: ["learning-sessions"], queryFn: sessionsApi.list });
  const today = useQuery({ queryKey: ["today"], queryFn: dashboardApi.today });
  const points = useQuery({
    queryKey: ["all-knowledge-points", courses.data?.map((item) => item.id).join(",")],
    queryFn: async () => (await Promise.all((courses.data ?? []).map((item) => coursesApi.points(item.id)))).flat(),
    enabled: Boolean(courses.data),
  });

  const selected = notes.data?.items.find((item) => item.id === selectedId) ?? null;
  const allTags = useMemo(
    () => [...new Set((notes.data?.items ?? []).flatMap((item) => item.tags))].sort(),
    [notes.data?.items],
  );
  const targets = useMemo(() => {
    if (linkType === "learning_goal") return (goals.data ?? []).map((item) => ({ id: item.id, label: item.title }));
    if (linkType === "course") return (courses.data ?? []).map((item) => ({ id: item.id, label: item.title }));
    if (linkType === "knowledge_point") return (points.data ?? []).map((item) => ({ id: item.id, label: item.title }));
    if (linkType === "material") return (materials.data ?? []).map((item) => ({ id: item.id, label: item.title || item.original_filename }));
    if (linkType === "daily_task") return (today.data?.tasks ?? []).map((item) => ({ id: item.id, label: item.title }));
    if (linkType === "learning_session") return (sessions.data ?? []).map((item) => ({ id: item.id, label: item.notes || `学习会话 #${item.id}` }));
    if (linkType === "learning_activity") return (activities.data?.items ?? []).map((item) => ({ id: item.id, label: item.title }));
    return [];
  }, [activities.data, courses.data, goals.data, linkType, materials.data, points.data, sessions.data, today.data]);

  useEffect(() => {
    if (creating) {
      const inferredType: NoteType = requestedType && requestedType in typeLabels
        ? requestedType
        : contextType === "course" ? "course"
          : contextType === "knowledge_point" ? "knowledge_point"
            : contextType === "material" ? "material" : "quick";
      setDraft({ ...emptyDraft, noteType: inferredType });
      setDirty(false);
      setSaveState("idle");
      return;
    }
    if (selected) {
      setDraft(toDraft(selected));
      setDirty(false);
      setSaveState("saved");
    }
  }, [contextType, creating, requestedType, selected]);

  useEffect(() => {
    if (!creating && !selectedId && notes.data?.items[0]) {
      setNotebookParams({ note: String(notes.data.items[0].id) }, { replace: true });
    }
  }, [creating, notes.data?.items, selectedId, setNotebookParams]);

  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (dirty) {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const save = useCallback(async () => {
    if (!dirty) return;
    if (creating && !draft.title.trim() && !draft.content.trim()) return;
    setSaveState("saving");
    const payload = {
      title: creating ? draft.title.trim() || null : draft.title.trim(),
      content_markdown: draft.content,
      note_type: draft.noteType,
      is_pinned: draft.pinned,
      tags: draft.tags.split(/[,，]/).map((item) => item.trim()).filter(Boolean),
      ...(creating && contextType && contextId ? {
        links: [{ entity_type: contextType, entity_id: contextId, relation_type: "context" }],
      } : {}),
    };
    try {
      const saved = creating
        ? await notesApi.create(payload)
        : await notesApi.update(selectedId!, payload);
      setDirty(false);
      setSaveState("saved");
      await queryClient.invalidateQueries({ queryKey: ["notes"] });
      if (creating) setNotebookParams({ note: String(saved.id) }, { replace: true });
    } catch (error) {
      setSaveState("failed");
      showToast(error instanceof Error ? error.message : "笔记保存失败", "error");
    }
  }, [contextId, contextType, creating, dirty, draft, queryClient, selectedId, setNotebookParams, showToast]);

  useEffect(() => {
    if (!dirty) return;
    const timer = window.setTimeout(() => void save(), 1000);
    return () => window.clearTimeout(timer);
  }, [dirty, draft, save]);

  useEffect(() => {
    const shortcut = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        void save();
      }
    };
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, [save]);

  const change = <K extends keyof Draft>(key: K, value: Draft[K]) => {
    setDraft((current) => ({ ...current, [key]: value }));
    setDirty(true);
    setSaveState("idle");
  };
  const choose = (id: number) => {
    if (dirty && !window.confirm("这条笔记还没有保存，仍要离开吗？")) return;
    setNotebookParams({ note: String(id) });
  };
  const refreshSelected = async () => {
    await queryClient.invalidateQueries({ queryKey: ["notes"] });
  };
  const addLink = async () => {
    if (!selectedId || !linkId) return;
    await notesApi.addLink(selectedId, { entity_type: linkType, entity_id: Number(linkId) });
    setLinkId("");
    await refreshSelected();
  };
  const addSource = async () => {
    if (!selectedId || !sourceMaterialId || !sourceQuote.trim()) return;
    await notesApi.addSource(selectedId, {
      material_id: Number(sourceMaterialId),
      quoted_text: sourceQuote.trim(),
    });
    setSourceQuote("");
    await refreshSelected();
  };
  const archiveNote = async () => {
    if (!selectedId) return;
    setManagementBusy(true);
    try {
      await notesApi.archive(selectedId);
      setNotebookParams({});
      await queryClient.invalidateQueries({ queryKey: ["notes"] });
      showToast("笔记已归档", "success");
    } catch (error) {
      showToast(error instanceof Error ? error.message : "笔记归档失败", "error");
    } finally {
      setManagementBusy(false);
    }
  };
  const deleteNote = async () => {
    if (!selectedId) return;
    setManagementBusy(true);
    setManagementError("");
    try {
      await notesApi.remove(selectedId);
      setNotebookParams({});
      await queryClient.invalidateQueries({ queryKey: ["notes"] });
      setDeleteOpen(false);
      showToast("笔记已删除", "success");
    } catch (error) {
      setManagementError(error instanceof Error ? error.message : "笔记删除失败");
    } finally {
      setManagementBusy(false);
    }
  };

  if (notes.isLoading) return <LoadingState label="正在打开笔记本" />;
  if (notes.isError) return <ErrorState message={notes.error.message} onRetry={() => notes.refetch()} />;

  return <div className={embedded ? "notebook-page notebook-page--embedded" : "page notebook-page"}>
    <header className={embedded ? "notebook-commandbar" : "page-header page-header--split"}>
      <div>{embedded ? <><strong>{notes.data?.total ?? notes.data?.items.length ?? 0} 条笔记</strong><p>筛选、选择，再在右侧继续整理。</p></> : <><h1>笔记本</h1><p>记录重点、资料摘录、临时想法和真实复盘，并把它们关联回正在推进的事项。</p></>}</div>
      <button className="button button--primary" onClick={() => setNotebookParams({ new: "1" })}><Plus size={16}/>新建笔记</button>
    </header>
    <aside className="notebook-filters" aria-label="筛选笔记">
        <label className="search-field"><Search size={16}/><input aria-label="搜索笔记" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索标题和正文"/></label>
        <label><span>笔记类型</span><select aria-label="笔记类型" value={type} onChange={(event) => setType(event.target.value)}><option value="">全部类型</option>{Object.entries(typeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label><span>标签</span><select aria-label="标签筛选" value={tag} onChange={(event) => setTag(event.target.value)}><option value="">全部标签</option>{allTags.map((item) => <option key={item}>{item}</option>)}</select></label>
        <label className="check-row"><input type="checkbox" checked={pinnedOnly} onChange={(event) => setPinnedOnly(event.target.checked)}/><Pin size={15}/>只看置顶</label>
        <label className="check-row"><input type="checkbox" checked={archived} onChange={(event) => { setArchived(event.target.checked); setNotebookParams({}); }}/><Archive size={15}/>已归档</label>
    </aside>
    <div className="notebook-layout">
      <section className="notebook-list" aria-label="笔记列表">
        {(notes.data?.items ?? []).length ? notes.data!.items.map((item) => <button key={item.id} className={`note-list-item ${selectedId === item.id ? "is-active" : ""}`} onClick={() => choose(item.id)}><span className="note-list-item__title">{item.is_pinned && <Pin size={13}/>}<strong>{item.title}</strong></span><p>{item.content_markdown.replace(/[#*_`]/g, " ").slice(0, 90) || "还没有正文"}</p><small>{typeLabels[item.note_type]} · {formatDateTime(item.updated_at)}</small><span className="note-list-item__links">{item.links.slice(0, 2).map((link) => <span key={link.id}>{link.source_available ? link.entity_title : "来源已失效"}</span>)}</span></button>) : <EmptyState title="还没有笔记" description="记录重点、资料摘录或临时想法，之后可以在这里统一整理。" action={<button className="button button--secondary" onClick={() => setNotebookParams({ new: "1" })}>新建笔记</button>}/>}
      </section>
      <main className="note-editor">
        {(creating || selected) ? <>
          <div className="note-editor__bar"><div className={`save-state save-state--${saveState}`}>{saveState === "saving" ? "保存中" : saveState === "failed" ? "保存失败，可重试" : saveState === "saved" ? <><Check size={14}/>已保存</> : dirty ? "等待自动保存" : "尚未编辑"}</div><div className="button-row"><button className="button button--secondary" onClick={() => setPreview((value) => !value)}><Eye size={15}/>{preview ? "继续编辑" : "预览"}</button><button className="button button--primary" disabled={!dirty} onClick={() => void save()}><Save size={15}/>保存</button>{!creating && selected && <ActionMenu label={`管理笔记 ${selected.title}`} items={[
            ...(selected.status === "active" ? [{ label: "归档", disabled: managementBusy, onSelect: () => void archiveNote() }] : []),
            { label: "删除笔记", destructive: true, disabled: managementBusy, onSelect: () => { setManagementError(""); setDeleteOpen(true); } },
          ]}/>}</div></div>
          <input className="note-title-input" aria-label="笔记标题" value={draft.title} onChange={(event) => change("title", event.target.value)} placeholder="笔记标题（可选）"/>
          <div className="note-editor__meta"><label><span>类型</span><select value={draft.noteType} onChange={(event) => change("noteType", event.target.value as NoteType)}>{Object.entries(typeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label className="check-row"><input type="checkbox" checked={draft.pinned} onChange={(event) => change("pinned", event.target.checked)}/><Pin size={15}/>置顶</label><label className="note-tags"><span>标签</span><input aria-label="笔记标签" value={draft.tags} onChange={(event) => change("tags", event.target.value)} placeholder="用逗号分隔"/></label></div>
          {preview ? <SafeMarkdown content={draft.content}/> : <textarea className="note-markdown-input" aria-label="Markdown 正文" value={draft.content} onChange={(event) => change("content", event.target.value)} placeholder="记录重点、摘录或自己的理解。支持基础 Markdown。"/>}
          {!creating && selected && <div className="note-context-grid">
            <section><h2><Link2 size={17}/>关联事项与内容</h2><div className="inline-form"><select aria-label="关联类型" value={linkType} onChange={(event) => { setLinkType(event.target.value); setLinkId(""); }}><option value="learning_goal">事项</option><option value="course">路线</option><option value="knowledge_point">步骤</option><option value="material">资料</option><option value="daily_task">今天的安排</option><option value="learning_session">推进记录</option><option value="learning_activity">练习</option></select><select aria-label="关联对象" value={linkId} onChange={(event) => setLinkId(event.target.value)}><option value="">选择对象</option>{targets.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select><button className="button button--secondary" disabled={!linkId} onClick={() => void addLink()}>添加</button></div><div className="note-chips">{selected.links.map((link) => <span key={link.id} className={!link.source_available ? "is-invalid" : ""}>{link.source_available ? link.entity_title : "来源已失效"}<button aria-label={`移除关联 ${link.entity_title}`} onClick={() => void notesApi.removeLink(selected.id, link.id).then(refreshSelected)}><Unlink size={13}/></button></span>)}</div></section>
            <section><h2><FileText size={17}/>来源摘录</h2><div className="source-form"><select aria-label="摘录资料" value={sourceMaterialId} onChange={(event) => setSourceMaterialId(event.target.value)}><option value="">选择资料</option>{(materials.data ?? []).map((item) => <option key={item.id} value={item.id}>{item.title || item.original_filename}</option>)}</select><textarea aria-label="摘录原文" value={sourceQuote} onChange={(event) => setSourceQuote(event.target.value)} placeholder="粘贴选中的原文，不会自动复制整个回答。"/><button className="button button--secondary" disabled={!sourceMaterialId || !sourceQuote.trim()} onClick={() => void addSource()}>添加摘录</button></div>{selected.sources.map((source) => <blockquote key={source.id} className={!source.source_available ? "is-invalid" : ""}><strong>{source.source_title}</strong><small>{source.source_available ? source.source_locator || "资料" : "来源已失效"}</small><p>{source.quoted_text}</p><button className="text-button" onClick={() => void notesApi.removeSource(selected.id, source.id).then(refreshSelected)}>移除摘录</button></blockquote>)}</section>
          </div>}
        </> : <div className="note-editor-empty"><NotebookPen size={28}/><h2>选择一条笔记继续整理</h2><p>也可以新建快速记录，再通过关联和标签逐步整理。</p><button className="button button--primary" onClick={() => setNotebookParams({ new: "1" })}><BookOpen size={16}/>开始记录</button></div>}
      </main>
    </div>
    <Dialog open={deleteOpen} title={`删除笔记「${selected?.title ?? ""}」？`} onClose={() => { if (!managementBusy) { setDeleteOpen(false); setManagementError(""); } }}>
      <div className="management-dialog"><p>删除后该笔记将无法恢复。</p><p className="management-dialog__detail">关联事项和资料本身不会被删除；这条笔记的关联与来源摘录会随笔记一并移除。</p>{managementError && <p className="form-error" role="alert">{managementError}</p>}<div className="dialog-actions"><button type="button" className="button button--secondary" disabled={managementBusy} onClick={() => { setDeleteOpen(false); setManagementError(""); }}>取消</button><button type="button" className="button button--danger" disabled={managementBusy} onClick={() => void deleteNote()}>{managementBusy ? "删除中" : "删除笔记"}</button></div></div>
    </Dialog>
  </div>;
}
