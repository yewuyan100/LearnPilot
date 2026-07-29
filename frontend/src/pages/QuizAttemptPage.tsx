import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, ArrowLeft, Check, Send } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { attemptsApi } from "../api/resources";
import { ErrorState, LoadingState } from "../components/States";
import { useToast } from "../components/toast-context";
import type { AttemptQuestion } from "../types";

type DraftAnswer = {
  answer?: Array<string | boolean> | null;
  answer_text?: string | null;
};

function isAnswered(question: AttemptQuestion, answer: DraftAnswer | undefined) {
  if (question.question_type === "short_answer") {
    return Boolean(answer?.answer_text?.trim());
  }
  return Boolean(answer?.answer?.length);
}

export function QuizAttemptPage() {
  const { id } = useParams();
  const attemptId = Number(id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [answers, setAnswers] = useState<Record<number, DraftAnswer>>({});
  const submitRequestId = useRef(crypto.randomUUID());
  const attempt = useQuery({
    queryKey: ["quiz-attempt", attemptId],
    queryFn: () => attemptsApi.get(attemptId),
    enabled: Number.isFinite(attemptId),
  });
  useEffect(() => {
    if (!attempt.data) return;
    setAnswers(
      Object.fromEntries(
        attempt.data.questions.map((question) => [
          question.id,
          {
            answer: question.saved_answer,
            answer_text: question.saved_answer_text,
          },
        ]),
      ),
    );
  }, [attempt.data]);
  useEffect(() => {
    if (attempt.data?.status === "completed") {
      navigate(`/quiz-attempts/${attempt.data.id}/result`, { replace: true });
    }
  }, [attempt.data?.id, attempt.data?.status, navigate]);
  const save = useMutation({
    mutationFn: ({
      questionId,
      value,
    }: {
      questionId: number;
      value: DraftAnswer;
    }) => attemptsApi.save(attemptId, questionId, value),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["quiz-attempt", attemptId] }),
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const submit = useMutation({
    mutationFn: () =>
      attemptsApi.submit(attemptId, {
        request_id: submitRequestId.current,
        answers: Object.entries(answers).map(([questionId, value]) => ({
          question_id: Number(questionId),
          ...value,
        })),
      }),
    onSuccess: (result) => {
      if (result.status === "completed") {
        navigate(`/quiz-attempts/${result.id}/result`);
      }
    },
    onError: (error: Error) => {
      showToast(error.message, "error");
      attempt.refetch();
    },
  });
  const unanswered = useMemo(
    () =>
      (attempt.data?.questions ?? []).filter(
        (question) => !isAnswered(question, answers[question.id]),
      ).length,
    [answers, attempt.data],
  );
  const update = (questionId: number, value: DraftAnswer) => {
    setAnswers((current) => ({ ...current, [questionId]: value }));
    save.mutate({ questionId, value });
  };

  if (attempt.isLoading) return <LoadingState label="正在恢复测验进度" />;
  if (attempt.isError || !attempt.data) {
    return (
      <ErrorState
        message={(attempt.error as Error)?.message ?? "测验不存在"}
        onRetry={() => attempt.refetch()}
      />
    );
  }
  if (attempt.data.status === "completed") {
    return <LoadingState label="正在打开测验结果" />;
  }

  return (
    <div className="quiz-shell">
      <header className="quiz-header">
        <button className="text-button" onClick={() => navigate("/activities")}>
          <ArrowLeft size={16} />退出测验
        </button>
        <div>
          <span className="eyebrow">进行中的测验</span>
          <h1>{attempt.data.activity_title}</h1>
        </div>
        <div className="quiz-progress">
          <strong>{attempt.data.questions.length - unanswered}/{attempt.data.questions.length}</strong>
          <span>已作答</span>
        </div>
      </header>

      {attempt.data.status === "failed" && (
        <aside className="quiz-error">
          <AlertCircle size={18} />
          <div>
            <strong>批改尚未完成</strong>
            <p>{attempt.data.error_message}。答案已保存，可使用原提交内容重试。</p>
          </div>
        </aside>
      )}

      <main className="quiz-content">
        <nav className="quiz-nav" aria-label="题目导航">
          {attempt.data.questions.map((question) => (
            <a
              key={question.id}
              href={`#question-${question.id}`}
              className={isAnswered(question, answers[question.id]) ? "answered" : ""}
            >
              {question.question_index}
            </a>
          ))}
        </nav>
        <section className="quiz-question-list">
          {attempt.data.questions.map((question) => {
            const value = answers[question.id] ?? {};
            return (
              <article
                key={question.id}
                id={`question-${question.id}`}
                className="quiz-question"
              >
                <header>
                  <span className="question-number">{question.question_index}</span>
                  <span>{question.points} 分 · {question.difficulty}</span>
                  {isAnswered(question, value) && <Check size={16} />}
                </header>
                <h2>{question.stem}</h2>
                {question.question_type === "single_choice" &&
                  question.options?.map((option) => (
                    <label key={option.id} className="answer-option">
                      <input
                        type="radio"
                        name={`question-${question.id}`}
                        checked={value.answer?.[0] === option.id}
                        onChange={() => update(question.id, { answer: [option.id] })}
                      />
                      <strong>{option.id}</strong><span>{option.text}</span>
                    </label>
                  ))}
                {question.question_type === "multiple_choice" &&
                  question.options?.map((option) => {
                    const selected = (value.answer ?? []).includes(option.id);
                    return (
                      <label key={option.id} className="answer-option">
                        <input
                          type="checkbox"
                          checked={selected}
                          onChange={(event) => {
                            const current = (value.answer ?? []) as string[];
                            update(question.id, {
                              answer: event.target.checked
                                ? [...current, option.id]
                                : current.filter((item) => item !== option.id),
                            });
                          }}
                        />
                        <strong>{option.id}</strong><span>{option.text}</span>
                      </label>
                    );
                  })}
                {question.question_type === "true_false" && (
                  <div className="true-false-grid">
                    {[true, false].map((option) => (
                      <label key={String(option)} className="answer-option">
                        <input
                          type="radio"
                          name={`question-${question.id}`}
                          checked={value.answer?.[0] === option}
                          onChange={() => update(question.id, { answer: [option] })}
                        />
                        <span>{option ? "正确" : "错误"}</span>
                      </label>
                    ))}
                  </div>
                )}
                {question.question_type === "short_answer" && (
                  <textarea
                    aria-label={`第 ${question.question_index} 题简答`}
                    value={value.answer_text ?? ""}
                    maxLength={4000}
                    placeholder="用自己的话回答；系统按资料中的概念和评分标准批改。"
                    onChange={(event) =>
                      setAnswers((current) => ({
                        ...current,
                        [question.id]: { answer_text: event.target.value },
                      }))
                    }
                    onBlur={() =>
                      save.mutate({
                        questionId: question.id,
                        value: answers[question.id] ?? { answer_text: "" },
                      })
                    }
                  />
                )}
              </article>
            );
          })}
        </section>
      </main>
      <footer className="quiz-submit-bar">
        <p>{unanswered ? `还有 ${unanswered} 题未作答，提交后未作答题计 0 分。` : "全部题目已作答。"}</p>
        <button
          className="button button--primary"
          disabled={submit.isPending || save.isPending}
          onClick={() => {
            if (
              window.confirm(
                unanswered
                  ? `仍有 ${unanswered} 题未作答，确认提交吗？`
                  : "确认提交测验并开始批改吗？",
              )
            ) {
              submit.mutate();
            }
          }}
        >
          <Send size={16} />{submit.isPending ? "正在批改…" : "提交测验"}
        </button>
      </footer>
    </div>
  );
}
