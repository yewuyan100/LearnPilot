import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import type { Note } from "../types";
import { renderApp } from "./render";


const now = "2026-08-01T04:00:00Z";
const response = (data: unknown, status = 200) => Promise.resolve(new Response(
  status === 204 ? null : JSON.stringify(data),
  { status, headers: { "Content-Type": "application/json" } },
));

function note(overrides: Partial<Note> = {}): Note {
  return {
    id: 1,
    title: "课程重点",
    content_markdown: '# 安全预览\n<script>alert("x")</script> **重点**',
    note_type: "course",
    status: "active",
    is_pinned: true,
    archived_at: null,
    tags: ["MCP"],
    links: [{ id: 1, entity_type: "course", entity_id: 1, relation_type: "context", entity_title: "MCP 基础", source_available: true, created_at: now }],
    sources: [],
    created_at: now,
    updated_at: now,
    ...overrides,
  };
}

describe("笔记本", () => {
  let notes: Note[];
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    notes = [note()];
    fetchMock = vi.fn((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/notes?") && (!init?.method || init.method === "GET")) {
        return response({ items: notes, total: notes.length, page: 1, page_size: 100, pages: notes.length ? 1 : 0 });
      }
      if (url.endsWith("/notes") && init?.method === "POST") {
        const payload = JSON.parse(String(init.body));
        const created = note({
          id: 2,
          title: payload.title || "未命名笔记",
          content_markdown: payload.content_markdown,
          note_type: payload.note_type,
          is_pinned: payload.is_pinned,
          tags: payload.tags,
          links: [],
        });
        notes = [created, ...notes];
        return response(created, 201);
      }
      if (url.includes("/notes/") && init?.method === "PATCH") {
        const id = Number(url.split("/notes/")[1]);
        const payload = JSON.parse(String(init.body));
        const current = notes.find((item) => item.id === id)!;
        const updated = note({
          ...current,
          title: payload.title || current.title,
          content_markdown: payload.content_markdown ?? current.content_markdown,
          note_type: payload.note_type ?? current.note_type,
          is_pinned: payload.is_pinned ?? current.is_pinned,
          tags: payload.tags ?? current.tags,
        });
        notes = notes.map((item) => item.id === id ? updated : item);
        return response(updated);
      }
      if (url.endsWith("/learning-goals")) return response([]);
      if (url.endsWith("/courses")) return response([{ id: 1, title: "MCP 基础" }]);
      if (url.includes("/courses/1/knowledge-points")) return response([]);
      if (url.includes("/materials")) return response([]);
      if (url.includes("/learning-activities")) return response({ items: [], total: 0, page: 1, page_size: 100, pages: 0 });
      if (url.endsWith("/learning-sessions")) return response([]);
      if (url.endsWith("/today")) return response({ date: "2026-08-01", current_goal: null, tasks: [], pending_count: 0, recent_course: null, recent_session: null });
      return response([]);
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("显示真实笔记、搜索筛选并安全预览 Markdown", async () => {
    renderApp(<App />, "/notes?note=1");
    expect(await screen.findByRole("heading", { name: "笔记本" })).toBeInTheDocument();
    expect(screen.getAllByText("MCP 基础").length).toBeGreaterThan(0);
    await userEvent.type(screen.getByLabelText("搜索笔记"), "重点");
    await waitFor(() => expect(fetchMock.mock.calls.filter(([url]) => String(url).includes("/notes?")).length).toBeGreaterThan(1));
    await userEvent.click(screen.getByRole("button", { name: "预览" }));
    expect(screen.queryByRole("script")).not.toBeInTheDocument();
    expect(screen.getByText('<script>alert("x")</script>')).toBeInTheDocument();
    expect(screen.getByText("重点")).toBeInTheDocument();
  });

  it("新建笔记会在 debounce 后自动保存，并支持 Ctrl+S", async () => {
    renderApp(<App />, "/notes?new=1");
    const title = await screen.findByLabelText("笔记标题");
    const body = screen.getByLabelText("Markdown 正文");
    await userEvent.type(title, "自动保存笔记");
    await userEvent.type(body, "记录真实学习内容");
    expect(screen.getByText("等待自动保存")).toBeInTheDocument();
    await waitFor(
      () => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true),
      { timeout: 2500 },
    );
    expect(await screen.findByText("已保存")).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("Markdown 正文"), "，继续补充");
    fireEvent.keyDown(window, { key: "s", ctrlKey: true });
    await waitFor(() => expect(fetchMock.mock.calls.some(([url, init]) => String(url).includes("/notes/2") && init?.method === "PATCH")).toBe(true));
  });
});
