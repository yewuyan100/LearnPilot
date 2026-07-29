import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { renderApp } from "./render";

const now = "2026-07-29T10:00:00";
const goal = { id: 1, title: "三周入门 MCP", description: "", target_date: "2026-08-19", daily_minutes: 40, current_level: "了解 API", status: "active", is_demo: false, created_at: now, updated_at: now };
const course = { id: 1, learning_goal_id: 1, learning_goal_title: goal.title, title: "MCP 基础", description: "", status: "active", knowledge_point_count: 1, created_at: now, updated_at: now };
const point = { id: 1, course_id: 1, title: "MCP 的定位", description: "理解协议定位", order_index: 1, estimated_minutes: 20, status: "learning", created_at: now, updated_at: now };
const task = { id: 1, learning_goal_id: 1, course_id: 1, knowledge_point_id: 1, title: "学习 MCP 的定位", task_type: "learning", estimated_minutes: 20, scheduled_date: "2026-07-29", status: "pending", created_at: now, updated_at: now };
const session = { id: 1, learning_goal_id: 1, course_id: 1, knowledge_point_id: 1, daily_task_id: 1, started_at: now, ended_at: null, status: "active", notes: "", goal_title: goal.title, course_title: course.title, knowledge_point_title: point.title, task_title: task.title, created_at: now, updated_at: now };

function response(data: unknown, status = 200) {
  return Promise.resolve(new Response(status === 204 ? null : JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } }));
}

describe("PersonalLearning V1 UI", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/today")) return response({ date: "2026-07-29", current_goal: goal, tasks: [task], pending_count: 1, recent_course: course, recent_session: null });
      if (url.endsWith("/learning-goals") && init?.method === "POST") return response(goal, 201);
      if (url.endsWith("/learning-goals")) return response([goal]);
      if (url.endsWith("/courses")) return response([course]);
      if (url.endsWith("/courses/1/knowledge-points") && init?.method === "POST") return response(point, 201);
      if (url.endsWith("/courses/1/knowledge-points")) return response([point]);
      if (url.endsWith("/materials/upload")) return response({
        id: 1,
        title: "guide",
        original_filename: "guide.md",
        stored_filename: "x.md",
        file_path: "x",
        source_type: "md",
        mime_type: "text/markdown",
        file_size: 10,
        processing_status: "ready",
        ingestion_status: "pending",
        indexing_status: "pending",
        chunk_count: 0,
        indexed_chunk_count: 0,
        processed_at: null,
        indexed_at: null,
        error_message: null,
        created_at: now,
        updated_at: now,
      }, 201);
      if (url.endsWith("/materials/index/status")) return response({
        available: false,
        healthy: true,
        stale: false,
        message: "尚未建立索引",
        chunk_count: 0,
        dimension: null,
        model_name: null,
        model_revision: null,
        built_at: null,
      });
      if (url.includes("/materials")) return response([]);
      if (url.endsWith("/learning-sessions") && init?.method === "POST") return response(session, 201);
      if (url.endsWith("/learning-sessions/1") && init?.method === "PATCH") return response({ ...session, status: "completed", ended_at: now, notes: "学习笔记" });
      if (url.endsWith("/learning-sessions/1")) return response(session);
      return response([]);
    }));
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders navigation and loads today data", async () => {
    renderApp(<App />);
    expect(await screen.findByRole("heading", { name: "今日学习" })).toBeInTheDocument();
    expect(screen.getByText("三周入门 MCP")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "课程" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "资料" })).toBeInTheDocument();
  });

  it("creates a learning goal from the empty state", async () => {
    vi.stubGlobal("fetch", vi.fn((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/today")) {
        return response({
          date: "2026-07-29",
          current_goal: null,
          tasks: [],
          pending_count: 0,
          recent_course: null,
          recent_session: null,
        });
      }
      if (url.endsWith("/learning-goals") && init?.method === "POST") return response(goal, 201);
      return response([]);
    }));

    renderApp(<App />);
    await userEvent.click(await screen.findByRole("button", { name: "创建目标" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("目标名称"), "三周入门 MCP");
    await userEvent.type(within(dialog).getByLabelText("当前水平"), "了解普通 API");
    await userEvent.click(within(dialog).getByRole("button", { name: "创建目标" }));
    await waitFor(() =>
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining("/learning-goals"),
        expect.objectContaining({ method: "POST" }),
      ),
    );
  });

  it("starts a learning session", async () => {
    renderApp(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /开始学习/ }));
    expect(await screen.findByRole("heading", { name: "MCP 的定位" })).toBeInTheDocument();
  });

  it("uploads a file", async () => {
    renderApp(<App />, "/materials");
    const input = await screen.findByLabelText("", { selector: "input[type=file]" }).catch(() => document.querySelector("input[type=file]") as HTMLElement);
    const file = new File(["# MCP"], "guide.md", { type: "text/markdown" });
    fireEvent.change(input, { target: { files: [file] } });
    await waitFor(() => expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/materials/upload"), expect.objectContaining({ method: "POST" })));
  });

  it("loads courses and creates a knowledge point", async () => {
    renderApp(<App />, "/courses");
    expect(await screen.findByRole("heading", { name: "MCP 基础" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /添加知识点/ }));
    const dialog = screen.getByRole("dialog");
    await userEvent.type(dialog.querySelector("input")!, "Resources");
    await userEvent.click(within(dialog).getByRole("button", { name: "添加知识点" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/knowledge-points"), expect.objectContaining({ method: "POST" })));
  });

  it("completes and restores a learning session", async () => {
    renderApp(<App />, "/learning-sessions/1");
    const notes = await screen.findByLabelText("学习笔记");
    await userEvent.type(notes, "学习笔记");
    await userEvent.click(screen.getByRole("button", { name: /完成本次学习/ }));
    await waitFor(() => expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/learning-sessions/1"), expect.objectContaining({ method: "PATCH" })));
  });

  it("shows backend error state", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("offline"))));
    renderApp(<App />);
    expect(await screen.findByText("数据未能加载")).toBeInTheDocument();
    expect(screen.getByText(/无法连接后端/)).toBeInTheDocument();
  });
});
