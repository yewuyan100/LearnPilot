import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  activitiesApi,
  coursesApi,
  dashboardApi,
  goalsApi,
  masteryApi,
  materialLearningApi,
  nextActionApi,
  notesApi,
  wrongAnswersApi,
} from "../api/resources";
import { GoalDetailPage } from "../pages/GoalDetailPage";
import { renderApp } from "./render";

const now = "2026-08-10T08:00:00Z";
const goal = {
  id: 2,
  title: "Goal 2",
  description: "Goal 2 description",
  target_date: "2026-08-31",
  daily_minutes: 40,
  current_level: "入门",
  status: "active",
  is_demo: false,
  created_at: now,
  updated_at: now,
};

function mockGoalDetail() {
  vi.spyOn(goalsApi, "get").mockResolvedValue(goal as never);
  vi.spyOn(coursesApi, "list").mockResolvedValue([{
    id: 10,
    learning_goal_id: goal.id,
    title: "Goal 2 路线",
    status: "active",
  }] as never);
  vi.spyOn(coursesApi, "points").mockResolvedValue([{
    id: 21,
    course_id: 10,
    title: "当前路线步骤",
    status: "learning",
  }] as never);
  vi.spyOn(materialLearningApi, "goalMaterials").mockResolvedValue([{
    material_id: 7,
    material_title: "Goal 2 资料",
    original_filename: "goal-2.pdf",
    indexing_status: "completed",
    contexts: [],
  }] as never);
  vi.spyOn(dashboardApi, "today").mockResolvedValue({
    date: "2026-08-10",
    current_goal: {
      id: goal.id,
      title: goal.title,
      target_date: goal.target_date,
      daily_minutes: goal.daily_minutes,
      current_level: goal.current_level,
    },
    tasks: [{ id: 81, learning_goal_id: goal.id, title: "已完成任务", status: "completed" }],
    pending_count: 0,
    blocked_count: 0,
    recent_course: null,
    recent_session: {
      id: 91,
      learning_goal_id: goal.id,
      started_at: now,
      ended_at: null,
      status: "active",
      notes: "",
    },
  } as never);
  vi.spyOn(notesApi, "list").mockResolvedValue({
    items: [{ id: 31, title: "Goal 2 笔记", updated_at: now }],
    total: 1,
    page: 1,
    page_size: 3,
    pages: 1,
  } as never);
  vi.spyOn(masteryApi, "weakPoints").mockResolvedValue([{
    course_id: 10,
    knowledge_point_id: 21,
    knowledge_point_title: "需要加强的步骤",
  }] as never);
  vi.spyOn(masteryApi, "list").mockResolvedValue({
    items: [{
      course_id: 10,
      knowledge_point_id: 22,
      knowledge_point_title: "已经稳定的步骤",
      mastery_level: "proficient",
    }],
    total: 1,
    page: 1,
    page_size: 100,
    pages: 1,
  } as never);
  vi.spyOn(activitiesApi, "list").mockResolvedValue({
    items: [{
      id: 41,
      course_id: 10,
      title: "Goal 2 练习",
      completed_attempt_count: 1,
      updated_at: now,
    }],
    total: 1,
    page: 1,
    page_size: 100,
    pages: 1,
  } as never);
  vi.spyOn(wrongAnswersApi, "list").mockResolvedValue({
    items: [{ id: 51, course_id: 10, status: "active" }],
    total: 1,
    page: 1,
    page_size: 100,
    pages: 1,
  } as never);
  vi.spyOn(dashboardApi, "reviews").mockResolvedValue({
    knowledge_points: [{ id: 61, course_id: 10, title: "待复习步骤" }],
  } as never);
  vi.spyOn(nextActionApi, "get").mockResolvedValue({
    learning_goal_id: goal.id,
    knowledge_point_id: 21,
    action_type: "continue_learning",
    title: "继续当前路线",
    reason: "保持 Goal 2 上下文",
    cta_label: "继续推进",
    cta_href: "/knowledge-points/21",
  } as never);
}

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname}{location.search}</output>;
}

function HistoryControls() {
  const navigate = useNavigate();
  return <div>
    <button type="button" onClick={() => navigate(-1)}>测试后退</button>
    <button type="button" onClick={() => navigate(1)}>测试前进</button>
  </div>;
}

function GoalRoutes({ historyControls = false }: { historyControls?: boolean }) {
  return <>
    {historyControls && <HistoryControls />}
    <Routes><Route path="/items/:id" element={<GoalDetailPage />} /></Routes>
    <LocationProbe />
  </>;
}

function expectActiveView(label: string) {
  expect(screen.getByRole("button", { name: label })).toHaveAttribute("aria-current", "page");
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

beforeEach(() => {
  mockGoalDetail();
});

describe("Final UX Batch 3B · Goal Detail URL contract", () => {
  it.each([
    ["/items/2", "概览", "继续当前路线"],
    ["/items/2?view=overview", "概览", "继续当前路线"],
    ["/items/2?view=route", "路线", "行动路线"],
    ["/items/2?view=content", "内容", "关联内容"],
    ["/items/2?view=feedback", "反馈", "最近练习"],
    ["/items/2?view=history", "记录", "回顾"],
  ])("%s 直接打开正确视图", async (path, activeLabel, heading) => {
    renderApp(<GoalRoutes />, path);
    expect(await screen.findByRole("heading", { level: 1, name: goal.title })).toBeInTheDocument();
    expectActiveView(activeLabel);
    expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
  });

  it("非法 view 安全回退 overview", async () => {
    renderApp(<GoalRoutes />, "/items/2?view=foo");
    expect(await screen.findByRole("heading", { name: "继续当前路线" })).toBeInTheDocument();
    expectActiveView("概览");
    expect(screen.queryByRole("heading", { name: "行动路线" })).not.toBeInTheDocument();
    expect(screen.getByTestId("location")).toHaveTextContent("/items/2?view=foo");
  });

  it("点击更新 URL 并保留已有 query params", async () => {
    renderApp(<GoalRoutes />, "/items/2?source=demo");
    expect(await screen.findByRole("heading", { name: goal.title })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "路线" }));
    expect(screen.getByTestId("location")).toHaveTextContent("/items/2?source=demo&view=route");
    expectActiveView("路线");
  });

  it("refresh-equivalent remount 保留当前视图", async () => {
    const first = renderApp(<GoalRoutes />, "/items/2?view=feedback");
    expect(await screen.findByRole("heading", { name: "最近练习" })).toBeInTheDocument();
    first.unmount();

    renderApp(<GoalRoutes />, "/items/2?view=feedback");
    expect(await screen.findByRole("heading", { name: "最近练习" })).toBeInTheDocument();
    expectActiveView("反馈");
  });

  it("Browser Back / Forward 恢复对应视图", async () => {
    renderApp(<GoalRoutes historyControls />, "/items/2");
    expect(await screen.findByRole("heading", { name: goal.title })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "路线" }));
    await userEvent.click(screen.getByRole("button", { name: "内容" }));
    expectActiveView("内容");

    await userEvent.click(screen.getByRole("button", { name: "测试后退" }));
    await waitFor(() => expectActiveView("路线"));
    expect(screen.getByRole("heading", { name: "行动路线" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "测试前进" }));
    await waitFor(() => expectActiveView("内容"));
    expect(screen.getByRole("heading", { name: "关联内容" })).toBeInTheDocument();
  });
});

describe("Final UX Batch 3B · Goal Detail view isolation and CTA contract", () => {
  it("overview 只展开下一步，Goal identity 与头部行动保持可见", async () => {
    renderApp(<GoalRoutes />, "/items/2");
    expect(await screen.findByRole("heading", { level: 1, name: goal.title })).toBeInTheDocument();
    expect(screen.getByText("下一步")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "继续推进" })).toHaveAttribute("href", "/knowledge-points/21");
    expect(screen.getByRole("button", { name: "关联资料" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "基于资料提问" })).toHaveAttribute(
      "href",
      "/knowledge?tab=qa&scope=learning_goal&learning_goal_id=2",
    );
    expect(screen.getByRole("link", { name: "AI 协作" })).toHaveAttribute("href", "/ai?goal_id=2");
    expect(screen.queryByRole("heading", { name: "行动路线" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "关联内容" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "练习与反馈" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "回顾" })).not.toBeInTheDocument();
  });

  it("route / content / feedback / history 各自只显示对应主体并保留 Goal header", async () => {
    renderApp(<GoalRoutes />, "/items/2");
    expect(await screen.findByRole("heading", { level: 1, name: goal.title })).toBeInTheDocument();

    const views = [
      ["路线", "行动路线"],
      ["内容", "关联内容"],
      ["反馈", "最近练习"],
      ["记录", "回顾"],
    ] as const;
    for (const [label, heading] of views) {
      await userEvent.click(screen.getByRole("button", { name: label }));
      expect(screen.getByRole("heading", { level: 1, name: goal.title })).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
      for (const otherHeading of views.map((view) => view[1]).filter((value) => value !== heading)) {
        expect(screen.queryByRole("heading", { name: otherHeading })).not.toBeInTheDocument();
      }
    }
  });

  it("content / feedback / history 保留现有 goal/context URL", async () => {
    renderApp(<GoalRoutes />, "/items/2?view=content");
    expect(await screen.findByRole("heading", { name: "关联内容" })).toBeInTheDocument();
    expect(screen.getByText("Goal 2 资料")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Goal 2 笔记" })).toHaveAttribute("href", "/knowledge?tab=notes&note=31");
    expect(screen.getByRole("link", { name: "记录笔记" })).toHaveAttribute(
      "href",
      "/knowledge?tab=notes&new=1&entity_type=learning_goal&entity_id=2",
    );

    await userEvent.click(screen.getByRole("button", { name: "反馈" }));
    expect(screen.getByRole("link", { name: /Goal 2 练习/ })).toHaveAttribute(
      "href",
      "/activities/41?origin=goal&goal_id=2",
    );

    await userEvent.click(screen.getByRole("button", { name: "记录" }));
    expect(screen.getByRole("link", { name: "记录一次回顾" })).toHaveAttribute(
      "href",
      "/knowledge?tab=notes&new=1&note_type=reflection&entity_type=learning_goal&entity_id=2",
    );
    expect(screen.getByText("已完成：已完成任务")).toBeInTheDocument();
  });

  it("非法 goal id 仍使用既有 NotFound contract", async () => {
    const get = vi.mocked(goalsApi.get);
    renderApp(<GoalRoutes />, "/items/foo?view=feedback");
    expect(await screen.findByText("页面不存在")).toBeInTheDocument();
    expect(get).not.toHaveBeenCalled();
  });
});
