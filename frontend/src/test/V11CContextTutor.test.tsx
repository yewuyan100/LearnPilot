import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { renderApp } from "./render";

const now = "2026-08-07T08:00:00Z";
const session = {
  id: 17,
  learning_goal_id: 1,
  course_id: 2,
  knowledge_point_id: 3,
  daily_task_id: 8,
  started_at: now,
  ended_at: null,
  status: "active",
  notes: "",
  invalidated_at: null,
  invalidation_reason: null,
  goal_title: "学习 MCP",
  course_title: "MCP 可靠性",
  knowledge_point_title: "受控调用",
  task_title: "理解受控调用",
  created_at: now,
  updated_at: now,
};
const point = {
  id: 3,
  course_id: 2,
  title: "受控调用",
  description: "理解调用边界",
  order_index: 1,
  estimated_minutes: 20,
  status: "learning",
  lifecycle_status: "active",
  version: 1,
  superseded_by_id: null,
  created_at: now,
  updated_at: now,
};

function json(data: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(data), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("V11C LearningSession 情境化辅导", () => {
  it("自动提交学习位置并展示教学回答、引用和理解检查", async () => {
    vi.stubGlobal("fetch", vi.fn((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/learning-sessions/17")) return json(session);
      if (url.endsWith("/courses/2/knowledge-points")) return json([point]);
      if (url.endsWith("/agent/conversations") && init?.method === "POST") {
        return json({ id: 9, title: "学习会话辅导", status: "active", thread_id: "tutor-9", last_message_at: null, created_at: now, updated_at: now }, 201);
      }
      if (url.endsWith("/learning/runtime/runs") && init?.method === "POST") {
        return json({
          run_id: "run-v11c-1",
          status: "completed",
          selected_agent: "tutor",
          answer: "**当前学习位置：MCP 可靠性 / 受控调用**\n\n边界用于限制可执行范围。[S1]",
          proposal: null,
          confirmation: null,
          citations: [],
          tutor_answer: {
            answer_markdown: "**当前学习位置：MCP 可靠性 / 受控调用**\n\n边界用于限制可执行范围。[S1]",
            teaching_mode: "explanation",
            citations: [{ source_label: "S1", material_id: 5, chunk_id: 6, original_filename: "reliability.md", page_number: 2, section_title: null, content_excerpt: "受控调用必须处于声明的边界内。", score: 0.96 }],
            context_references: [{ kind: "knowledge_point", id: 3, title: "受控调用" }],
            follow_up_check: "你能说出边界限制的对象吗？",
            limitations: [],
          },
          context_version: "a".repeat(64),
          warnings: [],
        }, 202);
      }
      return json([]);
    }));

    renderApp(<App />, "/learning-sessions/17");
    const input = await screen.findByLabelText("向当前知识点的学习导师提问");
    await userEvent.type(input, "为什么需要受控边界？");
    await userEvent.click(screen.getByRole("button", { name: "提问" }));

    expect(await screen.findByText("边界用于限制可执行范围。[S1]")).toBeInTheDocument();
    expect(screen.getByText("reliability.md")).toBeInTheDocument();
    expect(screen.getByText(/你能说出边界限制的对象吗/)).toBeInTheDocument();
    const call = vi.mocked(fetch).mock.calls.find(([url]) => String(url).endsWith("/learning/runtime/runs"));
    const body = JSON.parse(String(call?.[1]?.body));
    expect(body.channel).toBe("learning_session");
    expect(body.surface_context).toMatchObject({
      goal_id: 1,
      course_id: 2,
      knowledge_point_id: 3,
      learning_session_id: 17,
      source_path: "/learning-sessions/17",
    });
  });

  it("上下文不匹配时要求重新选择学习位置", async () => {
    vi.stubGlobal("fetch", vi.fn((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/learning-sessions/17")) return json(session);
      if (url.endsWith("/courses/2/knowledge-points")) return json([point]);
      if (url.endsWith("/agent/conversations") && init?.method === "POST") {
        return json({ id: 9, title: "学习会话辅导", status: "active", thread_id: "tutor-9", last_message_at: null, created_at: now, updated_at: now }, 201);
      }
      if (url.endsWith("/learning/runtime/runs")) {
        return json({ error: { code: "context_mismatch", message: "context changed" } }, 409);
      }
      return json([]);
    }));

    renderApp(<App />, "/learning-sessions/17");
    const input = await screen.findByLabelText("向当前知识点的学习导师提问");
    await userEvent.type(input, "为什么这样设计？");
    await userEvent.click(screen.getByRole("button", { name: "提问" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("当前学习内容已变化，请重新选择学习位置。");
  });
});
