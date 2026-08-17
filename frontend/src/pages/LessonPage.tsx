import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  BookOpenCheck,
  CheckCircle2,
  ChevronDown,
  Clock3,
  Lightbulb,
  MessageSquareText,
  Play,
  Quote,
  Target,
} from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { prepareLessonAssessment } from "../api/productFlow";
import { lessonsApi, sessionsApi } from "../api/resources";
import { ContextTutor } from "../components/ContextTutor";
import { SafeMarkdown } from "../components/SafeMarkdown";
import { ErrorState, LoadingState } from "../components/States";
import { useToast } from "../components/toast-context";
import { quizAttemptHref } from "../utils/quizNavigation";

export function LessonPage() {
  const { id } = useParams();
  const lessonId = Number(id);
  const [searchParams] = useSearchParams();
  const sessionId = Number(searchParams.get("session"));
  const hasSession = Number.isFinite(sessionId) && sessionId > 0;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [checksOpen, setChecksOpen] = useState(false);
  const lessonQuery = useQuery({
    queryKey: ["lesson", lessonId],
    queryFn: () => lessonsApi.get(lessonId),
    enabled: Number.isFinite(lessonId),
  });
  const sessionQuery = useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => sessionsApi.get(sessionId),
    enabled: hasSession,
  });
  const lesson = lessonQuery.data;
  const version = lesson?.active_version;
  const primaryPoint = version?.knowledge_points.find((point) => point.role === "primary");
  const session = sessionQuery.data;
  const sessionMismatch = Boolean(
    session && version && session.lesson_version_id !== version.id,
  );

  const start = useMutation({
    mutationFn: () => sessionsApi.create({
      learning_goal_id: lesson!.learning_goal_id,
      course_id: lesson!.course_id,
      knowledge_point_id: primaryPoint!.knowledge_point_id,
      lesson_version_id: version!.id,
    }),
    onSuccess: async (created) => {
      await queryClient.invalidateQueries({ queryKey: ["today"] });
      navigate(`/lessons/${lessonId}?session=${created.id}`, { replace: true });
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const complete = useMutation({
    mutationFn: () => sessionsApi.update(session!.id, {
      status: "completed",
      knowledge_point_status: "completed",
      ...(session!.daily_task_id ? { daily_task_status: "completed" } : {}),
    }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["session", sessionId] }),
        queryClient.invalidateQueries({ queryKey: ["today"] }),
        queryClient.invalidateQueries({ queryKey: ["progress"] }),
      ]);
      showToast("本课节已完成", "success");
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const assess = useMutation({
    mutationFn: async () => {
      if (session && session.status !== "completed") {
        await sessionsApi.update(session.id, {
          status: "completed",
          knowledge_point_status: "completed",
          ...(session.daily_task_id ? { daily_task_status: "completed" } : {}),
        });
      }
      return prepareLessonAssessment(lesson!, session?.id ?? null);
    },
    onSuccess: async (attempt) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["session", sessionId] }),
        queryClient.invalidateQueries({ queryKey: ["today"] }),
        queryClient.invalidateQueries({ queryKey: ["progress"] }),
        queryClient.invalidateQueries({ queryKey: ["learning-activities"] }),
      ]);
      navigate(quizAttemptHref(attempt.id, {
        kind: "lesson",
        lessonId,
        goalId: lesson!.learning_goal_id,
        ...(session?.id ? { sessionId: session.id } : {}),
      }));
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });

  if (lessonQuery.isLoading || (hasSession && sessionQuery.isLoading)) {
    return <LoadingState label="正在打开课节" />;
  }
  if (lessonQuery.isError) {
    return <ErrorState message={lessonQuery.error.message} onRetry={() => lessonQuery.refetch()} />;
  }
  if (sessionQuery.isError) {
    return <ErrorState message={sessionQuery.error.message} onRetry={() => sessionQuery.refetch()} />;
  }
  if (!lesson || !version || lesson.status === "archived") {
    return <ErrorState message="该课节还没有可学习的已发布版本。" onRetry={() => lessonQuery.refetch()} />;
  }

  const tutorDisabled = !session || sessionMismatch || Boolean(session.invalidated_at)
    || session.status === "completed" || session.status === "cancelled";
  const lessonLocation = `${lesson.course_title} / ${lesson.title} / ${primaryPoint?.title ?? "课节"}`;

  return (
    <div className="lesson-page">
      <aside className="lesson-outline">
        <Link className="back-link" to={`/items/${lesson.learning_goal_id}`}><ArrowLeft size={16} />返回事项</Link>
        <div className="lesson-outline__identity">
          <span>当前内容</span>
          <h2>{lesson.course_title}</h2>
          <p>{primaryPoint?.title}</p>
        </div>
        <section aria-labelledby="lesson-objectives-title">
          <div className="lesson-section-label"><Target size={16} /><h3 id="lesson-objectives-title">学习目标</h3></div>
          <ol className="lesson-objectives">
            {version.objectives.map((objective) => <li key={objective}>{objective}</li>)}
          </ol>
        </section>
        <div className="lesson-outline__time"><Clock3 size={16} /><span>预计 {version.estimated_minutes} 分钟</span></div>
      </aside>

      <main className="lesson-content">
        {sessionMismatch && (
          <div className="notice notice--warning" role="alert">
            当前会话绑定的不是这个已发布课节版本，请从今日学习重新进入。
          </div>
        )}
        <header className="lesson-hero">
          <span>本次学习</span>
          <h1>{lesson.title}</h1>
          <p>{lesson.description}</p>
          <div className="lesson-hero__actions">
            {!session && (
              <button
                className="button button--primary"
                disabled={start.isPending || !primaryPoint}
                onClick={() => start.mutate()}
              >
                <Play size={16} />{start.isPending ? "正在开始" : "开始本课"}
              </button>
            )}
            {session && session.status !== "completed" && !sessionMismatch && (
              <button
                className="button button--primary"
                disabled={complete.isPending || Boolean(session.invalidated_at)}
                onClick={() => complete.mutate()}
              >
                <CheckCircle2 size={16} />{complete.isPending ? "正在完成" : "完成课节"}
              </button>
            )}
            {session?.status === "completed" && (
              <span className="lesson-complete"><CheckCircle2 size={17} />本课节已完成</span>
            )}
          </div>
        </header>

        <article className="lesson-reading" aria-label="课节讲解">
          <SafeMarkdown content={version.content_markdown} />
        </article>

        <section className="lesson-section" aria-labelledby="lesson-examples-title">
          <div className="lesson-section-heading">
            <div><Lightbulb size={18} /><h2 id="lesson-examples-title">示例</h2></div>
            <span>{version.examples.length} 个</span>
          </div>
          <div className="lesson-example-list">
            {version.examples.map((example, index) => (
              <article key={`${example.title}-${index}`}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <div><h3>{example.title}</h3><SafeMarkdown content={example.explanation_markdown} /></div>
              </article>
            ))}
          </div>
        </section>

        <section className="lesson-section" aria-labelledby="lesson-practice-title">
          <div className="lesson-section-heading">
            <div><BookOpenCheck size={18} /><h2 id="lesson-practice-title">引导练习</h2></div>
          </div>
          <div className="lesson-practice-list">
            {version.guided_practice.map((practice, index) => (
              <article key={`${practice.prompt}-${index}`}>
                <strong>练习 {index + 1}</strong>
                <p>{practice.prompt}</p>
                <details><summary>查看提示 <ChevronDown size={14} /></summary><p>{practice.hint}</p></details>
              </article>
            ))}
          </div>
        </section>

        <section className="lesson-section lesson-checks" aria-labelledby="lesson-check-title">
          <div className="lesson-section-heading">
            <div><CheckCircle2 size={18} /><h2 id="lesson-check-title">理解检查</h2></div>
            <button className="button button--secondary" onClick={() => setChecksOpen((open) => !open)}>
              {checksOpen ? "收起检查" : "开始检查"}
            </button>
          </div>
          <p>先用这些问题快速回想；准备好后，再做一次正式练习并获得反馈。</p>
          {checksOpen && (
            <ol>
              {version.checks.map((check) => (
                <li key={check.prompt}>
                  <strong>{check.prompt}</strong>
                  {check.options.length > 0 && (
                    <ul>{check.options.map((option) => <li key={option}>{option}</li>)}</ul>
                  )}
                </li>
              ))}
            </ol>
          )}
          <div className="lesson-assessment-action">
            <div><strong>准备好检查理解了吗？</strong><p>系统会复用已发布练习，或按当前内容准备一份简短练习。</p></div>
            <button
              className="button button--primary"
              disabled={!session || sessionMismatch || Boolean(session?.invalidated_at) || assess.isPending}
              onClick={() => assess.mutate()}
            >
              <BookOpenCheck size={16}/>{assess.isPending ? "正在准备练习" : "检查一下理解"}
            </button>
          </div>
          {!session && <p className="muted">先开始本次学习，完成后即可进入练习。</p>}
        </section>

        <section className="lesson-section lesson-sources" aria-labelledby="lesson-sources-title">
          <div className="lesson-section-heading">
            <div><Quote size={18} /><h2 id="lesson-sources-title">本课引用</h2></div>
            <span>{version.sources.length} 条</span>
          </div>
          {version.sources.map((source) => (
            <details key={`${source.material_id}-${source.source_locator}`}>
              <summary><strong>{source.material_title}</strong><span>{source.source_locator}</span></summary>
              <p>{source.quoted_text}</p>
            </details>
          ))}
        </section>
      </main>

      <aside className="lesson-tutor">
        <ContextTutor
          title="边学边问"
          inputLabel="向本课学习导师提问"
          conversationTitle={`内容讨论 · ${lesson.title}`}
          locationLabel={lessonLocation}
          disabled={tutorDisabled}
          surfaceContext={{
            goal_id: lesson.learning_goal_id,
            course_id: lesson.course_id,
            knowledge_point_id: primaryPoint?.knowledge_point_id,
            learning_session_id: session?.id,
            lesson_id: lesson.id,
            lesson_version_id: version.id,
          }}
        />
        {!session && <p className="lesson-tutor__hint">开始本次学习后，讨论会自动带入当前内容和进度。</p>}
        <Link className="text-link lesson-ai-link" to={`/ai?lesson_id=${lesson.id}${session ? `&session_id=${session.id}` : ""}`}><MessageSquareText size={15}/>转到 AI 协作继续协作</Link>
      </aside>
    </div>
  );
}
