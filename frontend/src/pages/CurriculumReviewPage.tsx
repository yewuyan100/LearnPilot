import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, BookOpen, CheckCircle2, Clock3, GitBranch, Send, ShieldAlert } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { findFirstLesson, prepareFirstLesson } from "../api/productFlow";
import { curriculumApi } from "../api/resources";
import { ErrorState, LoadingState } from "../components/States";
import { useToast } from "../components/toast-context";
import type { CurriculumProposal } from "../types";

const statusLabels: Record<string, string> = {
  pending: "等待审查",
  review_required: "需要审查",
  accepted: "已接受",
  rejected: "已拒绝",
  expired: "已过期",
};

export function CurriculumReviewPage() {
  const proposalId = useParams().id ?? "";
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const proposalQuery = useQuery({
    queryKey: ["curriculum-proposal", proposalId],
    queryFn: () => curriculumApi.get(proposalId),
    enabled: Boolean(proposalId),
  });
  const refresh = (proposal: CurriculumProposal) => {
    queryClient.setQueryData(["curriculum-proposal", proposalId], proposal);
  };
  const decision = useMutation({
    mutationFn: (value: "accept" | "reject") => curriculumApi.decide(proposalId, value, proposalQuery.data!.version),
    onSuccess: (proposal) => { refresh(proposal); showToast(proposal.status === "accepted" ? "路线建议已接受" : "路线建议已拒绝", "success"); },
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const firstLesson = useQuery({
    queryKey: ["first-lesson", proposalId, proposalQuery.data?.architecture.status],
    queryFn: () => findFirstLesson(proposalQuery.data!),
    enabled: proposalQuery.data?.architecture.status === "published",
    retry: false,
  });
  const prepare = useMutation({
    mutationFn: (courseIds: number[] = []) => prepareFirstLesson(proposalQuery.data!, courseIds),
    onSuccess: async (result) => {
      queryClient.setQueryData(
        ["first-lesson", proposalId, "published"],
        result.lesson,
      );
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["lessons", result.lesson.course_id] }),
        queryClient.invalidateQueries({ queryKey: ["today"] }),
        queryClient.invalidateQueries({ queryKey: ["next-learning-action"] }),
      ]);
      showToast("第一步内容已经准备好", "success");
    },
    onError: () => showToast("第一步内容还没有准备好，可以稍后重新准备", "error"),
  });
  const publish = useMutation({
    mutationFn: () => curriculumApi.publish(proposalQuery.data!),
    onSuccess: async (result) => {
      refresh(result.proposal);
      await Promise.all([
        proposalQuery.refetch(),
        queryClient.invalidateQueries({ queryKey: ["courses"] }),
      ]);
      showToast("行动路线已开始使用，正在准备第一步", "success");
      prepare.mutate(result.publication.course_ids);
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });

  if (proposalQuery.isLoading) return <div className="page"><LoadingState label="正在读取路线建议"/></div>;
  if (proposalQuery.isError || !proposalQuery.data) return <div className="page"><ErrorState message={proposalQuery.error?.message ?? "路线建议不存在"}/></div>;
  const proposal = proposalQuery.data;
  const curriculum = proposal.curriculum;
  const canDecide = proposal.status === "pending" || proposal.status === "review_required";
  const published = proposal.architecture.status === "published";

  return <div className="page curriculum-review-page">
    <Link className="text-link" to={`/items/${proposal.goal.id}`}><ArrowLeft size={15}/>返回事项</Link>
    <header className="page-header page-header--split curriculum-review-header">
      <div><p className="page-kicker">路线建议</p><h1>{curriculum.course_title}</h1><p>{curriculum.course_description}</p></div>
      <div className="curriculum-review-actions"><span className={`status status--${proposal.status}`}>{statusLabels[proposal.status] ?? proposal.status}</span>{canDecide && <button className="button button--secondary" disabled={decision.isPending} onClick={() => decision.mutate("reject")}><ShieldAlert size={16}/>拒绝建议</button>}{canDecide && <button className="button button--primary" disabled={decision.isPending} onClick={() => decision.mutate("accept")}><CheckCircle2 size={16}/>接受建议</button>}{proposal.status === "accepted" && !published && <button className="button button--primary" disabled={publish.isPending || proposal.architecture.status !== "ready"} onClick={() => publish.mutate()}><Send size={16}/>{publish.isPending ? "正在启用" : "确认使用这条路线"}</button>}{published && firstLesson.data && <Link className="button button--primary" to={`/lessons/${firstLesson.data.id}`}>开始第一步</Link>}{published && !firstLesson.data && <button className="button button--primary" disabled={prepare.isPending || firstLesson.isLoading} onClick={() => prepare.mutate([])}>{prepare.isPending ? "正在准备" : "重新准备第一步"}</button>}{published && <Link className="button button--secondary" to={`/items/${proposal.goal.id}`}>查看事项</Link>}</div>
    </header>

    <section className={`notice ${proposal.grounding_mode === "goal_only" ? "notice--warning" : "notice--success"}`}><ShieldAlert size={17}/><span>{proposal.grounding_mode === "goal_only" ? "尚未关联资料：请重点核对范围、拆分与步骤顺序。" : `已根据 ${proposal.material_ids.length} 份关联资料核对。`}</span></section>
    {published && !firstLesson.isLoading && !firstLesson.data && <section className="notice notice--warning"><span>第一步内容还没有准备好。路线已经保留，你可以随时重新准备。</span></section>}
    {published && <section className="initial-plan-preview" aria-labelledby="initial-plan-title"><div><span>建议安排预览</span><h2 id="initial-plan-title">每天约 {proposal.goal.daily_minutes} 分钟，预计 {Math.max(1, Math.ceil(curriculum.estimated_duration / proposal.goal.daily_minutes))} 天完成当前路线</h2><p>这只是根据事项时间预算生成的轻量预览；你可以先开始第一步，需要时再调整完整安排。</p></div><Link className="text-link" to={`/items?advanced=planning&goal_id=${proposal.goal.id}`}>查看并调整安排</Link></section>}

    <section className="curriculum-review-ledger" aria-label="学习路径摘要">
      <article><span>所属事项</span><strong>{proposal.goal.title}</strong><small>{proposal.goal.current_level || "当前基础未填写"}</small></article>
      <article><Clock3 size={17}/><span>时间预算</span><strong>{curriculum.estimated_duration} 分钟</strong><small>每日 {proposal.goal.daily_minutes} 分钟 · {proposal.goal.target_date ?? "无截止日期"}</small></article>
      <article><BookOpen size={17}/><span>学习步骤</span><strong>{curriculum.knowledge_points.length} 个</strong><small>{curriculum.lesson_blueprints.length} 个内容预览</small></article>
      <article><GitBranch size={17}/><span>顺序依赖</span><strong>{curriculum.prerequisites.length} 条</strong><small>启用前仍会检查路线完整性</small></article>
    </section>

    <div className="curriculum-review-grid">
      <main className="curriculum-path-panel">
        <header className="section-heading"><div><h2>推荐学习顺序</h2><p>{curriculum.coverage_report.goal_alignment}</p></div></header>
        <ol>{curriculum.learning_order.map((title, index) => { const point = curriculum.knowledge_points.find((item) => item.title === title)!; return <li key={title}><span>{String(index + 1).padStart(2, "0")}</span><div><h3>{point.title}</h3><p>{point.description}</p><small>{point.difficulty_label} · {point.learning_objectives.join("；")}</small></div></li>; })}</ol>
      </main>
      <aside className="curriculum-review-sidebar">
        <section><header><h2>步骤顺序</h2><GitBranch size={17}/></header>{curriculum.prerequisites.map((edge) => <article className="curriculum-edge" key={`${edge.prerequisite_title}-${edge.dependent_title}`}><strong>{edge.prerequisite_title}</strong><span>→</span><strong>{edge.dependent_title}</strong><p>{edge.rationale}</p></article>)}{!curriculum.prerequisites.length && <p className="muted">没有额外顺序依赖。</p>}</section>
        <section><header><h2>覆盖与假设</h2></header><p><strong>覆盖：</strong>{curriculum.coverage_report.covered_topics.join("、")}</p>{curriculum.coverage_report.gaps.length > 0 && <p><strong>未覆盖：</strong>{curriculum.coverage_report.gaps.join("、")}</p>}<ul>{curriculum.assumptions.map((item) => <li key={item}>{item}</li>)}</ul></section>
      </aside>
    </div>

    <section className="section-card curriculum-blueprints"><header className="section-heading"><div><h2>学习步骤预览</h2><p>这里只定义每一步的目的与时长；不会提前生成讲解、例子、练习或检查内容。</p></div><Link className="text-link" to={`/course-architecture/drafts/${proposal.architecture.draft_id}`}>高级：编辑路线结构</Link></header><div>{curriculum.lesson_blueprints.map((item, index) => <article key={item.knowledge_point}><span>{index + 1}</span><div><strong>{item.knowledge_point}</strong><p>{item.lesson_goal}</p></div><small>{item.estimated_minutes} 分钟 · 等待内容准备</small></article>)}</div></section>
  </div>;
}
