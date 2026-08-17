import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import type { NextLearningAction } from "../types";
import { renderApp } from "./render";

const now = "2026-08-08T12:00:00Z";
const item = { id: 7, title: "提升 AI 应用开发能力", description: "能够独立交付带 AI 协作能力的应用", target_date: "2026-09-01", daily_minutes: 45, current_level: "能够开发普通 Web API", status: "active", is_demo: false, created_at: now, updated_at: now };
const route = { id: 11, learning_goal_id: 7, learning_goal_title: item.title, title: "AI 应用交付路线", description: "", status: "active", knowledge_point_count: 1, created_at: now, updated_at: now };
const step = { id: 17, course_id: 11, title: "构建可验证的工具调用", description: "", order_index: 1, estimated_minutes: 30, status: "learning", created_at: now, updated_at: now };

function json(data: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } }));
}

function LocationProbe() {
  return <output data-testid="location">{useLocation().pathname}</output>;
}

function installWorkspace(action: NextLearningAction | null, withItem = true) {
  vi.stubGlobal("fetch", vi.fn((input: string | URL) => {
    const url = String(input);
    if (url.endsWith("/today")) return json({ date: "2026-08-08", current_goal: withItem ? item : null, tasks: [], pending_count: 0, blocked_count: 0, recent_course: withItem ? route : null, recent_session: null });
    if (url.endsWith("/courses/11/knowledge-points")) return json([step]);
    if (url.endsWith("/courses")) return json(withItem ? [route] : []);
    if (url.endsWith("/learning-goals")) return json(withItem ? [item] : []);
    if (url.includes("/next-learning-action")) return json(action);
    if (url.includes("/reviews")) return json([]);
    return json([]);
  }));
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("V12B Frontend IA Migration", () => {
  it("一级导航固定为六个文字入口且不带图标", async () => {
    installWorkspace(null, false);
    renderApp(<App />, "/workspace");

    await screen.findByRole("heading", { name: "工作台" });
    const primary = screen.getByRole("navigation", { name: "主导航" });
    expect(within(primary).getAllByRole("link").map((link) => link.textContent)).toEqual([
      "工作台", "学习规划", "知识库", "发现", "AI 协作",
    ]);
    expect(primary.querySelectorAll("svg")).toHaveLength(0);
    expect(screen.getAllByRole("link", { name: "设置" })[0]).toHaveAttribute("href", "/settings");
  });

  it("新用户从工作台创建事项后直接进入事项详情，而不是课程页", async () => {
    let created = false;
    const createdItem = { ...item, id: 42 };
    vi.stubGlobal("fetch", vi.fn((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/learning-goals") && init?.method === "POST") { created = true; return json(createdItem, 201); }
      if (url.endsWith("/learning-goals/42/materials")) return json([]);
      if (url.endsWith("/learning-goals/42")) return json(createdItem);
      if (url.endsWith("/learning-goals")) return json(created ? [createdItem] : []);
      if (url.endsWith("/today")) return json({ date: "2026-08-08", current_goal: created ? createdItem : null, tasks: [], pending_count: 0, blocked_count: 0, recent_course: null, recent_session: null });
      if (url.endsWith("/courses")) return json([]);
      if (url.includes("/mastery/weak-points")) return json([]);
      if (url.includes("/notes?")) return json({ items: [], total: 0, page: 1, page_size: 3, pages: 0 });
      if (url.includes("/next-learning-action")) return json(null);
      if (url.includes("/reviews")) return json([]);
      return json([]);
    }));

    renderApp(<><App /><LocationProbe /></>, "/workspace");
    await userEvent.click(await screen.findByRole("button", { name: "创建事项" }));
    await userEvent.type(screen.getByLabelText("事项名称"), createdItem.title);
    await userEvent.type(screen.getByLabelText("想达成的结果"), createdItem.description);
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "创建事项" }));

    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/items/42"));
    expect(await screen.findByRole("heading", { name: createdItem.title })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /课程/ })).not.toBeInTheDocument();
  });

  it.each([
    ["resume_session", "继续推进", "/learning-sessions/19"],
    ["learn", "开始推进", "/today"],
    ["replan_required", "调整安排", "/items/7"],
    ["review_proposal", "审查 AI 建议", "/plan-adjustments/suggestion-1"],
  ] as const)("当前事项的 %s 行动使用 NextLearningAction CTA", async (actionType, label, href) => {
    installWorkspace({
      action_type: actionType,
      target_kind: "item",
      target_id: 17,
      learning_goal_id: 7,
      course_id: 11,
      course_title: route.title,
      knowledge_point_id: actionType === "review_proposal" ? null : 17,
      knowledge_point_title: actionType === "review_proposal" ? null : step.title,
      title: label,
      reason_code: "v12b-test",
      reason: "这是根据当前真实状态确定的下一步。",
      priority: 100,
      estimated_minutes: 30,
      from_formal_plan: true,
      is_due_review: false,
      plan_id: 1,
      plan_item_id: 1,
      cta_label: label,
      cta_href: href,
      action_signature: actionType.repeat(8),
      available_minutes: null,
    });
    renderApp(<App />, "/workspace");
    expect(await screen.findByRole("link", { name: label })).toHaveAttribute("href", href);
  });

  it("事项列表使用既有目标数据，但不暴露内部模型术语", async () => {
    installWorkspace({
      action_type: "review_proposal", target_kind: "proposal", target_id: 3, learning_goal_id: 7, course_id: 11, course_title: route.title, knowledge_point_id: null, knowledge_point_title: null,
      title: "审查路线建议", reason_code: "proposal", reason: "有一条建议等待决定。", priority: 100, estimated_minutes: 0, from_formal_plan: false, is_due_review: false, plan_id: 1, plan_item_id: null,
      cta_label: "审查建议", cta_href: "/plan-adjustments/3", action_signature: "proposal-signature", available_minutes: null,
    });
    renderApp(<App />, "/items");

    expect(await screen.findByRole("heading", { name: item.title })).toBeInTheDocument();
    expect(screen.getByText(item.description)).toBeInTheDocument();
    expect(await screen.findByText("审查路线建议")).toBeInTheDocument();
    expect(screen.getByText("有一条建议待你处理")).toBeInTheDocument();
    expect(screen.getByRole("main").textContent).not.toMatch(/学习目标|正式课程|知识点|Goal|Course|KnowledgePoint|StudyPlanVersion/);
  });

  it.each([
    ["/goals", "规划状态和操作"],
    ["/support", "从当前问题开始"],
    ["/materials", "资料与来源"],
    ["/rag", "资料问答"],
    ["/today", "今日学习"],
  ])("旧地址 %s 仍可到达可用页面", async (path, heading) => {
    vi.stubGlobal("fetch", vi.fn((input: string | URL) => {
      const url = String(input);
      if (url.endsWith("/today")) return json({ date: "2026-08-08", current_goal: null, tasks: [], pending_count: 0, blocked_count: 0, recent_course: null, recent_session: null });
      if (url.endsWith("/materials/index/status")) return json({ available: false, building: false, model_name: "BAAI/bge-m3", embedding_dimension: null, chunk_count: 0, built_at: null, index_version: null, stale: false, error_message: null });
      if (url.endsWith("/rag/status")) return json({ llm_configured: false, provider: "", model: "", index_available: false, index_stale: false, index_version: null, rag_prompt_version: "", rewrite_prompt_version: "" });
      if (url.includes("/rag/conversations")) return json({ items: [], total: 0, page: 1, page_size: 100, pages: 0 });
      if (url.includes("/notes?")) return json({ items: [], total: 0, page: 1, page_size: 100, pages: 0 });
      if (url.includes("/agent/conversations")) return json([]);
      if (url.includes("/next-learning-action")) return json(null);
      if (url.includes("/study-plans/active")) return json(null);
      if (url.includes("/reviews")) return json([]);
      if (url.includes("/materials?")) return json([]);
      if (url.endsWith("/learning-goals") || url.endsWith("/courses")) return json([]);
      return json([]);
    }));
    renderApp(<App />, path);
    if (path === "/goals") {
      expect(await screen.findByRole("banner", { name: heading })).toBeInTheDocument();
    } else {
      expect(await screen.findByRole("heading", { name: heading })).toBeInTheDocument();
    }
  });

  it("发现页明确没有接入外部数据，不伪造趋势或推荐", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json([])));
    renderApp(<App />, "/explore");
    expect(await screen.findByRole("heading", { name: "从已知，继续探索未知" })).toBeInTheDocument();
    expect(screen.getByText("外部资料与趋势来源尚未接入。")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "暂无外部内容" })).toBeInTheDocument();
    expect(screen.queryByText(/当前版本|入口已经就位|虚假的推荐或趋势/)).not.toBeInTheDocument();
  });
});
