import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { renderApp } from "./render";

const now = "2026-07-30T10:00:00Z";
const conversation = {
  id: 1,
  title: "MCP 资料问答",
  status: "active",
  default_top_k: null,
  last_message_at: now,
  created_at: now,
  updated_at: now,
};
const citation = {
  id: 1,
  source_label: "S1",
  chunk_id: 2,
  material_id: 3,
  rank: 1,
  score: 0.88,
  original_filename: "mcp.md",
  chunk_index: 0,
  page_number: null,
  section_title: "Tools",
  content_excerpt: "Tools 允许模型请求受控动作。",
  source_available: true,
  created_at: now,
};
const detail = {
  ...conversation,
  message_total: 2,
  message_page: 1,
  message_page_size: 100,
  message_pages: 1,
  messages: [
    {
      id: 1,
      conversation_id: 1,
      reply_to_message_id: null,
      role: "user",
      content: "Tools 做什么？",
      status: "completed",
      request_id: null,
      original_query: "Tools 做什么？",
      retrieval_query: null,
      answerable: null,
      refusal_reason: null,
      prompt_version: null,
      model_name: null,
      latency_ms: null,
      citations: [],
      created_at: now,
      updated_at: now,
    },
    {
      id: 2,
      conversation_id: 1,
      reply_to_message_id: 1,
      role: "assistant",
      content: "Tools 允许模型请求动作。[S1]",
      status: "completed",
      request_id: "request-1",
      original_query: "Tools 做什么？",
      retrieval_query: "MCP Tools",
      answerable: true,
      refusal_reason: null,
      prompt_version: "rag-answer-v1",
      model_name: "fake",
      latency_ms: 12,
      citations: [citation],
      created_at: now,
      updated_at: now,
    },
  ],
};

function json(data: unknown, status = 200) {
  return Promise.resolve(
    new Response(status === 204 ? null : JSON.stringify(data), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

describe("可信资料问答页面", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/notes") && init?.method === "POST") {
        const body = JSON.parse(String(init.body));
        return json({ id: 9, ...body, status: "active", archived_at: null, tags: [], links: [], sources: [], created_at: now, updated_at: now }, 201);
      }
      if (url.includes("/notes?")) return json({ items: [], total: 0, page: 1, page_size: 100, pages: 0 });
      if (url.endsWith("/rag/status")) {
        return json({
          llm_configured: true,
          provider: "openai_compatible",
          model: "fake",
          index_available: true,
          index_stale: false,
          index_version: "v1",
          rag_prompt_version: "rag-answer-v1",
          rewrite_prompt_version: "rag-rewrite-v1",
        });
      }
      if (url.includes("/rag/conversations/1")) return json(detail);
      if (url.includes("/rag/conversations")) {
        return json({ items: [conversation], total: 1, page: 1, page_size: 100, pages: 1 });
      }
      if (url.includes("/materials")) return json([]);
      return json([]);
    }));
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("加载会话、答案和可交互引用", async () => {
    renderApp(<App />, "/rag");
    expect(await screen.findByRole("heading", { name: "资料问答" })).toBeInTheDocument();
    expect(await screen.findByText("Tools 允许模型请求动作。", { exact: false })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "S1" }));
    expect(screen.getByText("mcp.md")).toBeInTheDocument();
    expect(screen.getByText("Tools 允许模型请求受控动作。")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "只保存引用为新笔记" }));
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([, init]) => {
      if (init?.method !== "POST") return false;
      const body = JSON.parse(String(init.body));
      return body.note_type === "material" && body.sources?.[0]?.chunk_id === 2;
    })).toBe(true));
    await userEvent.click(screen.getByRole("button", { name: "保存回答到新笔记" }));
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([, init]) => {
      if (init?.method !== "POST") return false;
      const body = JSON.parse(String(init.body));
      return body.links?.[0]?.entity_type === "rag_message";
    })).toBe(true));
    expect(screen.getAllByRole("link", { name: "知识库" }).length).toBeGreaterThan(0);
  });

  it("显示 SSE 完整答案事件且不依赖伪造 token", async () => {
    let closeStream: (() => void) | undefined;
    vi.stubGlobal("fetch", vi.fn((input: string | URL) => {
      const url = String(input);
      if (url.endsWith("/rag/status")) {
        return json({
          llm_configured: true,
          provider: "openai_compatible",
          model: "fake",
          index_available: true,
          index_stale: false,
          index_version: "v1",
          rag_prompt_version: "rag-answer-v1",
          rewrite_prompt_version: "rag-rewrite-v1",
        });
      }
      if (url.endsWith("/rag/conversations/1/stream")) {
        const encoder = new TextEncoder();
        const stream = new ReadableStream({
          start(controller) {
            controller.enqueue(encoder.encode('event: run.started\ndata: {"request_id":"x"}\n\n'));
            controller.enqueue(encoder.encode('event: retrieval.completed\ndata: {"source_count":1}\n\n'));
            controller.enqueue(encoder.encode('event: answer.completed\ndata: {"message_id":3,"text":"已校验的完整回答"}\n\n'));
            closeStream = () => controller.close();
          },
        });
        return Promise.resolve(
          new Response(stream, { status: 200, headers: { "Content-Type": "text/event-stream" } }),
        );
      }
      if (url.includes("/rag/conversations/1")) {
        return json({ ...detail, message_total: 0, messages: [] });
      }
      if (url.includes("/rag/conversations")) {
        return json({ items: [conversation], total: 1, page: 1, page_size: 100, pages: 1 });
      }
      if (url.includes("/materials")) return json([]);
      return json([]);
    }));

    renderApp(<App />, "/rag");
    const input = await screen.findByLabelText("向资料提问");
    await userEvent.type(input, "请解释 Tools");
    await userEvent.click(screen.getByRole("button", { name: "发送" }));
    expect(await screen.findByText("已校验的完整回答")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "停止" })).toBeInTheDocument();
    closeStream?.();
    await waitFor(() => expect(screen.queryByRole("button", { name: "停止" })).not.toBeInTheDocument());
  });
});
