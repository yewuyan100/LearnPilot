import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { GrowthReviewPage } from "../pages/GrowthReviewPage";
import { renderApp } from "./render";


const json = (data: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } }));

describe("成长复盘", () => {
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it("把用户填写的真实复盘保存为 reflection 笔记", async () => {
    const fetchMock = vi.fn((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/today")) return json({ date: "2026-08-01", current_goal: { id: 1, title: "真实目标" }, tasks: [], pending_count: 0, recent_course: null, recent_session: null });
      if (url.endsWith("/progress")) return json({ goal_count: 1, active_course_count: 0, knowledge_point_count: 0, completed_knowledge_point_count: 0, today_task_total: 0, today_task_completed: 0, sessions_last_7_days: 0, daily_sessions: [], recent_sessions: [] });
      if (url.includes("/mastery")) return json({ items: [], total: 0, page: 1, page_size: 100, pages: 0 });
      if (url.includes("/notes?") && (!init?.method || init.method === "GET")) return json({ items: [], total: 0, page: 1, page_size: 5, pages: 0 });
      if (url.endsWith("/notes") && init?.method === "POST") return json({ id: 1 }, 201);
      return json([]);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp(<GrowthReviewPage />, "/growth");
    await userEvent.type(await screen.findByLabelText("复盘完成情况"), "完成了真实任务");
    await userEvent.type(screen.getByLabelText("复盘下一步重点"), "继续整理笔记");
    await userEvent.click(screen.getByRole("button", { name: "保存复盘" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => {
      if (init?.method !== "POST") return false;
      const body = JSON.parse(String(init.body));
      return body.note_type === "reflection" && body.content_markdown.includes("完成了真实任务") && body.links[0].entity_type === "learning_goal";
    })).toBe(true));
  });
});
