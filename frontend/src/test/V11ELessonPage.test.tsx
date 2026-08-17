import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { renderApp } from "./render";

const now = "2026-08-07T08:00:00Z";
const version = {
  id: 41,
  lesson_id: 4,
  version_number: 2,
  status: "published",
  objectives: ["理解受控调用边界", "能够判断来源是否属于本课"],
  content_markdown: "# 核心讲解\n\n核心讲解内容。[S1]\n\n## 常见错误\n\n- 跨课程补取资料",
  examples: [{ title: "受控调用示例", explanation_markdown: "先确认边界，再执行调用。[S1]" }],
  guided_practice: [{ prompt: "判断当前资料是否属于课节范围。", hint: "查看来源快照。", expected_approach: "比对材料 ID。" }],
  checks: [{ prompt: "为什么不能跨课取资料？", check_type: "short_answer", options: [], expected_concepts: ["边界"] }],
  estimated_minutes: 25,
  source_snapshot_hash: "a".repeat(64),
  generation_request_id: "v11e-ui-version-2",
  model_name: "lesson-model",
  prompt_version: "v11e.lesson-generation.1",
  quality_report: { valid: true },
  published_at: now,
  created_at: now,
  updated_at: now,
  knowledge_points: [{ knowledge_point_id: 3, title: "受控调用", order_index: 1, role: "primary" }],
  sources: [{ material_id: 5, material_title: "可靠性手册", material_chunk_id: 6, source_role: "primary", source_locator: "chunk:0;section:边界", quoted_text: "受控调用必须处于声明的边界内。" }],
};
const lesson = {
  id: 4,
  public_id: "lesson-4",
  course_id: 2,
  course_title: "MCP 可靠性",
  learning_goal_id: 1,
  title: "在边界内完成受控调用",
  description: "从目标到讲解、示例、练习与理解检查的完整课节。",
  order_index: 1,
  status: "published",
  current_version_number: 2,
  active_version_number: 2,
  latest_version: version,
  active_version: version,
  idempotent_replay: false,
  created_at: now,
  updated_at: now,
};
const session = {
  id: 17,
  learning_goal_id: 1,
  course_id: 2,
  knowledge_point_id: 3,
  daily_task_id: 8,
  lesson_version_id: 41,
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
  lesson_id: 4,
  lesson_title: lesson.title,
  lesson_version_number: 2,
  created_at: now,
  updated_at: now,
};

function json(data: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  }));
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("V11E Lesson 学习页", () => {
  it("展示完整教学结构，并把课节版本、知识点和会话交给 Tutor", async () => {
    vi.stubGlobal("fetch", vi.fn((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/lessons/4")) return json(lesson);
      if (url.endsWith("/learning-sessions/17") && init?.method === "PATCH") {
        return json({ ...session, status: "completed", ended_at: now });
      }
      if (url.endsWith("/learning-sessions/17")) return json(session);
      if (url.endsWith("/agent/conversations") && init?.method === "POST") {
        return json({ id: 9, title: "课节辅导", status: "active", thread_id: "lesson-tutor-9", last_message_at: null, created_at: now, updated_at: now }, 201);
      }
      if (url.endsWith("/learning/runtime/runs") && init?.method === "POST") {
        return json({
          run_id: "run-v11e-ui-1",
          status: "completed",
          selected_agent: "tutor",
          answer: "本课目标先限定了调用边界。[S1]",
          proposal: null,
          confirmation: null,
          citations: [],
          tutor_answer: {
            answer_markdown: "本课目标先限定了调用边界。[S1]",
            teaching_mode: "worked_example",
            citations: [{ source_label: "S1", material_id: 5, chunk_id: 6, original_filename: "reliability.md", page_number: null, section_title: "边界", content_excerpt: "受控调用必须处于声明的边界内。", score: 0.97 }],
            context_references: [{ kind: "lesson_version", id: 41, title: "在边界内完成受控调用 · v2" }],
            follow_up_check: "这个示例支持哪个学习目标？",
            limitations: [],
          },
          context_version: "b".repeat(64),
          warnings: [],
        }, 202);
      }
      return json([]);
    }));

    renderApp(<App />, "/lessons/4?session=17");
    expect(await screen.findByRole("heading", { name: lesson.title })).toBeInTheDocument();
    expect(screen.getByText("理解受控调用边界")).toBeInTheDocument();
    expect(screen.getByText("核心讲解内容。[S1]")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "受控调用示例" })).toBeInTheDocument();
    expect(screen.getByText("可靠性手册")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "开始检查" }));
    expect(screen.getByText("为什么不能跨课取资料？")).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("向本课学习导师提问"), "为什么要先看边界？");
    await userEvent.click(screen.getByRole("button", { name: "提问" }));
    expect(await screen.findByText("本课目标先限定了调用边界。[S1]")).toBeInTheDocument();
    const runtimeCall = vi.mocked(fetch).mock.calls.find(([url]) => String(url).endsWith("/learning/runtime/runs"));
    const runtimeBody = JSON.parse(String(runtimeCall?.[1]?.body));
    expect(runtimeBody.surface_context).toMatchObject({
      goal_id: 1,
      course_id: 2,
      knowledge_point_id: 3,
      lesson_id: 4,
      lesson_version_id: 41,
      learning_session_id: 17,
      source_path: "/lessons/4?session=17",
    });

    await userEvent.click(screen.getByRole("button", { name: "完成课节" }));
    await waitFor(() => {
      const completeCall = vi.mocked(fetch).mock.calls.find(([url, init]) =>
        String(url).endsWith("/learning-sessions/17") && init?.method === "PATCH");
      expect(JSON.parse(String(completeCall?.[1]?.body))).toMatchObject({
        status: "completed",
        knowledge_point_status: "completed",
        daily_task_status: "completed",
      });
    });
  });

  it("没有会话时以精确发布版本开始本课", async () => {
    vi.stubGlobal("fetch", vi.fn((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/lessons/4")) return json(lesson);
      if (url.endsWith("/learning-sessions") && init?.method === "POST") {
        return json({ ...session, id: 18, daily_task_id: null }, 201);
      }
      if (url.endsWith("/learning-sessions/18")) return json({ ...session, id: 18, daily_task_id: null });
      return json([]);
    }));

    renderApp(<App />, "/lessons/4");
    await userEvent.click(await screen.findByRole("button", { name: "开始本课" }));
    await waitFor(() => {
      const startCall = vi.mocked(fetch).mock.calls.find(([url, init]) =>
        String(url).endsWith("/learning-sessions") && init?.method === "POST");
      expect(JSON.parse(String(startCall?.[1]?.body))).toEqual({
        learning_goal_id: 1,
        course_id: 2,
        knowledge_point_id: 3,
        lesson_version_id: 41,
      });
    });
    expect(await screen.findByRole("button", { name: "完成课节" })).toBeInTheDocument();
  });
});
