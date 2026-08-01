import {
  BarChart3,
  BookOpen,
  CalendarCheck,
  Files,
  GraduationCap,
  ClipboardCheck,
  Menu,
  MessageSquareText,
  Bot,
  RotateCcw,
  CircleX,
  Settings,
  X,
} from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

const navigation = [
  { to: "/agent", label: "学习助手", icon: Bot },
  { to: "/today", label: "今日学习", icon: CalendarCheck },
  { to: "/courses", label: "课程", icon: BookOpen },
  { to: "/materials", label: "资料", icon: Files },
  { to: "/rag", label: "资料问答", icon: MessageSquareText },
  { to: "/activities", label: "学习活动", icon: ClipboardCheck },
  { to: "/wrong-answers", label: "错题本", icon: CircleX },
  { to: "/reviews", label: "复习", icon: RotateCcw },
  { to: "/progress", label: "进度", icon: BarChart3 },
  { to: "/settings", label: "设置", icon: Settings },
];

export function AppLayout() {
  const [open, setOpen] = useState(false);
  return (
    <div className="app-shell">
      <header className="mobile-header">
        <div className="brand-mark"><GraduationCap size={20} /><span>PersonalLearning</span></div>
        <button className="icon-button" aria-label="打开导航" onClick={() => setOpen(true)}>
          <Menu size={20} />
        </button>
      </header>
      {open && <button className="nav-scrim" aria-label="关闭导航" onClick={() => setOpen(false)} />}
      <aside className={`side-rail ${open ? "side-rail--open" : ""}`}>
        <div className="side-rail__head">
          <div className="brand-mark">
            <span className="brand-mark__icon"><GraduationCap size={20} /></span>
            <span>Personal<br />Learning</span>
          </div>
          <button className="icon-button side-rail__close" aria-label="关闭导航" onClick={() => setOpen(false)}>
            <X size={18} />
          </button>
        </div>
        <nav aria-label="主导航">
          {navigation.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              onClick={() => setOpen(false)}
              className={({ isActive }) => `nav-link ${isActive ? "nav-link--active" : ""}`}
            >
              <Icon size={18} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="side-rail__foot">
          <span className="status-dot" /> 本地数据库
          <small>PersonalLearning V5</small>
        </div>
      </aside>
      <main className="app-main">
        <Outlet />
        <footer className="app-footer">PersonalLearning · V5 受控学习助手</footer>
      </main>
    </div>
  );
}
