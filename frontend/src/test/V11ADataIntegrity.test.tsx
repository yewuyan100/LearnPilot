import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { createTestQueryClient, renderApp } from "./render";

const now = "2026-08-07T08:00:00Z";
const goal = { id: 1, title: "完成可靠学习课程", description: "", target_date: "2026-08-30", daily_minutes: 40, current_level: "入门", status: "active", is_demo: false, created_at: now, updated_at: now };
const course = { id: 2, learning_goal_id: 1, learning_goal_title: goal.title, title: "数据完整性课程", description: "正式课程", status: "active", knowledge_point_count: 1, created_at: now, updated_at: now };
const point = { id: 3, course_id: 2, title: "事实完整性", description: "保留历史事实", order_index: 1, estimated_minutes: 20, status: "learning", lifecycle_status: "active", superseded_by_id: null, lifecycle_reason: null, archived_at: null, version: 1, created_at: now, updated_at: now };
const task = { id: 8, learning_goal_id: 1, course_id: 2, knowledge_point_id: 3, activity_id: null, title: "学习：事实完整性", task_type: "learn", estimated_minutes: 20, scheduled_date: "2026-08-07", status: "in_progress", blocked_at: null, blocked_reason: null, blocked_source_type: null, blocked_source_id: null, created_at: now, updated_at: now };
const impact = {
  knowledge_point_id: 3, knowledge_point_title: point.title, course_id: 2, point_version: 1,
  lifecycle_status: "active", action: "archive", superseded_by_id: null,
  prerequisite_edge_ids: [41], study_plan_ids: [9], study_plan_version_ids: [10], study_plan_item_ids: [11],
  daily_task_ids: [8], actionable_daily_task_ids: [8], learning_session_ids: [12], active_learning_session_ids: [12],
  activity_ids: [13, 14], mastery_ids: [15], review_schedule_ids: [16], impact_hash: "a".repeat(64), requires_confirmation: true,
} as const;

function json(data: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } }));
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("V11A 知识点生命周期与执行阻断", () => {
  it("课程页先展示真实影响，再携带确认快照执行归档", async () => {
    let activePoints = [point];
    const applyBodies: Array<Record<string, unknown>> = [];
    vi.stubGlobal("fetch", vi.fn((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/learning-goals")) return json([goal]);
      if (url.endsWith("/courses")) return json([course]);
      if (url.includes("/learning-activities?")) return json({ items: [], total: 0, page: 1, page_size: 100, pages: 0 });
      if (url.endsWith("/today")) return json({ date: "2026-08-07", current_goal: goal, tasks: [task], pending_count: 1, blocked_count: 0, recent_course: course, recent_session: null });
      if (url.includes("/mastery")) return json({ items: [], total: 0 });
      if (url.endsWith("/courses/2/knowledge-points")) return json(activePoints);
      if (url.endsWith("/courses/2/materials")) return json([]);
      if (url.endsWith("/knowledge-points/3/impact") && init?.method === "POST") return json(impact);
      if (url.endsWith("/knowledge-points/3/archive") && init?.method === "POST") {
        applyBodies.push(JSON.parse(String(init.body)));
        activePoints = [];
        return json({ point: { ...point, lifecycle_status: "archived", lifecycle_reason: "课程内容已调整，不再安排该知识点", archived_at: now, version: 2 }, impact, idempotent_replay: false });
      }
      return json([]);
    }));

    const client = createTestQueryClient();
    client.setQueryData(["courses"], [course]);
    client.setQueryData(["goals"], [goal]);
    client.setQueryData(["learning-activities"], { items: [], total: 0, page: 1, page_size: 100, pages: 0 });
    client.setQueryData(["today"], { date: "2026-08-07", current_goal: goal, tasks: [task], pending_count: 1, blocked_count: 0, recent_course: course, recent_session: null });
    client.setQueryData(["mastery"], { items: [], total: 0 });
    client.setQueryData(["knowledge-points", course.id], activePoints);
    client.setQueryData(["effective-materials", "course", course.id], []);

    renderApp(<App />, "/courses", client);
    await userEvent.click(await screen.findByRole("button", { name: "归档 事实完整性" }));
    expect(await screen.findByText("学习计划 1 个版本 · 今日任务 1 项 · 活跃会话 1 个")).toBeInTheDocument();
    expect(screen.getByText(/历史活动 2 项 · 掌握记录 1 项 · 复习安排 1 项/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "确认归档并停止受影响执行" }));
    await waitFor(() => expect(applyBodies).toHaveLength(1));
    expect(applyBodies[0]).toMatchObject({
      action: "archive",
      expected_version: 1,
      impact_hash: impact.impact_hash,
      confirmed: true,
    });
    expect(String(applyBodies[0].request_id).length).toBeGreaterThanOrEqual(8);
    expect(await screen.findByText("知识点已归档，受影响的计划、任务和会话已停止执行")).toBeInTheDocument();
  });

  it("Today 对 blocked 任务给出固定解释和重新规划入口，不允许继续", async () => {
    const blockedTask = { ...task, blocked_at: now, blocked_reason: "该任务对应课程内容已变化，需要重新规划", blocked_source_type: "knowledge_point", blocked_source_id: 3 };
    const action = { action_type: "replan_required", target_kind: "study_plan", target_id: 9, learning_goal_id: 1, course_id: 2, course_title: course.title, knowledge_point_id: null, knowledge_point_title: null, title: "调整学习计划", reason_code: "study_plan_stale", reason: "知识点已归档，需要重新生成学习计划", priority: 85, estimated_minutes: 0, from_formal_plan: false, is_due_review: false, plan_id: 9, plan_item_id: null, cta_label: "调整计划", cta_href: "/goals", action_signature: "b".repeat(64), available_minutes: 40 };
    vi.stubGlobal("fetch", vi.fn((input: string | URL) => {
      const url = String(input);
      if (url.endsWith("/today")) return json({ date: "2026-08-07", current_goal: goal, tasks: [blockedTask], pending_count: 0, blocked_count: 1, recent_course: course, recent_session: null });
      if (url.includes("/next-learning-action")) return json(action);
      return json([]);
    }));

    renderApp(<App />, "/today");
    expect(await screen.findByText("该任务对应课程内容已变化，需要重新规划")).toBeInTheDocument();
    expect(screen.getByText(/1 项需要重新规划/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "继续学习" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "今天跳过" })).not.toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "调整学习计划" }).length).toBeGreaterThan(0);
  });

  it("失效会话展示原因并关闭所有继续学习控制", async () => {
    const invalidSession = { id: 12, learning_goal_id: 1, course_id: 2, knowledge_point_id: 3, daily_task_id: 8, started_at: now, ended_at: null, status: "active", notes: "历史笔记", invalidated_at: now, invalidation_reason: "该学习会话关联的知识点已失效，不能继续学习", goal_title: goal.title, course_title: course.title, knowledge_point_title: point.title, task_title: task.title, created_at: now, updated_at: now };
    vi.stubGlobal("fetch", vi.fn((input: string | URL) => {
      const url = String(input);
      if (url.endsWith("/learning-sessions/12")) return json(invalidSession);
      if (url.endsWith("/courses/2/knowledge-points")) return json([]);
      return json([]);
    }));

    renderApp(<App />, "/learning-sessions/12");
    expect(await screen.findByText("该学习会话已失效，不能继续学习")).toBeInTheDocument();
    expect(screen.getByText(invalidSession.invalidation_reason)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存笔记" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "完成并保存记录" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "暂停" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "继续" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "调整学习计划" })).toBeInTheDocument();
  });
});
