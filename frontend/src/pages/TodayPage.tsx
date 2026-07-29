import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, CalendarDays, Clock3, Flag, Play, Plus, RotateCcw } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { dashboardApi, sessionsApi, tasksApi } from "../api/resources";
import { Dialog } from "../components/Dialog";
import { GoalForm } from "../components/GoalForm";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { useToast } from "../components/toast-context";
import { formatDate, formatDateTime, statusLabel } from "../utils/format";
import type { DailyTask } from "../types";

export function TodayPage() {
  const [goalOpen, setGoalOpen] = useState(false);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const today = useQuery({ queryKey: ["today"], queryFn: dashboardApi.today });
  const startMutation = useMutation({
    mutationFn: (task: DailyTask) =>
      sessionsApi.create({
        learning_goal_id: task.learning_goal_id,
        course_id: task.course_id,
        knowledge_point_id: task.knowledge_point_id,
        daily_task_id: task.id,
      }),
    onSuccess: (session) => {
      queryClient.invalidateQueries({ queryKey: ["today"] });
      navigate(`/learning-sessions/${session.id}`);
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const taskMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) => tasksApi.update(id, { status }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["today"] }),
    onError: (error: Error) => showToast(error.message, "error"),
  });

  if (today.isLoading) return <LoadingState label="正在读取今日安排" />;
  if (today.isError) return <ErrorState message={today.error.message} onRetry={() => today.refetch()} />;
  const data = today.data!;

  return (
    <div className="page">
      <header className="page-header page-header--split">
        <div>
          <p className="page-kicker">今天 · {formatDate(data.date)}</p>
          <h1>今日学习</h1>
          <p>把目标、课程和今天的一次专注学习连接起来。</p>
        </div>
        {data.current_goal && (
          <div className="time-budget">
            <Clock3 size={20} />
            <div><span>每日计划</span><strong>{data.current_goal.daily_minutes} 分钟</strong></div>
          </div>
        )}
      </header>

      {!data.current_goal ? (
        <EmptyState
          title="还没有学习目标"
          description="先创建一个明确目标，课程和今日任务才有归属。"
          action={<button className="button button--primary" onClick={() => setGoalOpen(true)}><Plus size={16} />创建目标</button>}
        />
      ) : (
        <>
          <section className="goal-banner">
            <div className="goal-banner__icon"><Flag size={22} /></div>
            <div>
              <span>当前学习目标</span>
              <h2>{data.current_goal.title}</h2>
              <p>目标日期 {formatDate(data.current_goal.target_date)} · 当前水平 {data.current_goal.current_level || "未填写"}</p>
            </div>
          </section>

          <section className="section-block">
            <div className="section-heading">
              <div>
                <h2>今日任务</h2>
                <p>{data.pending_count > 0 ? `还有 ${data.pending_count} 项待完成` : "今天的任务已经完成"}</p>
              </div>
              <Link className="button button--secondary" to="/reviews"><RotateCcw size={16} />查看复习</Link>
            </div>
            {data.tasks.length === 0 ? (
              <EmptyState
                title="今天还没有任务"
                description="从课程或复习页选择一个知识点，加入今天的安排。"
                action={<Link className="button button--primary" to="/courses">打开课程</Link>}
              />
            ) : (
              <div className="task-grid">
                {data.tasks.map((task) => (
                  <article className="task-card" key={task.id}>
                    <div className="task-card__top">
                      <span className={`status status--${task.status}`}>{statusLabel[task.status]}</span>
                      <span><Clock3 size={14} /> {task.estimated_minutes} 分钟</span>
                    </div>
                    <h3>{task.title}</h3>
                    <p>{task.task_type === "review" ? "手动复习任务" : "新知识学习"}</p>
                    <div className="task-card__actions">
                      {task.status !== "completed" && (
                        <button
                          className="button button--primary"
                          disabled={startMutation.isPending}
                          onClick={() => startMutation.mutate(task)}
                        >
                          <Play size={16} />{task.status === "in_progress" ? "继续学习" : "开始学习"}
                        </button>
                      )}
                      {task.status === "pending" && (
                        <button className="button button--quiet" onClick={() => taskMutation.mutate({ id: task.id, status: "skipped" })}>
                          今天跳过
                        </button>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
        </>
      )}

      <section className="overview-grid">
        <article className="overview-card">
          <BookOpen size={20} />
          <span>最近课程</span>
          <strong>{data.recent_course?.title ?? "暂无课程"}</strong>
          {data.recent_course && <Link to="/courses">查看课程结构</Link>}
        </article>
        <article className="overview-card">
          <CalendarDays size={20} />
          <span>最近学习记录</span>
          <strong>{data.recent_session ? statusLabel[data.recent_session.status] : "暂无记录"}</strong>
          <p>{data.recent_session ? formatDateTime(data.recent_session.started_at) : "完成一次学习后会显示在这里"}</p>
        </article>
      </section>

      <Dialog open={goalOpen} title="创建学习目标" onClose={() => setGoalOpen(false)}>
        <GoalForm onDone={() => setGoalOpen(false)} />
      </Dialog>
    </div>
  );
}
