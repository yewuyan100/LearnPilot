import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  CalendarClock,
  CheckCircle2,
  GitCommitHorizontal,
  RotateCcw,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { planAdjustmentsApi } from "../api/resources";
import { ErrorState, LoadingState } from "../components/States";
import { useToast } from "../components/toast-context";
import type { PlanAdjustmentProposal } from "../types";

const statusLabels: Record<string, string> = {
  pending: "等待确认",
  accepted: "已接受并应用",
  rejected: "已拒绝",
  expired: "已过期",
};

const masteryLabels: Record<string, string> = {
  unassessed: "尚未评估",
  beginner: "入门",
  developing: "发展中",
  proficient: "熟练",
  strong: "稳固",
};

export function PlanAdjustmentReviewPage() {
  const proposalId = useParams().id ?? "";
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const proposalQuery = useQuery({
    queryKey: ["plan-adjustment", proposalId],
    queryFn: () => planAdjustmentsApi.get(proposalId),
    enabled: Boolean(proposalId),
  });
  const decision = useMutation({
    mutationFn: (value: "accept" | "reject") =>
      planAdjustmentsApi.decide(proposalQuery.data!, value),
    onSuccess: async (proposal: PlanAdjustmentProposal) => {
      queryClient.setQueryData(["plan-adjustment", proposalId], proposal);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["next-learning-action"] }),
        queryClient.invalidateQueries({ queryKey: ["today"] }),
        queryClient.invalidateQueries({ queryKey: ["study-plan"] }),
      ]);
      showToast(
        proposal.status === "accepted"
          ? "新的安排已启用"
          : "已保留原安排，不应用本次调整",
        "success",
      );
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });

  if (proposalQuery.isLoading) {
    return <div className="page"><LoadingState label="正在读取 AI 建议" /></div>;
  }
  if (proposalQuery.isError || !proposalQuery.data) {
    return <div className="page"><ErrorState message={proposalQuery.error?.message ?? "AI 建议不存在"} /></div>;
  }

  const proposal = proposalQuery.data;
  const canDecide = proposal.status === "pending";

  return (
    <div className="page plan-adjustment-review-page">
      <Link className="text-link" to="/workspace"><ArrowLeft size={15} />返回工作台</Link>
      <header className="page-header page-header--split plan-adjustment-review-header">
        <div>
          <p className="page-kicker">AI建议</p>
          <h1>审查接下来的安排</h1>
          <p>系统只提出建议；只有在你明确接受后，接下来的安排才会变化。</p>
        </div>
        <div className="plan-adjustment-review-actions">
          <span className={`status status--${proposal.status}`}>
            {statusLabels[proposal.status] ?? proposal.status}
          </span>
          {canDecide && (
            <button
              className="button button--secondary"
              disabled={decision.isPending}
              onClick={() => decision.mutate("reject")}
            >
              <XCircle size={16} />拒绝调整
            </button>
          )}
          {canDecide && (
            <button
              className="button button--primary"
              disabled={decision.isPending}
              onClick={() => decision.mutate("accept")}
            >
              <CheckCircle2 size={16} />
              {decision.isPending ? "正在重新排期…" : "接受调整"}
            </button>
          )}
        </div>
      </header>

      <section className="notice notice--warning">
        <ShieldCheck size={18} />
        <span>确认前，现有安排保持不变；页面不会展示模型内部推理。</span>
      </section>

      <section className="plan-adjustment-review-grid" aria-label="计划调整摘要">
        <article className="section-card">
          <header><RotateCcw size={19} /><span>调整原因</span></header>
          <h2>{proposal.mastery_change.knowledge_point_title}</h2>
          <p>{proposal.reason}</p>
          <small>
            熟练状态 {masteryLabels[proposal.mastery_change.old_level] ?? proposal.mastery_change.old_level}
            {" → "}
            {masteryLabels[proposal.mastery_change.new_level] ?? proposal.mastery_change.new_level}
            {` · 置信度 ${Math.round(proposal.mastery_change.confidence)}%`}
          </small>
        </article>
        <article className="section-card">
          <header><GitCommitHorizontal size={19} /><span>建议变化</span></header>
          <h2>增加一次复习</h2>
          <p>{proposal.suggestion}</p>
          <small>依据 {proposal.mastery_evidence_ids.length} 条最近练习与评估记录</small>
        </article>
        <article className="section-card">
          <header><CalendarClock size={19} /><span>影响</span></header>
          <h2>更新接下来的安排</h2>
          <p>{proposal.impact}</p>
          <small>接受后才会生效</small>
        </article>
      </section>

      {proposal.application && (
        <section className="notice notice--success plan-adjustment-application">
          <CheckCircle2 size={18} />
          <div>
            <strong>新的安排已经生效</strong>
            <p>
              新增 {proposal.application.created_task_ids.length} 项、沿用 {proposal.application.reused_task_ids.length} 项、
              调整 {proposal.application.rescheduled_task_ids.length} 项。
            </p>
          </div>
          <Link className="button button--primary" to="/today">返回今日学习</Link>
        </section>
      )}

      {proposal.status === "rejected" && (
        <section className="notice">
          <ShieldCheck size={18} />
          <span>你拒绝了这次建议。现有安排没有变化。</span>
        </section>
      )}
    </div>
  );
}
