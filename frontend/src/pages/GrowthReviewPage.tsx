import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Save } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { dashboardApi, masteryApi, notesApi } from "../api/resources";
import { ErrorState, LoadingState } from "../components/States";
import { useToast } from "../components/toast-context";
import { ProgressPage } from "./ProgressPage";

const tabs = [{ id: "today", label: "今日回看" }, { id: "summary", label: "阶段总结" }, { id: "progress", label: "成长进度" }] as const;

export function GrowthReviewPage() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [params, setParams] = useSearchParams();
  const requested = params.get("tab");
  const active = tabs.some((tab) => tab.id === requested) ? requested : "today";
  const today = useQuery({ queryKey: ["today"], queryFn: dashboardApi.today });
  const progress = useQuery({ queryKey: ["progress"], queryFn: dashboardApi.progress });
  const mastery = useQuery({ queryKey: ["mastery"], queryFn: masteryApi.list });
  const reflections = useQuery({ queryKey: ["notes", "reflection"], queryFn: () => notesApi.list({ noteType: "reflection", pageSize: 5 }) });
  const [completed, setCompleted] = useState("");
  const [problems, setProblems] = useState("");
  const [methods, setMethods] = useState("");
  const [next, setNext] = useState("");
  const saveReflection = useMutation({
    mutationFn: () => notesApi.create({
      title: active === "today" ? `今日复盘 · ${today.data!.date}` : "阶段复盘",
      note_type: "reflection",
      content_markdown: `## 完成情况\n${completed.trim() || "未填写"}\n\n## 遇到的问题\n${problems.trim() || "未填写"}\n\n## 有效方法\n${methods.trim() || "未填写"}\n\n## 下一步重点\n${next.trim() || "未填写"}`,
      links: today.data!.current_goal ? [{ entity_type: "learning_goal", entity_id: today.data!.current_goal.id, relation_type: "reflection_for" }] : [],
    }),
    onSuccess: async () => {
      setCompleted(""); setProblems(""); setMethods(""); setNext("");
      await queryClient.invalidateQueries({ queryKey: ["notes"] });
      showToast("复盘已保存到笔记本", "success");
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });
  if (today.isLoading || progress.isLoading || mastery.isLoading || reflections.isLoading) return <div className="page"><LoadingState label="正在整理成长记录" /></div>;
  if (today.isError || progress.isError || mastery.isError || reflections.isError) return <div className="page"><ErrorState message="成长记录暂时无法加载" onRetry={() => void progress.refetch()} /></div>;
  const mastered = mastery.data!.items.filter((item) => item.mastery_level === "proficient" || item.mastery_level === "strong").length;
  return <div className="page integrated-page growth-page">
    <header className="page-header"><p className="page-kicker">复盘</p><h1>成长复盘</h1><p>基于已有任务、学习会话和掌握证据回看进展，不生成虚构总结。</p></header>
    <nav className="page-tabs" aria-label="成长复盘视图">{tabs.map((tab) => <button key={tab.id} className={active === tab.id ? "is-active" : ""} onClick={() => setParams({ tab: tab.id })}>{tab.label}</button>)}</nav>
    {active === "progress" ? <div className="integrated-content"><ProgressPage /></div> : <>
      <section className="review-ledger"><article><span>今日完成</span><strong>{progress.data!.today_task_completed}<small> / {progress.data!.today_task_total}</small></strong><p>来自今日任务状态</p></article><article><span>最近七天</span><strong>{progress.data!.sessions_last_7_days}</strong><p>次学习会话</p></article><article><span>知识点进展</span><strong>{progress.data!.completed_knowledge_point_count}<small> / {progress.data!.knowledge_point_count}</small></strong><p>课程中的完成状态</p></article><article><span>较稳固掌握</span><strong>{mastered}</strong><p>基于当前掌握证据</p></article></section>
      <section className="review-narrative"><div><span className="page-kicker">{active === "today" ? "今天" : "当前阶段"}</span><h2>{active === "today" ? "把今天收束成下一步" : "用真实记录看清节奏"}</h2><p>{today.data!.tasks.length ? `今天记录了 ${today.data!.tasks.length} 项任务，其中 ${progress.data!.today_task_completed} 项已完成。` : "今天尚无任务记录，可以从目标与计划或今日学习安排下一步。"}</p></div><div><h3>值得继续关注</h3><p>{mastery.data!.items.length ? `目前有 ${mastery.data!.items.length - mastered} 个知识点尚未达到较稳固状态。` : "完成学习活动后，掌握证据会在这里形成可回看的线索。"}</p><p className="muted">这些数字来自现有任务、会话和掌握证据；文字复盘由你填写后保存。</p></div></section>
      <section className="reflection-editor"><header><div><h2>写下真实复盘</h2><p>不会自动补写没有发生的学习经历，保存后作为反思笔记进入笔记本。</p></div>{reflections.data!.items[0] && <Link className="text-link" to={`/notes?note=${reflections.data!.items[0].id}`}>查看最近复盘</Link>}</header><div className="reflection-fields"><label><span>完成情况</span><textarea aria-label="复盘完成情况" value={completed} onChange={(event) => setCompleted(event.target.value)} placeholder="今天或本阶段实际完成了什么"/></label><label><span>遇到的问题</span><textarea aria-label="复盘遇到的问题" value={problems} onChange={(event) => setProblems(event.target.value)} placeholder="哪些地方卡住了"/></label><label><span>有效方法</span><textarea aria-label="复盘有效方法" value={methods} onChange={(event) => setMethods(event.target.value)} placeholder="哪些做法值得保留"/></label><label><span>下一步重点</span><textarea aria-label="复盘下一步重点" value={next} onChange={(event) => setNext(event.target.value)} placeholder="接下来最重要的一步"/></label></div><button className="button button--primary" disabled={saveReflection.isPending || ![completed, problems, methods, next].some((value) => value.trim())} onClick={() => saveReflection.mutate()}><Save size={16}/>{saveReflection.isPending ? "正在保存" : "保存复盘"}</button></section>
    </>}
  </div>;
}
