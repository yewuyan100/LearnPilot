import { cleanup, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { renderApp } from "./render";

const now = "2026-08-01T08:00:00Z";
const conversation = { id: 1, title: "V5 学习助手", status: "active", thread_id: "thread-1", last_message_at: now, created_at: now, updated_at: now };

describe("V5 学习助手", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn((input: string | URL) => {
      const url = String(input);
      const body = url.endsWith("/agent/conversations/1")
        ? { ...conversation, messages: [{ id: 1, role: "assistant", content: "查询可以直接执行，写入需要确认。", citations: [], run_id: 1, created_at: now }] }
        : [conversation];
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }));
    }));
  });

  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it("显示三栏工作区、安全说明和会话消息", async () => {
    renderApp(<App />, "/agent");
    expect(await screen.findByRole("heading", { name: "学习助手" })).toBeInTheDocument();
    expect(await screen.findByText("查询可以直接执行，写入需要确认。")).toBeInTheDocument();
    expect(screen.getByLabelText("助手会话")).toBeInTheDocument();
    expect(screen.getByLabelText("运行详情")).toHaveTextContent("最多 4 步、只允许 1 次写入");
    expect(screen.getByRole("link", { name: "学习助手" })).toBeInTheDocument();
  });
});
