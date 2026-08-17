import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Link, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
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
import type { TodayData } from "../types";
import { formatDateTime } from "../utils/format";
import { renderApp } from "./render";

const now = "2026-08-10T08:00:00Z";
const goalA = {
  id: 1,
  title: "Goal A",
  description: "Goal A description",
  target_date: "2026-08-31",
  daily_minutes: 30,
  current_level: "baseline",
  status: "active",
  is_demo: false,
  created_at: now,
  updated_at: now,
};
const goalB = { ...goalA, id: 2, title: "Goal B", description: "Goal B description" };
const sessionA = {
  id: 101,
  learning_goal_id: goalA.id,
  started_at: "2026-08-09T03:21:00Z",
  ended_at: null,
  status: "active",
  notes: "Goal A session content",
};
const sessionB = {
  id: 202,
  learning_goal_id: goalB.id,
  started_at: "2026-08-10T12:34:00Z",
  ended_at: null,
  status: "active",
  notes: "Goal B session content",
};

function today(recentSession: TodayData["recent_session"]): TodayData {
  return {
    date: "2026-08-10",
    current_goal: {
      id: goalA.id,
      title: goalA.title,
      target_date: goalA.target_date,
      daily_minutes: goalA.daily_minutes,
      current_level: goalA.current_level,
    },
    tasks: [],
    pending_count: 0,
    blocked_count: 0,
    recent_course: null,
    recent_session: recentSession,
  };
}

function mockGoalDetail(recentSession: TodayData["recent_session"]) {
  vi.spyOn(goalsApi, "get").mockImplementation(async (id) => id === goalA.id ? goalA : goalB);
  vi.spyOn(coursesApi, "list").mockResolvedValue([]);
  vi.spyOn(coursesApi, "points").mockResolvedValue([]);
  vi.spyOn(materialLearningApi, "goalMaterials").mockResolvedValue([]);
  vi.spyOn(dashboardApi, "today").mockResolvedValue(today(recentSession));
  vi.spyOn(notesApi, "list").mockResolvedValue({ items: [], total: 0, page: 1, page_size: 3, pages: 0 });
  vi.spyOn(masteryApi, "weakPoints").mockResolvedValue([]);
  vi.spyOn(masteryApi, "list").mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100, pages: 0 });
  vi.spyOn(activitiesApi, "list").mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100, pages: 0 });
  vi.spyOn(wrongAnswersApi, "list").mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100, pages: 0 });
  vi.spyOn(dashboardApi, "reviews").mockResolvedValue({ knowledge_points: [] } as never);
  vi.spyOn(nextActionApi, "get").mockResolvedValue({ learning_goal_id: goalA.id } as never);
}

function recentLine(startedAt: string) {
  return `${formatDateTime(startedAt)} 开始了一次推进`;
}

function GoalRoutes() {
  return <>
    <nav>
      <Link to="/items/1?view=history">Open Goal A</Link>
      <Link to="/items/2?view=history">Open Goal B</Link>
    </nav>
    <Routes>
      <Route path="/items/:id" element={<GoalDetailPage />} />
    </Routes>
  </>;
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("Final Fix Batch 2B - Goal recent-session ownership", () => {
  it("shows a recent session owned by Goal A", async () => {
    mockGoalDetail(sessionA);
    renderApp(<GoalRoutes />, "/items/1?view=history");

    expect(await screen.findByRole("heading", { level: 1, name: "Goal A" })).toBeInTheDocument();
    expect(screen.getByText(recentLine(sessionA.started_at))).toBeInTheDocument();
  });

  it("does not leak Goal B's global recent session into Goal A", async () => {
    mockGoalDetail(sessionB);
    renderApp(<GoalRoutes />, "/items/1?view=history");

    expect(await screen.findByRole("heading", { level: 1, name: "Goal A" })).toBeInTheDocument();
    expect(screen.queryByText(recentLine(sessionB.started_at))).not.toBeInTheDocument();
    expect(screen.queryByText(sessionB.notes)).not.toBeInTheDocument();
    expect(screen.getByText("还没有新的推进记录。")).toBeInTheDocument();
  });

  it("uses the safe empty state when there is no recent session", async () => {
    mockGoalDetail(null);
    renderApp(<GoalRoutes />, "/items/1?view=history");

    expect(await screen.findByRole("heading", { level: 1, name: "Goal A" })).toBeInTheDocument();
    expect(screen.getByText("还没有新的推进记录。")).toBeInTheDocument();
  });

  it("keeps ownership correct while switching from Goal A to Goal B", async () => {
    mockGoalDetail(sessionB);
    renderApp(<GoalRoutes />, "/items/1?view=history");

    expect(await screen.findByRole("heading", { level: 1, name: "Goal A" })).toBeInTheDocument();
    expect(screen.queryByText(recentLine(sessionB.started_at))).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("link", { name: "Open Goal B" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Goal B" })).toBeInTheDocument();
    expect(screen.getByText(recentLine(sessionB.started_at))).toBeInTheDocument();
  });

  it("keeps Goal A isolated after a refresh-equivalent remount", async () => {
    mockGoalDetail(sessionB);
    const first = renderApp(<GoalRoutes />, "/items/1?view=history");

    expect(await screen.findByRole("heading", { level: 1, name: "Goal A" })).toBeInTheDocument();
    expect(screen.queryByText(recentLine(sessionB.started_at))).not.toBeInTheDocument();
    first.unmount();

    renderApp(<GoalRoutes />, "/items/1?view=history");
    expect(await screen.findByRole("heading", { level: 1, name: "Goal A" })).toBeInTheDocument();
    expect(screen.queryByText(recentLine(sessionB.started_at))).not.toBeInTheDocument();
    expect(screen.getByText("还没有新的推进记录。")).toBeInTheDocument();
  });
});
