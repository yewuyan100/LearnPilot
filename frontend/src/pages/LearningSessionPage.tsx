import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle2, Clock3, Pause, Play, Save, Square } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { coursesApi, sessionsApi } from "../api/resources";
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
  const finish = () => update.mutate(
    { notes, status: "completed", knowledge_point_status: pointStatus, daily_task_status: "completed" },
    { onSuccess: () => { showToast("本次学习已完成", "success"); navigate("/today"); } },
  );

  if (session.isLoading) return <LoadingState label="正在恢复学习会话" />;
  if (session.isError) return <ErrorState message={session.error.message} onRetry={() => session.refetch()} />;
  const data = session.data!;
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
        <header>
          <span>当前知识点</span>
          <h1>{data.knowledge_point_title ?? data.task_title ?? "自由学习记录"}</h1>
          <p>{currentPoint?.description || "本次会话没有关联知识点描述，你仍可以记录手动学习笔记。"}</p>
        </header>
        <section className="note-editor">
          <label className="field">
            <span>学习笔记</span>
            <textarea
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              placeholder="记录定义、例子、疑问或下一步行动"
            />
          </label>
          <label className="field field--compact">
            <span>知识点状态</span>
            <select value={pointStatus} disabled={!data.knowledge_point_id} onChange={(event) => setPointStatus(event.target.value)}>
              <option value="not_started">未开始</option>
              <option value="learning">学习中</option>
              <option value="completed">已完成</option>
              <option value="locked">已锁定</option>
            </select>
          </label>
          <div className="button-row">
            <button className="button button--secondary" disabled={update.isPending} onClick={save}><Save size={16} />保存笔记</button>
            <button className="button button--primary" disabled={update.isPending || data.status === "completed"} onClick={finish}><CheckCircle2 size={16} />完成本次学习</button>
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
          {data.status === "active" && <button className="button button--secondary" onClick={() => update.mutate({ notes, status: "paused" })}><Pause size={16} />暂停</button>}
          {data.status === "paused" && <button className="button button--secondary" onClick={() => update.mutate({ notes, status: "active" })}><Play size={16} />继续</button>}
          {data.status !== "completed" && <button className="button button--quiet" onClick={() => update.mutate({ notes, status: "cancelled", ended_at: new Date().toISOString() }, { onSuccess: () => navigate("/today") })}><Square size={15} />结束但不完成</button>}
        </div>
        <p className="session-honesty">V1 学习工作台只记录手动笔记与状态，不提供 AI 对话或流式输出。</p>
      </aside>
    </div>
  );
}
