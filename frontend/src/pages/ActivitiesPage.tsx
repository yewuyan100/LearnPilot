import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BookOpenCheck,
  ChevronRight,
  ClipboardCheck,
  Plus,
  Sparkles,
} from "lucide-react";
import { useMemo, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { activitiesApi, coursesApi, materialsApi } from "../api/resources";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { useToast } from "../components/toast-context";
import { formatDateTime } from "../utils/format";

const questionTypes = [
  ["single_choice", "单选题"],
  ["multiple_choice", "多选题"],
  ["true_false", "判断题"],
  ["short_answer", "简答题"],
] as const;

const statusLabel: Record<string, string> = {
  draft: "草稿",
  published: "已发布",
  archived: "已归档",
  generation_failed: "生成失败",
};

export function ActivitiesPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState("");
  const [courseId, setCourseId] = useState("");
  const [pointId, setPointId] = useState("");
  const [materialIds, setMaterialIds] = useState<number[]>([]);
  const [types, setTypes] = useState<string[]>(["single_choice", "true_false"]);
  const [questionCount, setQuestionCount] = useState(6);
  const [difficulty, setDifficulty] = useState("mixed");

  const activities = useQuery({
    queryKey: ["learning-activities"],
    queryFn: () => activitiesApi.list(),
  });
  const courses = useQuery({ queryKey: ["courses"], queryFn: coursesApi.list });
  const materials = useQuery({
    queryKey: ["materials", "", ""],
    queryFn: () => materialsApi.list(),
  });
  const points = useQuery({
    queryKey: ["course-points", courseId],
    queryFn: () => coursesApi.points(Number(courseId)),
    enabled: Boolean(courseId),
  });
  const usableMaterials = useMemo(
    () =>
      (materials.data ?? []).filter(
        (item) =>
          item.ingestion_status === "completed" &&
          item.indexing_status === "completed",
      ),
    [materials.data],
  );

  const generate = useMutation({
    mutationFn: () =>
      activitiesApi.generate({
        title: title.trim(),
        course_id: courseId ? Number(courseId) : null,
        knowledge_point_id: pointId ? Number(pointId) : null,
        material_ids: materialIds,
        question_types: types,
        question_count: questionCount,
        difficulty,
        request_id: crypto.randomUUID(),
      }),
    onSuccess: async (activity) => {
      await queryClient.invalidateQueries({ queryKey: ["learning-activities"] });
      showToast("活动草稿已生成，请检查题目和来源", "success");
      navigate(`/activities/${activity.id}`);
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!title.trim() || !materialIds.length || !types.length) return;
    generate.mutate();
  };

  if (activities.isLoading || courses.isLoading || materials.isLoading) {
    return <LoadingState label="正在加载学习活动" />;
  }
  if (activities.isError || courses.isError || materials.isError) {
    const error = (activities.error ?? courses.error ?? materials.error) as Error;
    return <ErrorState message={error.message} onRetry={() => activities.refetch()} />;
  }

  return (
    <div className="page activity-page">
      <header className="page-header page-header--split">
        <div>
          <span className="eyebrow">V4 · 基于真实资料</span>
          <h1>学习活动</h1>
          <p>从已索引资料生成可预览、可批改、可复习的练习。</p>
        </div>
        <button
          className="button button--primary"
          onClick={() => setShowForm((value) => !value)}
        >
          <Plus size={17} />生成活动
        </button>
      </header>

      {showForm && (
        <form className="activity-generator" onSubmit={submit}>
          <header>
            <div>
              <span className="eyebrow">生成配置</span>
              <h2>创建有来源的题目草稿</h2>
            </div>
            <Sparkles size={22} />
          </header>
          <div className="form-grid">
            <label className="field field--wide">
              <span>活动标题</span>
              <input
                aria-label="活动标题"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="例如：MCP 核心原语测验"
                maxLength={255}
                required
              />
            </label>
            <label className="field">
              <span>课程</span>
              <select
                aria-label="活动课程"
                value={courseId}
                onChange={(event) => {
                  setCourseId(event.target.value);
                  setPointId("");
                }}
              >
                <option value="">不限定课程</option>
                {courses.data?.map((course) => (
                  <option key={course.id} value={course.id}>{course.title}</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>知识点</span>
              <select
                aria-label="活动知识点"
                value={pointId}
                disabled={!courseId}
                onChange={(event) => setPointId(event.target.value)}
              >
                <option value="">不限定知识点</option>
                {points.data?.map((point) => (
                  <option key={point.id} value={point.id}>{point.title}</option>
                ))}
              </select>
            </label>
            <fieldset className="field field--wide activity-scope">
              <legend>资料范围（仅显示已处理并索引的资料）</legend>
              {usableMaterials.length ? usableMaterials.map((material) => (
                <label key={material.id} className="check-row">
                  <input
                    type="checkbox"
                    checked={materialIds.includes(material.id)}
                    onChange={(event) =>
                      setMaterialIds((current) =>
                        event.target.checked
                          ? [...current, material.id]
                          : current.filter((id) => id !== material.id),
                      )
                    }
                  />
                  <span>{material.original_filename}</span>
                  <small>{material.chunk_count} 个资料片段</small>
                </label>
              )) : (
                <p className="muted">暂无可用资料，请先在资料页完成处理和索引。</p>
              )}
            </fieldset>
            <fieldset className="field field--wide activity-type-grid">
              <legend>题型</legend>
              {questionTypes.map(([value, label]) => (
                <label key={value} className="check-row">
                  <input
                    type="checkbox"
                    checked={types.includes(value)}
                    onChange={(event) =>
                      setTypes((current) =>
                        event.target.checked
                          ? [...current, value]
                          : current.filter((item) => item !== value),
                      )
                    }
                  />
                  <span>{label}</span>
                </label>
              ))}
            </fieldset>
            <label className="field">
              <span>题目数量</span>
              <input
                aria-label="题目数量"
                type="number"
                min={1}
                max={20}
                value={questionCount}
                onChange={(event) => setQuestionCount(Number(event.target.value))}
              />
            </label>
            <label className="field">
              <span>难度</span>
              <select
                aria-label="活动难度"
                value={difficulty}
                onChange={(event) => setDifficulty(event.target.value)}
              >
                <option value="mixed">混合</option>
                <option value="easy">简单</option>
                <option value="medium">中等</option>
                <option value="hard">困难</option>
              </select>
            </label>
          </div>
          <div className="activity-generator__actions">
            <p>生成只会保存为草稿；发布前可删除题目和调整顺序。</p>
            <button
              className="button button--primary"
              disabled={
                generate.isPending ||
                !title.trim() ||
                !materialIds.length ||
                !types.length
              }
              type="submit"
            >
              <Sparkles size={16} />
              {generate.isPending ? "正在检索资料并生成…" : "生成题目草稿"}
            </button>
          </div>
        </form>
      )}

      <section className="activity-list-section">
        <div className="section-heading">
          <div>
            <span className="eyebrow">活动记录</span>
            <h2>{activities.data?.total ?? 0} 个活动</h2>
          </div>
        </div>
        {!activities.data?.items.length ? (
          <EmptyState
            title="还没有学习活动"
            description="选择已索引资料，生成第一组有来源的练习题。"
          />
        ) : (
          <div className="activity-list">
            {activities.data.items.map((activity) => (
              <article key={activity.id} className="activity-row">
                <span className={`status status--${activity.status}`}>
                  {statusLabel[activity.status] ?? activity.status}
                </span>
                <div className="activity-row__main">
                  <h3>{activity.title}</h3>
                  <p>
                    {activity.course_title ?? "未关联课程"}
                    {activity.knowledge_point_title
                      ? ` · ${activity.knowledge_point_title}`
                      : ""}
                  </p>
                  <small>{formatDateTime(activity.created_at)}</small>
                </div>
                <dl>
                  <div><dt>题目</dt><dd>{activity.question_count}</dd></div>
                  <div><dt>总分</dt><dd>{activity.total_points}</dd></div>
                  <div><dt>完成</dt><dd>{activity.completed_attempt_count}</dd></div>
                </dl>
                <button
                  className="button button--secondary"
                  onClick={() => navigate(`/activities/${activity.id}`)}
                >
                  {activity.status === "published" ? (
                    <><BookOpenCheck size={16} />查看并开始</>
                  ) : (
                    <><ClipboardCheck size={16} />检查草稿</>
                  )}
                  <ChevronRight size={16} />
                </button>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
