import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import { Bell, ChevronDown, Menu, MessageSquareText, Search, Sparkles, X } from "lucide-react";
import { activitiesApi, coursesApi, goalsApi, materialsApi, notesApi } from "../api/resources";
import { LearnPilotLogo } from "../components/LearnPilotLogo";
import { useLocalClock } from "../utils/useLocalClock";

const primaryNavigation = [
  { to: "/workspace", label: "工作台" },
  { to: "/items", label: "学习规划" },
  { to: "/knowledge", label: "知识库" },
  { to: "/explore", label: "发现" },
  { to: "/ai", label: "AI 协作" },
];

const allNavigation = [...primaryNavigation, { to: "/settings", label: "设置" }];

export function AppLayout() {
  const [open, setOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [term, setTerm] = useState("");
  const { dateLabel, timeLabel } = useLocalClock();
  const goals = useQuery({ queryKey: ["goals"], queryFn: goalsApi.list, enabled: searchOpen });
  const courses = useQuery({ queryKey: ["courses"], queryFn: coursesApi.list, enabled: searchOpen });
  const materials = useQuery({ queryKey: ["materials", "", ""], queryFn: () => materialsApi.list(), enabled: searchOpen });
  const activities = useQuery({ queryKey: ["learning-activities"], queryFn: () => activitiesApi.list(), enabled: searchOpen });
  const notes = useQuery({ queryKey: ["notes", "search"], queryFn: () => notesApi.list(), enabled: searchOpen });
  const results = useMemo(() => {
    const query = term.trim().toLocaleLowerCase();
    if (!query) return [];
    return [
      ...(goals.data ?? []).filter((item) => item.title.toLocaleLowerCase().includes(query)).map((item) => ({ label: item.title, type: "学习规划", to: `/items/${item.id}` })),
      ...(courses.data ?? []).filter((item) => item.title.toLocaleLowerCase().includes(query)).map((item) => ({ label: item.title, type: "路线内容", to: item.learning_goal_id ? `/items/${item.learning_goal_id}` : "/courses" })),
      ...(materials.data ?? []).filter((item) => item.title.toLocaleLowerCase().includes(query) || item.original_filename.toLocaleLowerCase().includes(query)).map((item) => ({ label: item.title || item.original_filename, type: "资料", to: "/knowledge?tab=materials" })),
      ...(activities.data?.items ?? []).filter((item) => item.title.toLocaleLowerCase().includes(query)).map((item) => ({ label: item.title, type: "练习记录", to: `/activities/${item.id}` })),
      ...(notes.data?.items ?? []).filter((item) => item.title.toLocaleLowerCase().includes(query) || item.content_markdown.toLocaleLowerCase().includes(query)).map((item) => ({ label: item.title, type: "笔记", to: `/notes?note=${item.id}` })),
    ].slice(0, 8);
  }, [activities.data, courses.data, goals.data, materials.data, notes.data, term]);

  useEffect(() => {
    const handleShortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLocaleLowerCase() === "k") {
        event.preventDefault();
        setSearchOpen(true);
      }
      if (event.key === "Escape") {
        setSearchOpen(false);
      }
    };
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  }, []);

  return <div className="app-shell">
    <header className="mobile-header"><Link to="/workspace" className="brand-mark"><span className="brand-mark__icon"><LearnPilotLogo /></span><span>LearnPilot</span></Link><button className="icon-button" aria-label="打开导航" onClick={() => setOpen(true)}><Menu size={20} /></button></header>
    {open && <button className="nav-scrim" aria-label="关闭导航" onClick={() => setOpen(false)} />}
    <aside className={`side-rail ${open ? "side-rail--open" : ""}`}>
      <div className="side-rail__head"><Link to="/workspace" className="brand-mark"><span className="brand-mark__icon"><LearnPilotLogo /></span><span className="brand-mark__copy">LearnPilot</span></Link><button className="icon-button side-rail__close" aria-label="关闭导航" onClick={() => setOpen(false)}><X size={18} /></button></div>
      <nav aria-label="主导航">{primaryNavigation.map(({ to, label }) => <NavLink key={to} to={to} onClick={() => setOpen(false)} className={({ isActive }) => `nav-link ${isActive ? "nav-link--active" : ""}`}><span>{label}</span></NavLink>)}</nav>
      <div className="side-rail__settings"><NavLink to="/settings" onClick={() => setOpen(false)} className={({ isActive }) => `nav-link ${isActive ? "nav-link--active" : ""}`}><span>设置</span></NavLink></div>
    </aside>
    <main className="app-main">
      <header className="top-bar">
        <div className="top-bar__clock"><strong>{dateLabel}</strong><time dateTime={timeLabel}>{timeLabel}</time></div>
        <div className="top-bar__actions">
          <button className="top-search" aria-label="全局搜索" title="全局搜索" onClick={() => setSearchOpen(true)}><Search size={17} /><span>搜索知识、笔记、资料或提问 AI...</span><kbd>Ctrl K</kbd></button>
          <Link className="icon-button top-bar__icon" to="/workspace#pending" aria-label="查看待处理内容" title="待处理"><Bell size={18} /></Link>
          <Link className="icon-button top-bar__icon" to="/ai" aria-label="打开消息" title="消息"><MessageSquareText size={18} /></Link>
          <Link className="top-ai-button" to="/ai"><Sparkles size={16} />AI 助手<ChevronDown size={15} aria-hidden="true" /></Link>
        </div>
      </header>
      <Outlet />
    </main>
    <nav className="mobile-bottom-nav" aria-label="移动端主导航">{allNavigation.map(({ to, label }) => <NavLink key={to} to={to} className={({ isActive }) => isActive ? "is-active" : ""}><span>{label}</span></NavLink>)}</nav>
    {searchOpen && <div className="search-overlay" role="dialog" aria-modal="true" aria-label="全局搜索"><button className="nav-scrim search-overlay__scrim" aria-label="关闭搜索" onClick={() => setSearchOpen(false)} /><div className="search-dialog"><label><Search size={18}/><input autoFocus value={term} onChange={(event) => setTerm(event.target.value)} placeholder="搜索知识、笔记、资料或提问 AI..." /></label>{term && <div className="search-results">{results.length ? results.map((item, index) => <Link key={`${item.type}-${index}`} to={item.to} onClick={() => { setSearchOpen(false); setTerm(""); }}><span>{item.type}</span>{item.label}</Link>) : <p>没有匹配的现有记录。</p>}</div>}</div></div>}
  </div>;
}
