import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, BrainCircuit, RefreshCw, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { masteryApi } from "../api/resources";

const levelLabel: Record<string, string> = {
  unassessed: "未评估", beginner: "入门", developing: "发展中",
  proficient: "熟练", strong: "较强",
};

function Score({ value, kind }: { value: number | null; kind: "mastery" | "confidence" }) {
  if (value === null) return <span className="mastery-score mastery-score--empty">未评估</span>;
  return (
    <span className={`mastery-score mastery-score--${kind}`}>
      <strong>{Math.round(value)}</strong><small>/ 100</small>
    </span>
  );
}
export function MasteryPage() {
  const queryClient = useQueryClient();
  const mastery = useQuery({ queryKey: ["mastery"], queryFn: masteryApi.list });
  const weak = useQuery({ queryKey: ["weak-points"], queryFn: masteryApi.weakPoints });
  const rebuild = useMutation({
    mutationFn: masteryApi.rebuild,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["mastery"] }),
  });
  if (mastery.isLoading) return <main className="page mastery-page"><LoadingState label="正在计算掌握度…" /></main>;
  if (mastery.isError) return <main className="page mastery-page"><ErrorState message="掌握度暂时无法加载" onRetry={() => mastery.refetch()} /></main>;
  const items = mastery.data?.items ?? [];
  const knownWeak = weak.data?.filter((item) => item.classification === "weak") ?? [];
  const unassessed = items.filter((item) => item.mastery_level === "unassessed").length;
  return (
    <main className="page mastery-page">
      <header className="page-header page-header--split">
        <div>
          <p className="page-kicker">V6 · Adaptive learning</p>
          <h1>掌握度</h1>
          <p>根据真实测验、复习、任务和学习会话，以透明规则展示掌握情况与证据置信度。</p>
        </div>
        <button className="button button--secondary" onClick={() => rebuild.mutate()} disabled={rebuild.isPending}>
          <RefreshCw size={16} /> {rebuild.isPending ? "正在重建" : "重建掌握度"}
        </button>
      </header>
      <div className="notice notice--info"><ShieldCheck size={18} />掌握度是项目规则分数，不代表正式教育测评结果；无证据不会显示为 0 分。</div>
      <section className="mastery-summary" aria-label="掌握度摘要">
        <article><BrainCircuit size={20} /><span>知识点</span><strong>{items.length}</strong></article>
        <article><AlertTriangle size={20} /><span>已知薄弱</span><strong>{knownWeak.length}</strong></article>
        <article><ShieldCheck size={20} /><span>未评估</span><strong>{unassessed}</strong></article>
      </section>
      {items.length === 0 ? <EmptyState title="还没有知识点" description="先在课程页创建知识点，再开始积累学习证据。" /> : (
        <section className="mastery-table" aria-label="知识点掌握度列表">
          <header><span>知识点</span><span>掌握度</span><span>置信度</span><span>证据</span><span>下次复习</span></header>
          {items.map((item) => (
            <Link key={item.knowledge_point_id} to={`/mastery/${item.knowledge_point_id}`} className="mastery-row">
              <div><strong>{item.knowledge_point_title}</strong><small>{item.course_title} · {levelLabel[item.mastery_level]}</small></div>
              <Score value={item.mastery_score} kind="mastery" />
              <Score value={item.confidence_score} kind="confidence" />
              <span>{item.evidence_count} 条{item.active_wrong_answers ? ` · ${item.active_wrong_answers} 条错题` : ""}</span>
              <span>{item.next_review_at ? new Date(item.next_review_at).toLocaleDateString("zh-CN") : "暂无"}</span>
            </Link>
          ))}
        </section>
      )}
    </main>
  );
}
