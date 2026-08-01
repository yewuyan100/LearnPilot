import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CalendarClock, History, Layers3 } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { masteryApi } from "../api/resources";
import { EmptyState, ErrorState, LoadingState } from "../components/States";

const evidenceLabel: Record<string, string> = {
  objective_quiz: "客观题", short_answer_quiz: "简答题", wrong_answer: "活跃错题",
  successful_review: "成功复习", task_completion: "任务完成",
  learning_session: "学习会话", self_assessment: "用户自评",
};

export function MasteryDetailPage() {
  const id = Number(useParams().id);
  const queryClient = useQueryClient();
  const detail = useQuery({ queryKey: ["mastery", id], queryFn: () => masteryApi.get(id), enabled: Number.isInteger(id) });
  const assess = useMutation({
    mutationFn: (rating: number) => masteryApi.selfAssessment(id, rating),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["mastery", id] });
      queryClient.invalidateQueries({ queryKey: ["mastery"] });
    },
  });
  if (detail.isLoading) return <main className="page"><LoadingState label="正在读取掌握度依据…" /></main>;
  if (detail.isError || !detail.data) return <main className="page"><ErrorState message="掌握度详情暂时无法加载" onRetry={() => detail.refetch()} /></main>;
  const data = detail.data;
  const categoryScores = (data.evidence_summary.category_scores ?? {}) as Record<string, number>;
  return (
    <main className="page mastery-detail-page">
      <Link className="button button--quiet mastery-back" to="/mastery"><ArrowLeft size={16} />返回掌握度</Link>
      <header className="page-header">
        <p className="page-kicker">{data.course_title}</p>
        <h1>{data.knowledge_point_title}</h1>
        <p>算法版本 {data.algorithm_version} · 最近计算 {new Date(data.calculated_at).toLocaleString("zh-CN")}</p>
      </header>
      <section className="mastery-hero">
        <article><span>当前掌握度</span><strong>{data.mastery_score === null ? "未评估" : Math.round(data.mastery_score)}</strong><small>{data.mastery_score === null ? "没有有效证据" : "/ 100"}</small></article>
        <article><span>当前置信度</span><strong>{Math.round(data.confidence_score)}</strong><small>/ 100</small></article>
        <article><span>证据数量</span><strong>{data.evidence_count}</strong><small>条真实记录</small></article>
      </section>
      {data.mastery_score !== null && data.confidence_score < 45 && <div className="notice notice--warning">当前表现可能较好，但证据仍较少，请结合后续测验继续观察。</div>}
      <section className="adaptive-grid">
        <article className="adaptive-panel">
          <header><Layers3 size={18} /><h2>证据组成</h2></header>
          {Object.keys(categoryScores).length === 0 ? <EmptyState title="暂无有效证据" description="完成测验、复习或学习记录后会自动更新。" /> : (
            <div className="evidence-bars">{Object.entries(categoryScores).map(([kind, score]) => (
              <div key={kind}><span>{evidenceLabel[kind] ?? kind}</span><div><i style={{ width: `${score}%` }} /></div><strong>{Math.round(score)}</strong></div>
            ))}</div>
          )}
        </article>
        <article className="adaptive-panel">
          <header><CalendarClock size={18} /><h2>复习建议</h2></header>
          {data.review_schedule ? <div className="review-reason"><strong>{data.review_schedule.overdue ? "已逾期" : new Date(data.review_schedule.due_at).toLocaleDateString("zh-CN")}</strong><p>{data.review_schedule.reason_summary}</p></div> : <p className="muted">当前没有薄弱复习安排。</p>}
          <label className="field"><span>更新自评（1–5，仅作低权重证据）</span><select defaultValue="" onChange={(event) => event.target.value && assess.mutate(Number(event.target.value))}><option value="" disabled>选择自评</option>{[1,2,3,4,5].map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
        </article>
      </section>
      <section className="adaptive-panel">
        <header><History size={18} /><h2>掌握度历史</h2></header>
        {data.snapshots.length === 0 ? <p className="muted">还没有快照。</p> : <div className="snapshot-list">{data.snapshots.map((snapshot) => <div key={snapshot.id}><time>{new Date(snapshot.calculated_at).toLocaleString("zh-CN")}</time><strong>{snapshot.mastery_score === null ? "未评估" : Math.round(snapshot.mastery_score)}</strong><span>置信度 {Math.round(snapshot.confidence_score)} · {snapshot.trigger_type}</span></div>)}</div>}
      </section>
      <section className="adaptive-panel">
        <header><Layers3 size={18} /><h2>最近证据</h2></header>
        <div className="evidence-list">{data.evidence.map((item) => <div key={item.id}><strong>{evidenceLabel[item.evidence_type] ?? item.evidence_type}</strong><span>{new Date(item.occurred_at).toLocaleString("zh-CN")}</span><span>归一化 {Math.round(item.normalized_score)} · 类别权重 {item.weight}</span><small>来源 {item.source_type} #{item.source_id}</small></div>)}</div>
      </section>
      <p className="mastery-disclaimer">掌握度是根据当前学习记录计算的项目规则分数，不代表正式教育测评结果。</p>
    </main>
  );
}
