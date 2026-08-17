import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, ClipboardCheck, History, RefreshCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { diagnosticsApi } from "../api/resources";
import { ErrorState, LoadingState } from "./States";
import { useToast } from "./toast-context";
import { formatDateTime, statusLabel } from "../utils/format";
import type { AttemptQuestion, Course, DiagnosticKnowledgeResult, DiagnosticSession } from "../types";

type AnswerValue = { answer?: Array<string | boolean> | null; answer_text?: string | null };

const abilityLabel: Record<string, string> = {
  evidence_insufficient: "证据不足",
  beginner: "刚刚起步",
  developing: "正在发展",
  proficient: "较为熟练",
  strong: "掌握稳固",
};

export function CourseDiagnosticPanel({ course }: { course: Course }) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const latest = useQuery({
    queryKey: ["diagnostic-latest", course.id],
    queryFn: () => diagnosticsApi.latest(course.id),
    enabled: course.status === "active",
  });
  const history = useQuery({
    queryKey: ["diagnostic-history", course.id],
    queryFn: () => diagnosticsApi.history(course.id),
    enabled: course.status === "active",
  });
  const [answers, setAnswers] = useState<Record<number, AnswerValue>>({});
  const createRequest = useRef(crypto.randomUUID());
  const submitRequest = useRef(crypto.randomUUID());

  useEffect(() => {
    const questions = latest.data?.attempt?.questions ?? [];
    setAnswers(Object.fromEntries(questions.map((question) => [
      question.id,
      { answer: question.saved_answer, answer_text: question.saved_answer_text },
    ])));
    submitRequest.current = crypto.randomUUID();
  }, [latest.data?.id, latest.data?.attempt?.questions]);

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["diagnostic-latest", course.id] }),
      queryClient.invalidateQueries({ queryKey: ["diagnostic-history", course.id] }),
      queryClient.invalidateQueries({ queryKey: ["next-learning-action"] }),
    ]);
  };
  const generate = useMutation({
    mutationFn: (supersedes: number | null) => diagnosticsApi.create(course.id, {
      request_id: createRequest.current,
      questions_per_point: 2,
      question_types: ["single_choice", "multiple_choice", "true_false", "short_answer"],
      difficulty: "medium",
      supersedes_session_id: supersedes,
    }),
    onSuccess: async (diagnostic) => {
      createRequest.current = crypto.randomUUID();
      await refresh();
      showToast(
        diagnostic.status === "generation_failed" ? "诊断未能生成，请查看原因后重试" : "诊断已准备好",
        diagnostic.status === "generation_failed" ? "error" : "success",
      );
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const submit = useMutation({
    mutationFn: (diagnostic: DiagnosticSession) => diagnosticsApi.submit(diagnostic.id, {
      request_id: submitRequest.current,
      expected_version: diagnostic.version,
      answers: diagnostic.attempt!.questions.map((question) => ({
        question_id: question.id,
        answer: answers[question.id]?.answer ?? null,
        answer_text: answers[question.id]?.answer_text ?? null,
      })),
    }),
    onSuccess: async () => {
      submitRequest.current = crypto.randomUUID();
      await refresh();
      showToast("诊断已提交，能力基线已更新", "success");
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });

  if (course.status !== "active") return (
    <section className="diagnostic-panel">
      <header><div><span className="page-kicker">初始诊断</span><h3>发布课程后开始诊断</h3></div></header>
      <p className="muted">只有正式可用的课程才能生成基于真实资料的诊断。</p>
    </section>
  );
  if (latest.isLoading || history.isLoading) return <LoadingState label="正在读取课程诊断" />;
  if (latest.isError || history.isError) return (
    <ErrorState message={(latest.error ?? history.error)!.message} onRetry={() => void refresh()} />
  );
  const diagnostic = latest.data;
  const canSubmit = diagnostic?.status === "pending" && diagnostic.attempt?.questions.every(
    (question) => isAnswered(answers[question.id]),
  );

  return (
    <section className="diagnostic-panel" aria-label="课程初始诊断">
      <header>
        <div><span className="page-kicker">能力基线</span><h3>初始诊断</h3><p>题目只使用这门课程已核验的真实资料。</p></div>
        {diagnostic && <span className={`status status--${diagnostic.status}`}>{statusLabel[diagnostic.status] ?? diagnostic.status}</span>}
      </header>

      {!diagnostic && (
        <div className="diagnostic-empty">
          <ClipboardCheck size={24} />
          <div><strong>尚未诊断</strong><p>先确认当前基础，计划才能把时间用在真正需要的知识点上。</p></div>
          <button className="button button--primary" disabled={generate.isPending} onClick={() => generate.mutate(null)}>
            {generate.isPending ? "正在生成…" : "开始诊断"}
          </button>
        </div>
      )}

      {generate.isPending && <div className="generation-progress" role="status"><div><strong>正在准备诊断</strong><small>系统正按知识点分批读取课程资料并检查题目来源。</small></div><progress /></div>}

      {diagnostic?.status === "generation_failed" && (
        <div className="notice notice--warning diagnostic-failure">
          <AlertTriangle size={18} />
          <div><strong>诊断生成失败</strong><p>{diagnostic.last_error_message || "课程资料暂时无法形成可靠题目。"}</p></div>
          <button className="button button--secondary" disabled={generate.isPending} onClick={() => generate.mutate(diagnostic.id)}><RefreshCw size={16} />重新诊断</button>
        </div>
      )}

      {diagnostic?.status === "pending" && diagnostic.attempt && (
        <form className="diagnostic-form" onSubmit={(event) => { event.preventDefault(); if (canSubmit) submit.mutate(diagnostic); }}>
          <CoverageSummary diagnostic={diagnostic} />
          <div className="diagnostic-questions">
            {diagnostic.attempt.questions.map((question, index) => (
              <DiagnosticQuestion
                key={question.id}
                index={index + 1}
                question={question}
                value={answers[question.id] ?? {}}
                onChange={(value) => setAnswers((current) => ({ ...current, [question.id]: value }))}
              />
            ))}
          </div>
          <div className="form-actions diagnostic-submit">
            <span>{canSubmit ? "所有题目已作答，可以提交。" : "完成全部题目后提交诊断。"}</span>
            <button className="button button--primary" type="submit" disabled={!canSubmit || submit.isPending}>
              {submit.isPending ? "正在提交…" : "提交诊断"}
            </button>
          </div>
        </form>
      )}

      {diagnostic && ["submitted", "review_required", "evidence_insufficient"].includes(diagnostic.status) && (
        <DiagnosticResults diagnostic={diagnostic} onReassess={() => generate.mutate(diagnostic.id)} pending={generate.isPending} />
      )}

      {!!history.data?.total && (
        <details className="diagnostic-history">
          <summary><History size={16} />诊断历史 <span>{history.data.total}</span></summary>
          <div>
            {history.data.items.map((item) => (
              <article key={item.id}>
                <span className={`status status--${item.status}`}>{statusLabel[item.status] ?? item.status}</span>
                <div><strong>{formatDateTime(item.submitted_at ?? item.created_at)}</strong><small>覆盖 {Math.round((item.coverage_report.coverage_rate ?? 0) * 100)}% · {item.results.filter((result) => result.is_skill_gap).length} 个技能缺口</small></div>
              </article>
            ))}
          </div>
        </details>
      )}
    </section>
  );
}

function CoverageSummary({ diagnostic }: { diagnostic: DiagnosticSession }) {
  const coverage = diagnostic.coverage_report;
  return <div className="diagnostic-coverage"><div><span>知识点覆盖</span><strong>{coverage.covered_count ?? 0}<small> / {coverage.knowledge_point_count ?? 0}</small></strong></div><div><span>诊断题</span><strong>{coverage.question_count ?? diagnostic.attempt?.questions.length ?? 0}</strong></div><div><span>资料来源</span><strong>已核验</strong></div></div>;
}

function DiagnosticQuestion({ index, question, value, onChange }: {
  index: number;
  question: AttemptQuestion;
  value: AnswerValue;
  onChange: (value: AnswerValue) => void;
}) {
  const name = `diagnostic-${question.id}`;
  if (question.question_type === "short_answer") return (
    <fieldset className="diagnostic-question"><legend><span>{index}</span>{question.stem}</legend><textarea aria-label={`第 ${index} 题回答`} rows={5} value={value.answer_text ?? ""} onChange={(event) => onChange({ answer: null, answer_text: event.target.value })} placeholder="用自己的话说明；证据不足时系统会提示人工检查。" /></fieldset>
  );
  const options = question.question_type === "true_false"
    ? [{ id: true, text: "正确" }, { id: false, text: "错误" }]
    : (question.options ?? []).map((option) => ({ id: option.id, text: option.text }));
  const multiple = question.question_type === "multiple_choice";
  return (
    <fieldset className="diagnostic-question"><legend><span>{index}</span>{question.stem}</legend><div className="diagnostic-options">{options.map((option) => {
      const selected = (value.answer ?? []).includes(option.id);
      return <label key={String(option.id)} className={selected ? "is-selected" : ""}><input type={multiple ? "checkbox" : "radio"} name={name} checked={selected} onChange={() => {
        if (!multiple) onChange({ answer: [option.id], answer_text: null });
        else {
          const current = value.answer ?? [];
          onChange({ answer: selected ? current.filter((item) => item !== option.id) : [...current, option.id], answer_text: null });
        }
      }} /><span>{option.text}</span></label>;
    })}</div></fieldset>
  );
}

function isAnswered(value?: AnswerValue) {
  return Boolean(value?.answer?.length || value?.answer_text?.trim());
}

function DiagnosticResults({ diagnostic, onReassess, pending }: {
  diagnostic: DiagnosticSession;
  onReassess: () => void;
  pending: boolean;
}) {
  const gaps = diagnostic.results.filter((result) => result.is_skill_gap);
  const reviewCount = diagnostic.results.flatMap((result) => result.assessments).filter((item) => item.recommend_manual_review).length;
  return (
    <div className="diagnostic-results">
      <div className="diagnostic-result-header"><div><CheckCircle2 size={22} /><div><strong>诊断结果已形成</strong><p>{gaps.length ? `识别到 ${gaps.length} 个需要优先补强的知识点。` : "当前没有被可靠识别为技能缺口的知识点。"}</p></div></div><button className="button button--secondary" disabled={pending} onClick={onReassess}><RefreshCw size={16} />重新诊断</button></div>
      {reviewCount > 0 && <div className="notice notice--warning">有 {reviewCount} 道简答题需要人工检查；系统没有为低置信度答案编造正式分数。</div>}
      <div className="diagnostic-result-grid">{diagnostic.results.map((result) => <ResultCard key={result.id} result={result} />)}</div>
    </div>
  );
}

function ResultCard({ result }: { result: DiagnosticKnowledgeResult }) {
  return <article className={result.is_skill_gap ? "is-gap" : ""}><header><div><strong>{result.knowledge_point_title}</strong><span>{abilityLabel[result.ability_level] ?? result.ability_level}</span></div>{result.is_skill_gap && <span className="status status--review_required">优先补强</span>}</header><div className="result-score"><strong>{result.score_percentage == null ? "—" : `${Math.round(result.score_percentage)}%`}</strong><span>置信度 {Math.round(result.confidence * 100)}%</span></div><p>{result.reason}</p><small>{result.answered_count} 题作答 · {result.evidence_source_ids.length} 个真实资料证据</small></article>;
}
