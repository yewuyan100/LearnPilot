import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle2, Clock3, NotebookPen, Pause, Play, Save, Square } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { coursesApi, notesApi, sessionsApi } from "../api/resources";
import { ContextTutor } from "../components/ContextTutor";
import { ErrorState, LoadingState } from "../components/States";
import { useToast } from "../components/toast-context";
import { formatDateTime, statusLabel } from "../utils/format";

export function LearningSessionPage() {
  const { id } = useParams();
  const sessionId = Number(id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const session = useQuery({ queryKey: ["session", sessionId], queryFn: () => sessionsApi.get(sessionId), enabled: Number.isFinite(sessionId) });
  const points = useQuery({
    queryKey: ["knowledge-points", session.data?.course_id],
    queryFn: () => coursesApi.points(session.data!.course_id!),
    enabled: Boolean(session.data?.course_id),
  });
  const [notes, setNotes] = useState("");
  const [pointStatus, setPointStatus] = useState("learning");
  useEffect(() => {
    if (session.data) {
      setNotes(session.data.notes);
      const point = points.data?.find((item) => item.id === session.data.knowledge_point_id);
      if (point) setPointStatus(point.status);
    }
  }, [session.data, points.data]);

  const update = useMutation({
    mutationFn: (payload: unknown) => sessionsApi.update(sessionId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
      await queryClient.invalidateQueries({ queryKey: ["today"] });
      await queryClient.invalidateQueries({ queryKey: ["progress"] });
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const save = () => update.mutate({ notes, knowledge_point_status: pointStatus });
  const finish = async () => {
    await update.mutateAsync({ notes, status: "completed", knowledge_point_status: pointStatus, daily_task_status: "completed" });
    if (notes.trim()) {
      await notesApi.create({
        title: data.knowledge_point_title ? `学习记录 · ${data.knowledge_point_title}` : `学习会话 #${data.id}`,
        content_markdown: notes,
        note_type: "study",
        links: [
          { entity_type: "learning_session", entity_id: data.id },
          ...(data.course_id ? [{ entity_type: "course", entity_id: data.course_id }] : []),
          ...(data.knowledge_point_id ? [{ entity_type: "knowledge_point", entity_id: data.knowledge_point_id }] : []),
        ],
      });
      await queryClient.invalidateQueries({ queryKey: ["notes"] });
    }
    showToast(notes.trim() ? "本次学习已完成，笔记已进入笔记本" : "本次学习已完成", "success");
    navigate("/today");
  };

  if (session.isLoading) return <LoadingState label="正在恢复学习会话" />;
  if (session.isError) return <ErrorState message={session.error.message} onRetry={() => session.refetch()} />;
  const data = session.data!;
  const invalidated = Boolean(data.invalidated_at);
  const currentPoint = points.data?.find((point) => point.id === data.knowledge_point_id);

  return (
    <div className="session-page">
      <aside className="session-outline">
        <Link className="back-link" to="/today"><ArrowLeft size={16} />返回今日学习</Link>
        <div><span>当前课程</span><h2>{data.course_title ?? "未关联课程"}</h2><p>{data.goal_title}</p></div>
        <nav aria-label="课程知识点">
          {points.data?.map((point) => (
            <div className={`outline-point ${point.id === data.knowledge_point_id ? "outline-point--active" : ""}`} key={point.id}>
              <span>{String(point.order_index).padStart(2, "0")}</span><p>{point.title}<small>{statusLabel[point.status]}</small></p>
            </div>
          ))}
        </nav>
        <span className={`status status--${data.status}`}>会话{statusLabel[data.status]}</span>
      </aside>
      <main className="session-workspace">
        {invalidated && <div className="notice notice--warning"><strong>该学习会话已失效，不能继续学习</strong><p>{data.invalidation_reason}</p><Link to="/today">返回今日学习并重新规划</Link></div>}
        <header>
          <span>当前知识点</span>
          <h1>{data.knowledge_point_title ?? data.task_title ?? "自由学习记录"}</h1>
          <p>{currentPoint?.description || "本次会话没有关联知识点描述，你仍可以记录手动学习笔记。"}</p>
        </header>
        <ContextTutor
          title="就当前知识点提问"
          inputLabel="向当前知识点的学习导师提问"
          conversationTitle="学习会话辅导"
          locationLabel={data.course_title && data.knowledge_point_title ? `${data.course_title} / ${data.knowledge_point_title}` : "当前学习位置"}
          disabled={invalidated}
          surfaceContext={{
            goal_id: data.learning_goal_id,
            course_id: data.course_id,
            knowledge_point_id: data.knowledge_point_id,
            learning_session_id: data.id,
            lesson_id: data.lesson_id,
            lesson_version_id: data.lesson_version_id,
          }}
        />
        <section className="note-editor">
          <label className="field">
            <span>学习笔记</span>
            <textarea
              value={notes}
              disabled={invalidated}
              onChange={(event) => setNotes(event.target.value)}
              placeholder="记录定义、例子、疑问或下一步行动"
            />
          </label>
          <label className="field field--compact">
            <span>知识点状态</span>
            <select value={pointStatus} disabled={!data.knowledge_point_id || invalidated} onChange={(event) => setPointStatus(event.target.value)}>
              <option value="not_started">未开始</option>
              <option value="learning">学习中</option>
              <option value="completed">已完成</option>
              <option value="locked">已锁定</option>
            </select>
          </label>
          <div className="button-row">
            <button className="button button--secondary" disabled={update.isPending || invalidated} onClick={save}><Save size={16} />保存笔记</button>
            <button className="button button--primary" disabled={update.isPending || data.status === "completed" || invalidated} onClick={() => void finish()}><CheckCircle2 size={16} />完成并保存记录</button>
          </div>
        </section>
      </main>
      <aside className="session-panel">
        <h2>本次任务</h2>
        <dl>
          <div><dt>任务</dt><dd>{data.task_title ?? "自由学习"}</dd></div>
          <div><dt>开始时间</dt><dd>{formatDateTime(data.started_at)}</dd></div>
          <div><dt>会话状态</dt><dd>{statusLabel[data.status]}</dd></div>
          {currentPoint && <div><dt>预计时间</dt><dd><Clock3 size={14} /> {currentPoint.estimated_minutes} 分钟</dd></div>}
        </dl>
        <div className="session-controls">
          {!invalidated && data.status === "active" && <button className="button button--secondary" onClick={() => update.mutate({ notes, status: "paused" })}><Pause size={16} />暂停</button>}
          {!invalidated && data.status === "paused" && <button className="button button--secondary" onClick={() => update.mutate({ notes, status: "active" })}><Play size={16} />继续</button>}
          {!invalidated && data.status !== "completed" && <button className="button button--quiet" onClick={() => update.mutate({ notes, status: "cancelled", ended_at: new Date().toISOString() }, { onSuccess: () => navigate("/today") })}><Square size={15} />结束但不完成</button>}
          {invalidated && <Link className="button button--secondary" to="/goals">调整学习计划</Link>}
        </div>
        <p className="session-honesty"><NotebookPen size={15}/>完成会话时，已填写内容会保存到统一笔记本并关联本次学习。</p>
      </aside>
    </div>
  );
}
