import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarCheck, CheckCircle2, Clock3, XCircle } from "lucide-react";
import { Link } from "react-router-dom";
import { adaptiveApi } from "../api/resources";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import type { AdaptiveReview } from "../types";

function group(review: AdaptiveReview): string {
  const due = new Date(review.due_at);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const days = Math.ceil((due.getTime() - today.getTime()) / 86400000);
  if (review.overdue || days < 0) return "已逾期";
  if (days === 0) return "今天";
  if (days <= 7) return "未来 7 天";
  return "稍后";
}
export function ReviewPlanPage() {
  const queryClient = useQueryClient();
  const reviews = useQuery({ queryKey: ["adaptive-reviews"], queryFn: adaptiveApi.reviews });
  const recommendations = useQuery({ queryKey: ["adaptive-recommendations"], queryFn: () => adaptiveApi.recommendations("pending") });
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["adaptive-reviews"] });
    queryClient.invalidateQueries({ queryKey: ["adaptive-recommendations"] });
  };
  const accept = useMutation({ mutationFn: adaptiveApi.accept, onSuccess: refresh });
  const reject = useMutation({ mutationFn: adaptiveApi.reject, onSuccess: refresh });
  if (reviews.isLoading || recommendations.isLoading) return <main className="page"><LoadingState label="正在整理复习计划…" /></main>;
  if (reviews.isError || recommendations.isError) return <main className="page"><ErrorState message="复习计划暂时无法加载" onRetry={() => { reviews.refetch(); recommendations.refetch(); }} /></main>;
  const pending = recommendations.data ?? [];
  const groups = ["已逾期", "今天", "未来 7 天", "稍后"];
  return (
    <main className="page review-plan-page">
      <header className="page-header"><p className="page-kicker">V6 · Review scheduler</p><h1>复习计划</h1><p>复习日期和优先级由透明规则计算；创建任务前始终由你确认。</p></header>
      {pending.length > 0 && <section className="recommendation-strip"><header><CalendarCheck size={20} /><div><h2>待确认建议</h2><p>建议不会自动写入今日任务。</p></div></header>{pending.map((item) => <article key={item.id}><div><span className={`status status--${item.priority === "high" ? "failed" : "pending"}`}>{item.priority}</span><h3>{item.title}</h3><p>{String(item.reason_details.reason_summary ?? item.reason_code)}</p><small>{item.suggested_date} · {item.suggested_minutes} 分钟</small></div><div className="button-row"><button className="button button--primary" onClick={() => window.confirm(`确认创建“${item.title}”任务？`) && accept.mutate(item.id)}><CheckCircle2 size={16} />创建任务</button><button className="button button--quiet" onClick={() => reject.mutate(item.id)}><XCircle size={16} />忽略</button></div></article>)}</section>}
      {(reviews.data ?? []).length === 0 ? <EmptyState title="当前没有复习项" description="完成学习活动后，符合规则的知识点会出现在这里。" /> : groups.map((name) => {
        const rows = (reviews.data ?? []).filter((item) => group(item) === name && ["pending", "scheduled"].includes(item.status));
        if (!rows.length) return null;
        return <section className="review-group" key={name}><header><Clock3 size={18} /><h2>{name}</h2><span>{rows.length}</span></header>{rows.map((item) => <article key={item.id}><div><h3>{item.knowledge_point_title}</h3><p>{item.reason_summary}</p><small>{new Date(item.due_at).toLocaleDateString("zh-CN")} · 优先分 {Math.round(item.priority_score)} · {item.status}</small></div><Link className="button button--secondary" to={`/mastery/${item.knowledge_point_id}`}>查看知识点</Link></article>)}</section>;
      })}
    </main>
  );
}
