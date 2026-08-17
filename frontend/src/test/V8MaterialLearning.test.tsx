import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { renderApp } from "./render";

const now = "2026-08-04T06:00:00Z";
const material = {
  id: 1, title: "MCP 指南", original_filename: "mcp.md", stored_filename: "stored.md", file_path: "hidden",
  source_type: "md", mime_type: "text/markdown", file_size: 128, processing_status: "completed",
  ingestion_status: "completed", indexing_status: "completed", chunk_count: 2, indexed_chunk_count: 2,
  processed_at: now, indexed_at: now, archived_at: null, error_message: null, deletion_status: "active",
  deletion_error: null, deletion_requested_at: null, deletion_attempts: 0, created_at: now, updated_at: now,
};
const goal = { id: 1, title: "学习 MCP", description: "", target_date: null, daily_minutes: 30, current_level: "", status: "active", is_demo: false, created_at: now, updated_at: now };
const course = { id: 2, learning_goal_id: 1, learning_goal_title: "学习 MCP", title: "MCP 基础", description: "", status: "active", knowledge_point_count: 1, created_at: now, updated_at: now };
const point = { id: 3, course_id: 2, title: "Tools", description: "", order_index: 1, estimated_minutes: 20, status: "learning", created_at: now, updated_at: now };

function json(data: unknown, status = 200) {
  return Promise.resolve(new Response(status === 204 ? null : JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } }));
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("V8 资料与学习结构联动", () => {
  it("知识收件箱显示待归类状态并通过确定性接口建立目标关联", async () => {
    vi.stubGlobal("fetch", vi.fn((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/materials?") || url.endsWith("/materials")) return json([material]);
      if (url.includes("/material-learning-links") && init?.method === "POST") {
        const body = JSON.parse(String(init.body));
        return json({ id: 9, material_id: 1, target_type: "learning_goal", target_id: 1, target_title: goal.title, relation_type: body.relation_type, is_primary: false, created_at: now, updated_at: now }, 201);
      }
      if (url.includes("/material-learning-links")) return json([]);
      if (url.endsWith("/learning-goals")) return json([goal]);
      if (url.endsWith("/courses")) return json([course]);
      return json([]);
    }));
    renderApp(<App />, "/inbox");
    expect(await screen.findByRole("heading", { name: "知识收件箱" })).toBeInTheDocument();
    expect(screen.getAllByText("待归类").length).toBeGreaterThan(0);
    await userEvent.click(screen.getByRole("button", { name: "归类" }));
    await userEvent.selectOptions(await screen.findByLabelText("关联对象"), "1");
    await userEvent.click(screen.getByRole("button", { name: "准备归类" }));
    await userEvent.click(screen.getByRole("button", { name: "确认归类" }));
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([url, init]) => {
      if (!String(url).endsWith("/materials/1/learning-links") || init?.method !== "POST") return false;
      const body = JSON.parse(String(init.body));
      return body.target_type === "learning_goal" && body.learning_goal_id === 1;
    })).toBe(true));
    expect(screen.queryByText(/GitHub 2小时前/)).not.toBeInTheDocument();
    expect(screen.queryByText(/飞书 2小时前/)).not.toBeInTheDocument();
  });

  it("知识点详情从有效资料搜索真实 chunk 并保存来源", async () => {
    vi.stubGlobal("fetch", vi.fn((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/knowledge-points/3") && !url.includes("sources")) return json(point);
      if (url.endsWith("/courses/2")) return json(course);
      if (url.endsWith("/knowledge-points/3/materials")) return json([{ material_id: 1, material_title: material.title, original_filename: material.original_filename, source_type: "md", processing_status: "completed", ingestion_status: "completed", indexing_status: "completed", deletion_status: "active", contexts: [{ id: 5, material_id: 1, material_title: material.title, original_filename: material.original_filename, source_type: "md", processing_status: "completed", ingestion_status: "completed", indexing_status: "completed", deletion_status: "active", target_type: "course", target_id: 2, target_title: course.title, relation_type: "reference", is_primary: false, visibility: "inherited", created_at: now, updated_at: now }] }]);
      if (url.includes("/knowledge-points/3/source-chunks")) return json({ items: [{ id: 11, material_id: 1, material_title: material.title, chunk_index: 0, content: "Tools 允许模型请求受控动作。", page_number: null, section_title: "Tools", source_locator: "Tools, chunk 1", previous_chunk_id: null, next_chunk_id: 12 }], total: 1, page: 1, page_size: 20, pages: 1 });
      if (url.endsWith("/knowledge-points/3/sources") && init?.method === "POST") return json({ id: 21 }, 201);
      if (url.endsWith("/knowledge-points/3/sources")) return json([]);
      if (url.includes("/notes?")) return json({ items: [], total: 0, page: 1, page_size: 100, pages: 0 });
      if (url.includes("/learning-activities")) return json({ items: [], total: 0, page: 1, page_size: 100, pages: 0 });
      return json([]);
    }));
    renderApp(<App />, "/knowledge-points/3");
    expect(await screen.findByRole("heading", { name: "Tools" })).toBeInTheDocument();
    expect(screen.getByText(/继承资料/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "从资料选择片段" }));
    await userEvent.selectOptions(await screen.findByLabelText("来源资料"), "1");
    await userEvent.click(await screen.findByRole("button", { name: /Tools, chunk 1/ }));
    await userEvent.click(screen.getByRole("button", { name: "添加来源" }));
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([url, init]) => String(url).endsWith("/knowledge-points/3/sources") && init?.method === "POST" && JSON.parse(String(init.body)).material_chunk_id === 11)).toBe(true));
  });

  it("资料问答把课程范围传给真实 SSE 请求", async () => {
    const conversation = { id: 7, title: "课程问答", status: "active", default_top_k: null, last_message_at: now, created_at: now, updated_at: now };
    vi.stubGlobal("fetch", vi.fn((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/rag/status")) return json({ llm_configured: true, provider: "test", model: "test", index_available: true, index_stale: false, index_version: "v8", rag_prompt_version: "v8", rewrite_prompt_version: "v8" });
      if (url.endsWith("/rag/conversations/7/stream")) {
        const body = JSON.parse(String(init?.body));
        expect(body.course_id).toBe(2);
        expect(body.material_ids).toBeNull();
        const encoder = new TextEncoder();
        return Promise.resolve(new Response(new ReadableStream({ start(controller) { controller.enqueue(encoder.encode('event: answer.completed\ndata: {"message_id":8,"text":"课程范围回答"}\n\nevent: run.completed\ndata: {"message_id":8}\n\n')); controller.close(); } }), { status: 200, headers: { "Content-Type": "text/event-stream" } }));
      }
      if (url.includes("/rag/conversations/7")) return json({ ...conversation, messages: [], message_total: 0, message_page: 1, message_page_size: 100, message_pages: 0 });
      if (url.includes("/rag/conversations")) return json({ items: [conversation], total: 1, page: 1, page_size: 100, pages: 1 });
      if (url.endsWith("/courses")) return json([course]);
      if (url.includes("/courses/2/knowledge-points")) return json([point]);
      if (url.endsWith("/learning-goals")) return json([goal]);
      if (url.includes("/materials")) return json([material]);
      if (url.includes("/notes?")) return json({ items: [], total: 0, page: 1, page_size: 100, pages: 0 });
      return json([]);
    }));
    renderApp(<App />, "/knowledge?tab=qa&scope=course&course_id=2");
    expect(await screen.findByRole("heading", { name: "资料问答" })).toBeInTheDocument();
    expect(screen.getByLabelText("选择检索路线")).toHaveValue("2");
    await userEvent.type(screen.getByLabelText("向资料提问"), "课程范围问题");
    await userEvent.click(screen.getByRole("button", { name: "发送" }));
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).endsWith("/rag/conversations/7/stream"))).toBe(true));
  });
});
