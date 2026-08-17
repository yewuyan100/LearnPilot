import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes, useLocation } from "react-router-dom";
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
import { GoalsPage } from "../pages/PlanningPages";
import { NotesPage } from "../pages/NotesPage";
import type { LearningGoal, Note } from "../types";
import { renderApp } from "./render";

const now = "2026-08-13T04:00:00Z";
const goal: LearningGoal = {
  id: 7,
  title: "学习",
  description: "把真实能力推进到可交付",
  target_date: "2026-09-01",
  daily_minutes: 40,
  current_level: "入门",
  status: "active",
  is_demo: false,
  created_at: now,
  updated_at: now,
};

const note: Note = {
  id: 3,
  title: "修正",
  content_markdown: "正文保持不变",
  note_type: "study",
  status: "active",
  is_pinned: false,
  archived_at: null,
  tags: [],
  links: [],
  sources: [],
  created_at: now,
  updated_at: now,
};

function setupPlanning() {
  vi.spyOn(goalsApi, "list").mockResolvedValue([goal]);
  vi.spyOn(coursesApi, "list").mockResolvedValue([]);
  vi.spyOn(dashboardApi, "today").mockResolvedValue({
    date: "2026-08-13",
    current_goal: goal,
    tasks: [],
    pending_count: 0,
    blocked_count: 0,
    recent_course: null,
    recent_session: null,
  } as never);
  vi.spyOn(nextActionApi, "get").mockResolvedValue(null as never);
}

function setupDetail() {
  vi.spyOn(goalsApi, "get").mockResolvedValue(goal);
  vi.spyOn(coursesApi, "list").mockResolvedValue([]);
  vi.spyOn(materialLearningApi, "goalMaterials").mockResolvedValue([]);
  vi.spyOn(dashboardApi, "today").mockResolvedValue({
    date: "2026-08-13", current_goal: goal, tasks: [], pending_count: 0,
    blocked_count: 0, recent_course: null, recent_session: null,
  } as never);
  vi.spyOn(notesApi, "list").mockResolvedValue({ items: [], total: 0, page: 1, page_size: 3, pages: 0 });
  vi.spyOn(masteryApi, "weakPoints").mockResolvedValue([]);
  vi.spyOn(masteryApi, "list").mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100, pages: 0 } as never);
  vi.spyOn(activitiesApi, "list").mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100, pages: 0 } as never);
  vi.spyOn(wrongAnswersApi, "list").mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100, pages: 0 } as never);
  vi.spyOn(dashboardApi, "reviews").mockResolvedValue({ knowledge_points: [] } as never);
  vi.spyOn(nextActionApi, "get").mockResolvedValue(null as never);
}

function setupNotes() {
  vi.spyOn(notesApi, "list").mockResolvedValue({ items: [note], total: 1, page: 1, page_size: 100, pages: 1 });
  vi.spyOn(goalsApi, "list").mockResolvedValue([]);
  vi.spyOn(coursesApi, "list").mockResolvedValue([]);
  vi.spyOn(activitiesApi, "list").mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100, pages: 0 } as never);
  vi.spyOn(dashboardApi, "today").mockResolvedValue({ date: "2026-08-13", current_goal: null, tasks: [], pending_count: 0, blocked_count: 0, recent_course: null, recent_session: null } as never);
}

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname}{location.search}</output>;
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("Final usability closure · planning and items", () => {
  it("uses a compact live-count toolbar and removes the old title/subtitle layer", async () => {
    setupPlanning();
    renderApp(<GoalsPage/>, "/items");
    const toolbar = await screen.findByRole("banner", { name: "规划状态和操作" });
    expect(within(toolbar).getByText("进行中")).toBeInTheDocument();
    expect(within(toolbar).getByText("· 1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "创建事项" })).toBeInTheDocument();
    expect(screen.queryByText(/当前推进 1 项/)).not.toBeInTheDocument();
    expect(screen.queryByText(/先看最需要保持连续性/)).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: goal.title })).toBeInTheDocument();
  });

  it("renames the canonical item and synchronizes the planning surface", async () => {
    setupPlanning();
    const renamed = { ...goal, title: "AI 应用开发学习" };
    vi.spyOn(goalsApi, "update").mockResolvedValue(renamed);
    const list = vi.mocked(goalsApi.list);
    list.mockResolvedValueOnce([goal]).mockResolvedValue([renamed]);

    renderApp(<GoalsPage/>, "/items");
    await userEvent.click(await screen.findByRole("button", { name: `管理事项 ${goal.title}` }));
    await userEvent.click(screen.getByRole("menuitem", { name: "重命名" }));
    const dialog = screen.getByRole("dialog");
    const input = within(dialog).getByLabelText("新的事项名称");
    await userEvent.clear(input);
    await userEvent.type(input, "  AI 应用开发学习  ");
    await userEvent.click(within(dialog).getByRole("button", { name: "保存" }));
    await waitFor(() => expect(goalsApi.update).toHaveBeenCalledWith(goal.id, { title: renamed.title }));
    expect(await screen.findByRole("heading", { name: renamed.title })).toBeInTheDocument();
  });

  it("requires delete confirmation and cancel makes no request", async () => {
    setupPlanning();
    vi.spyOn(goalsApi, "remove").mockResolvedValue(undefined);
    renderApp(<GoalsPage/>, "/items");
    await userEvent.click(await screen.findByRole("button", { name: `管理事项 ${goal.title}` }));
    await userEvent.click(screen.getByRole("menuitem", { name: "删除事项" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/资料、笔记、摘录和回答会保留/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "取消" }));
    expect(goalsApi.remove).not.toHaveBeenCalled();
  });

  it("deletes from detail and navigates to canonical planning index", async () => {
    setupDetail();
    vi.spyOn(goalsApi, "remove").mockResolvedValue(undefined);
    renderApp(<><Routes><Route path="/items/:id" element={<GoalDetailPage/>}/><Route path="/items" element={<p>规划索引</p>}/></Routes><LocationProbe/></>, "/items/7");
    await userEvent.click(await screen.findByRole("button", { name: `管理事项 ${goal.title}` }));
    await userEvent.click(screen.getByRole("menuitem", { name: "删除事项" }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "删除事项" }));
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/items"));
    expect(screen.getByText("规划索引")).toBeInTheDocument();
  });
});

describe("Final usability closure · notes", () => {
  it("renames via the canonical title editor without a duplicate menu action", async () => {
    setupNotes();
    vi.spyOn(notesApi, "update").mockResolvedValue({ ...note, title: "LangGraph Checkpoint 复盘" });
    renderApp(<NotesPage/>, "/notes?note=3");
    const title = await screen.findByLabelText("笔记标题");
    await userEvent.clear(title);
    await userEvent.type(title, "LangGraph Checkpoint 复盘");
    await waitFor(() => expect(notesApi.update).toHaveBeenCalled(), { timeout: 2500 });
    await userEvent.click(screen.getByRole("button", { name: `管理笔记 ${note.title}` }));
    expect(screen.queryByRole("menuitem", { name: "重命名" })).not.toBeInTheDocument();
  });

  it("keeps archive and delete together, confirms delete, supports cancel and success", async () => {
    setupNotes();
    vi.spyOn(notesApi, "remove").mockResolvedValue(undefined);
    renderApp(<NotesPage/>, "/notes?note=3");
    await userEvent.click(await screen.findByRole("button", { name: `管理笔记 ${note.title}` }));
    expect(screen.getByRole("menuitem", { name: "归档" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("menuitem", { name: "删除笔记" }));
    let dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/关联事项和资料本身不会被删除/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "取消" }));
    expect(notesApi.remove).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: `管理笔记 ${note.title}` }));
    await userEvent.click(screen.getByRole("menuitem", { name: "删除笔记" }));
    dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "删除笔记" }));
    await waitFor(() => expect(notesApi.remove).toHaveBeenCalledWith(note.id));
  });
});
