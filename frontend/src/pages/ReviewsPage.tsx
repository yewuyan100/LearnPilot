import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarPlus, Clock3, Info, RotateCcw } from "lucide-react";
import { coursesApi, dashboardApi, tasksApi } from "../api/resources";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { useToast } from "../components/toast-context";
import { formatDate, statusLabel } from "../utils/format";

const localDate = () => {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
};

export function ReviewsPage() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const reviews = useQuery({ queryKey: ["reviews"], queryFn: dashboardApi.reviews });
  const courses = useQuery({ queryKey: ["courses"], queryFn: coursesApi.list });
  const addTask = useMutation({
    mutationFn: ({ pointId, courseId, title, estimatedMinutes }: { pointId: number; courseId: number; title: string; estimatedMinutes: number }) => {
      const course = courses.data?.find((item) => item.id === courseId);
      if (!course) throw new Error("找不到知识点所属课程");
      return tasksApi.create({
        learning_goal_id: course.learning_goal_id,
        course_id: courseId,
        knowledge_point_id: pointId,
        title: `复习 ${title}`,
        task_type: "review",
        estimated_minutes: estimatedMinutes,
        scheduled_date: localDate(),
        status: "pending",
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["today"] });
      showToast("已加入今天的任务", "success");
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });

  if (reviews.isLoading || courses.isLoading) return <LoadingState label="正在整理可复习内容" />;
  if (reviews.isError) return <ErrorState message={reviews.error.message} onRetry={() => reviews.refetch()} />;
  const data = reviews.data!;

  return (
    <div className="page">
      <header className="page-header">
        <h1>复习</h1>
        <p>从学习中和未完成的内容里，手动选择今天要回顾的知识点。</p>
      </header>
      <div className="notice notice--info"><Info size={18} /><span>V1 不计算掌握度，也不自动安排复习日期。自动复习调度将在后续版本实现。</span></div>
      <section className="section-block">
        <div className="section-heading"><div><h2>学习中的知识点</h2><p>包含“学习中”和“未开始”的课程内容</p></div></div>
        {!data.knowledge_points.length ? (
          <EmptyState title="没有可复习的知识点" description="在课程中创建知识点或将状态改为“学习中”。" />
        ) : (
          <div className="review-list">
            {data.knowledge_points.map((point) => (
              <article className="review-item" key={point.id}>
                <div className="review-item__icon"><RotateCcw size={19} /></div>
                <div><strong>{point.title}</strong><p><span className={`status status--${point.status}`}>{statusLabel[point.status]}</span> · <Clock3 size={14} /> {point.estimated_minutes} 分钟</p></div>
                <button
                  className="button button--secondary"
                  disabled={addTask.isPending}
                  onClick={() => addTask.mutate({ pointId: point.id, courseId: point.course_id, title: point.title, estimatedMinutes: point.estimated_minutes })}
                ><CalendarPlus size={16} />加入今天</button>
              </article>
            ))}
          </div>
        )}
      </section>
      <section className="section-block">
        <div className="section-heading"><div><h2>未完成的历史任务</h2><p>计划日期早于今天，仍未完成的任务</p></div></div>
        {!data.unfinished_tasks.length ? (
          <EmptyState title="没有积压任务" description="过去安排的任务都已处理。" />
        ) : (
          <div className="review-list">
            {data.unfinished_tasks.map((task) => (
              <article className="review-item" key={task.id}>
                <div className="review-item__icon review-item__icon--warning"><Clock3 size={19} /></div>
                <div><strong>{task.title}</strong><p>原计划 {formatDate(task.scheduled_date)} · {task.estimated_minutes} 分钟</p></div>
                <span className={`status status--${task.status}`}>{statusLabel[task.status]}</span>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
