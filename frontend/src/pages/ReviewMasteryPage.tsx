import { NotebookPen } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { MasteryPage } from "./MasteryPage";
import { ReviewPlanPage } from "./ReviewPlanPage";
import { WrongAnswersPage } from "./WrongAnswersPage";

const tabs = [
  { id: "review", label: "复习安排" },
  { id: "mastery", label: "掌握情况" },
  { id: "wrong", label: "错题记录" },
] as const;

export function ReviewMasteryPage() {
  const [params, setParams] = useSearchParams();
  const requested = params.get("tab");
  const active = tabs.some((tab) => tab.id === requested) ? requested : "review";
  return <div className="page integrated-page">
    <header className="page-header page-header--split"><div><p className="page-kicker">学习</p><h1>复习与掌握</h1><p>把复习安排、掌握证据与错题回看放在同一条巩固路径中。</p></div><Link className="button button--secondary" to="/notes?new=1&note_type=study"><NotebookPen size={16}/>记录复习笔记</Link></header>
    <nav className="page-tabs" aria-label="复习与掌握视图">{tabs.map((tab) => <button key={tab.id} className={active === tab.id ? "is-active" : ""} onClick={() => setParams({ tab: tab.id })}>{tab.label}</button>)}</nav>
    <div className="integrated-content">
      {active === "review" && <ReviewPlanPage />}
      {active === "mastery" && <MasteryPage />}
      {active === "wrong" && <WrongAnswersPage />}
    </div>
  </div>;
}
