import { cleanup, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { renderApp } from "./render";

const now = "2026-07-29T10:00:00";
const goal = { id: 1, title: "三周入门 MCP", description: "", target_date: "2026-08-19", daily_minutes: 40, current_level: "了解 API", status: "active", is_demo: false, created_at: now, updated_at: now };
const course = { id: 1, learning_goal_id: 1, learning_goal_title: goal.title, title: "MCP 基础", description: "", status: "active", knowledge_point_count: 2, created_at: now, updated_at: now };
const task = { id: 1, learning_goal_id: 1, course_id: 1, knowledge_point_id: 1, activity_id: null, title: "学习 MCP 的定位", task_type: "learning", estimated_minutes: 20, scheduled_date: "2026-07-29", status: "pending", created_at: now, updated_at: now };
const points = [
  { id: 1, course_id: 1, title: "MCP 的定位", description: "", order_index: 1, estimated_minutes: 20, status: "learning", created_at: now, updated_at: now },
  { id: 2, course_id: 1, title: "MCP 的核心角色", description: "", order_index: 2, estimated_minutes: 25, status: "not_started", created_at: now, updated_at: now },
];
const nextLearningAction = {
  action_type: "learn",
  target_kind: "knowledge_point",
  target_id: 1,
  learning_goal_id: 1,
  course_id: 1,
  course_title: course.title,
  knowledge_point_id: 1,
  knowledge_point_title: points[0].title,
  title: "继续学习 MCP 的定位",
  reason_code: "current_path",
  reason: "这是当前学习路径中正在推进的知识点。",
  priority: 100,
  estimated_minutes: 20,
  from_formal_plan: true,
  is_due_review: false,
  plan_id: 1,
  plan_item_id: 1,
  cta_label: "开始学习",
  cta_href: "/today",
  action_signature: "workspace-action",
  available_minutes: null,
};
const response = (data: unknown) => Promise.resolve(new Response(JSON.stringify(data), { status: 200, headers: { "Content-Type": "application/json" } }));

let todayPayload: Record<string, unknown>;
let coursePayload: typeof course[];
let pointPayload: typeof points;
let nextActionPayload: unknown;
let reviewPayload: unknown[];
let progressPayload: Record<string, unknown>;

describe("个人成长工作台", () => {
  beforeEach(() => {
    todayPayload = {
      date: "2026-07-29",
      current_goal: goal,
      tasks: [task],
      pending_count: 1,
      recent_course: course,
      recent_session: null,
    };
    coursePayload = [course];
    pointPayload = points;
    nextActionPayload = nextLearningAction;
    reviewPayload = [];
    progressPayload = { sessions_last_7_days: 0, daily_sessions: [], recent_sessions: [] };

    vi.stubGlobal("fetch", vi.fn((input: string | URL) => {
      const url = String(input);
      if (url.includes("/courses/1/knowledge-points")) return response(pointPayload);
      if (url.includes("/next-learning-action")) return response(nextActionPayload);
      if (url.endsWith("/today")) return response(todayPayload);
      if (url.includes("/reviews")) return response(reviewPayload);
      if (url.endsWith("/progress")) return response(progressPayload);
      if (url.endsWith("/learning-goals")) return response([goal]);
      if (url.endsWith("/courses")) return response(coursePayload);
      if (url.includes("/materials")) return response([]);
      if (url.includes("/rag/conversations")) return response({ items: [], total: 0, page: 1, page_size: 100, pages: 0 });
      if (url.includes("/notes?")) return response({ items: [], total: 0, page: 1, page_size: 5, pages: 0 });
      return response([]);
    }));
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("默认只提供一个继续学习主操作，并保留真实项目上下文", async () => {
    renderApp(<App />, "/");

    expect(await screen.findByRole("heading", { name: "MCP 的定位" })).toBeInTheDocument();
    expect(screen.getByText("MCP 的定位")).toBeInTheDocument();
    expect(screen.getAllByText("这是当前学习路径中正在推进的知识点。").length).toBeGreaterThan(0);
    const continueLinks = screen.getAllByRole("link", { name: "开始学习" });
    expect(continueLinks).toHaveLength(1);
    expect(continueLinks[0]).toHaveAttribute("href", "/today");
    expect(screen.getByRole("heading", { name: "下一步" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "下一步建议" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "掌握概览" })).not.toBeInTheDocument();
    expect(screen.queryByText("快速新增")).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/用户头像/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "全局搜索" })).toBeInTheDocument();
  });

  it("没有已安排内容时仍保留工作台分区并展示诚实空状态", async () => {
    todayPayload = { ...todayPayload, tasks: [], pending_count: 0 };
    nextActionPayload = null;
    renderApp(<App />, "/workspace");

    expect(await screen.findByRole("heading", { name: "MCP 的定位" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "下一步" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "待处理" })).toBeInTheDocument();
    expect(screen.getByText("当前没有需要你处理的内容")).toBeInTheDocument();
    expect(screen.getByText("新的建议或确认项会出现在这里")).toBeInTheDocument();
    expect(screen.getByText("还没有形成学习趋势")).toBeInTheDocument();
    expect(screen.queryByLabelText(/过去 7 天共有/)).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "掌握概览" })).not.toBeInTheDocument();
  });

  it("存在真实学习活动时才展示七日活动图", async () => {
    const chartDay = new Date();
    chartDay.setHours(12, 0, 0, 0);
    const date = `${chartDay.getFullYear()}-${String(chartDay.getMonth() + 1).padStart(2, "0")}-${String(chartDay.getDate()).padStart(2, "0")}`;
    progressPayload = { sessions_last_7_days: 2, daily_sessions: [{ date, count: 2 }], recent_sessions: [] };
    renderApp(<App />, "/workspace");

    expect(await screen.findByLabelText("过去 7 天共有 2 次学习会话")).toBeInTheDocument();
    expect(screen.queryByText("还没有形成学习趋势")).not.toBeInTheDocument();
  });

  it("没有事项时只显示创建第一个事项的引导", async () => {
    todayPayload = {
      date: "2026-07-29",
      current_goal: null,
      tasks: [],
      pending_count: 0,
      recent_course: null,
      recent_session: null,
    };
    coursePayload = [];
    pointPayload = [];
    nextActionPayload = null;
    renderApp(<App />, "/workspace");

    expect(await screen.findByRole("heading", { name: "创建你的第一个事项" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "创建事项" })).toHaveLength(1);
    expect(screen.getByRole("heading", { name: "下一步" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "待处理" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /查看事项/ })).not.toBeInTheDocument();
  });

  it("旧路线数据存在但没有事项时仍从创建事项开始", async () => {
    todayPayload = { ...todayPayload, current_goal: null, tasks: [], pending_count: 0 };
    nextActionPayload = null;
    renderApp(<App />, "/workspace");

    expect(await screen.findByRole("heading", { name: "创建你的第一个事项" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "创建事项" })).toHaveLength(1);
    expect(screen.queryByRole("link", { name: /查看事项/ })).not.toBeInTheDocument();
  });

  it("项目存在但没有下一知识点时提供选择下一步", async () => {
    todayPayload = { ...todayPayload, tasks: [], pending_count: 0 };
    pointPayload = [];
    nextActionPayload = null;
    renderApp(<App />, "/workspace");

    expect(await screen.findByRole("heading", { name: "为「三周入门 MCP」选择下一步" })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "查看事项" })).toHaveLength(1);
  });

  it("只显示真实到期的复习提醒", async () => {
    reviewPayload = [
      {
        id: 1,
        knowledge_point_id: 1,
        knowledge_point_title: "MCP 的定位",
        status: "scheduled",
        priority_score: 80,
        recommended_at: now,
        due_at: "2026-07-29T14:00:00",
        overdue: false,
        reason_code: "due",
        reason_summary: "今天需要巩固",
        completed_task_id: null,
      },
      {
        id: 2,
        knowledge_point_id: 2,
        knowledge_point_title: "MCP 的核心角色",
        status: "scheduled",
        priority_score: 60,
        recommended_at: now,
        due_at: "2026-07-30T14:00:00",
        overdue: false,
        reason_code: "future",
        reason_summary: "明天再复习",
        completed_task_id: null,
      },
    ];
    renderApp(<App />, "/workspace");

    expect(await screen.findByRole("heading", { name: "待处理" })).toBeInTheDocument();
    expect(screen.getAllByText("MCP 的定位").length).toBeGreaterThan(0);
    expect(screen.queryByText("明天再复习")).not.toBeInTheDocument();
  });

  it("保留今日学习旧路由", async () => {
    renderApp(<App />, "/today");
    expect(await screen.findByRole("heading", { name: "今日学习" })).toBeInTheDocument();
    expect(screen.getByText("三周入门 MCP")).toBeInTheDocument();
  });

  it("知识收件箱只声明本地真实来源", async () => {
    renderApp(<App />, "/inbox");
    expect(await screen.findByRole("heading", { name: "知识收件箱" })).toBeInTheDocument();
    expect(screen.getByText(/当前收件箱只包含真实本地上传资料/)).toBeInTheDocument();
    expect(screen.getByText("收件箱还是空的")).toBeInTheDocument();
    expect(screen.queryByText(/小时前/)).not.toBeInTheDocument();
  });

  it("旧资料路由重定向到合并页面", async () => {
    renderApp(<App />, "/materials");
    expect(await screen.findByRole("heading", { name: "资料与来源" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "资料与来源" })).toBeInTheDocument();
  });
});
