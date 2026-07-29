import { useQuery } from "@tanstack/react-query";
import { BarChart3, BookCheck, BookOpen, CalendarCheck, Flag } from "lucide-react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { dashboardApi } from "../api/resources";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { formatDateTime, statusLabel } from "../utils/format";

export function ProgressPage() {
  const progress = useQuery({ queryKey: ["progress"], queryFn: dashboardApi.progress });
  if (progress.isLoading) return <LoadingState label="正在计算真实学习进度" />;
  if (progress.isError) return <ErrorState message={progress.error.message} onRetry={() => progress.refetch()} />;
  const data = progress.data!;
  const completion = data.knowledge_point_count
    ? Math.round((data.completed_knowledge_point_count / data.knowledge_point_count) * 100)
    : 0;

  return (
    <div className="page">
      <header className="page-header"><h1>进度</h1><p>所有数字来自本地数据库，不使用预置趋势或掌握度分数。</p></header>
      <section className="metric-grid">
        <Metric icon={<Flag size={19} />} label="学习目标" value={data.goal_count} suffix="个" />
        <Metric icon={<BookOpen size={19} />} label="活跃课程" value={data.active_course_count} suffix="门" />
        <Metric icon={<BookCheck size={19} />} label="已完成知识点" value={data.completed_knowledge_point_count} suffix={` / ${data.knowledge_point_count}`} />
        <Metric icon={<CalendarCheck size={19} />} label="今日任务" value={data.today_task_completed} suffix={` / ${data.today_task_total}`} />
      </section>
      {data.knowledge_point_count > 0 && (
        <section className="progress-card">
          <div><span>知识点完成比例</span><strong>{completion}%</strong></div>
          <div className="progress-track"><span style={{ "--progress": `${completion}%` } as React.CSSProperties} /></div>
        </section>
      )}
      <div className="progress-layout">
        <section className="chart-card">
          <div className="section-heading"><div><h2>最近七天学习会话</h2><p>共 {data.sessions_last_7_days} 次</p></div><BarChart3 size={20} /></div>
          {data.sessions_last_7_days === 0 ? (
            <EmptyState title="最近七天没有学习记录" description="开始并完成一次学习，会话数量会出现在这里。" />
          ) : (
            <div className="chart-wrap" aria-label="最近七天会话数量柱状图">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.daily_sessions}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="date" tickFormatter={(value) => value.slice(5)} />
                  <YAxis allowDecimals={false} width={28} />
                  <Tooltip labelFormatter={(value) => `日期 ${value}`} />
                  <Bar dataKey="count" name="会话数" fill="var(--color-accent)" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </section>
        <section className="recent-card">
          <div className="section-heading"><div><h2>最近学习记录</h2><p>最多显示六条</p></div></div>
          {!data.recent_sessions.length ? (
            <EmptyState title="暂无记录" description="完成学习后，记录会保存在本地数据库。" />
          ) : (
            <div className="timeline">
              {data.recent_sessions.map((session) => (
                <div className="timeline__item" key={session.id}>
                  <span />
                  <div><strong>{formatDateTime(session.started_at)}</strong><p>{statusLabel[session.status]} · {session.notes ? "已记录笔记" : "无笔记"}</p></div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function Metric({ icon, label, value, suffix }: { icon: React.ReactNode; label: string; value: number; suffix: string }) {
  return <article className="metric-card"><span>{icon}</span><div><small>{label}</small><strong>{value}<em>{suffix}</em></strong></div></article>;
}

