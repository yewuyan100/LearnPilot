import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { renderApp } from "./render";

const now = "2026-08-04T08:00:00Z";
const goal = { id: 1, title: "掌握 MCP", description: "", target_date: null, daily_minutes: 30, current_level: "", status: "active", is_demo: false, created_at: now, updated_at: now };
const material = { id: 2, title: "MCP 指南", original_filename: "mcp.md", stored_filename: "stored.md", file_path: "hidden", source_type: "md", mime_type: "text/markdown", file_size: 100, processing_status: "ready", ingestion_status: "completed", indexing_status: "completed", chunk_count: 3, indexed_chunk_count: 3, processed_at: now, indexed_at: now, archived_at: null, error_message: null, deletion_status: "active", deletion_error: null, deletion_requested_at: null, deletion_attempts: 0, created_at: now, updated_at: now };
const source = { id: 8, draft_knowledge_point_id: 7, material_id: 2, material_title: "MCP 指南", material_chunk_id: 20, chunk_index: 0, source_locator: "第 1 页", quoted_text: "真实片段", source_role: "primary", relevance_score: null, origin: "manual", context_url: "/materials/2?chunk=20", created_at: now, updated_at: now };
const baseDraft = {
  id: 4, public_id: "draft-4", learning_goal_id: 1, learning_goal_title: goal.title,
  title: "MCP 课程架构", description: "从资料整理", status: "review_required", generation_status: "completed", version: 6,
  source_snapshot_version: 1, generation_mode: "structured_llm", model_name: "configured-model", prompt_version: "course-architecture-v1",
  generation_progress: { stage: "draft.ready", completed_batches: 2, total_batches: 2, events: [{ event: "draft.ready", message: "草案已准备好，请检查后发布" }] },
  last_error_code: null, last_error_message: null, quality_status: "blocked",
  quality_report: { status: "blocked", blocker_count: 1, warning_count: 0, info_count: 0, source_coverage: 50, issues: [{ code: "knowledge_point_without_source", severity: "blocker", message: "知识点尚未关联真实资料片段。", course_id: 5, knowledge_point_id: 7 }] },
  publish_request_id: null, published_at: null, archived_at: null, created_at: now, updated_at: now,
  materials: [{ id: 3, draft_id: 4, material_id: 2, material_title: material.title, original_filename: material.original_filename, order_index: 0, material_updated_at_snapshot: now, chunk_count_snapshot: 3, index_state_snapshot: "completed", current_chunk_count: 3, current_indexing_status: "completed", stale: false, created_at: now, updated_at: now }],
  courses: [{ id: 5, draft_id: 4, title: "MCP 基础", description: "协议基础", order_index: 0, learning_outcomes: [], origin: "generated", is_locked: false, user_modified: false, published_course_id: null, created_at: now, updated_at: now, knowledge_points: [{ id: 7, draft_course_id: 5, title: "Tools", description: "工具边界", order_index: 0, learning_objectives: [], key_terms: [], granularity_label: null, difficulty_label: "beginner", origin: "generated", is_locked: false, user_modified: false, source_status: "missing", validation_status: "unchecked", published_knowledge_point_id: null, sources: [], created_at: now, updated_at: now }, { id: 9, draft_course_id: 5, title: "Resources", description: "资源边界", order_index: 1, learning_objectives: [], key_terms: [], granularity_label: null, difficulty_label: "beginner", origin: "generated", is_locked: false, user_modified: false, source_status: "valid", validation_status: "valid", published_knowledge_point_id: null, sources: [source], created_at: now, updated_at: now }] }],
  prerequisites: [{ id: 10, draft_id: 4, prerequisite_knowledge_point_id: 7, prerequisite_title: "Tools", dependent_knowledge_point_id: 9, dependent_title: "Resources", rationale: "学习顺序", confidence: 0.8, origin: "generated", validation_status: "valid", created_at: now, updated_at: now }],
};

function json(data: unknown, status = 200) { return Promise.resolve(new Response(status === 204 ? null : JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } })); }

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("V9 课程架构草案", () => {
  it("在课程内切换草案并只允许选择真实可用资料", async () => {
    const unavailable = { ...material, id: 3, title: "未处理资料", ingestion_status: "pending", indexing_status: "pending", chunk_count: 0 };
    vi.stubGlobal("fetch", vi.fn((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/course-architecture/drafts?") && !init?.method) return json({ items: [], total: 0 });
      if (url.endsWith("/course-architecture/drafts") && init?.method === "POST") return json(baseDraft, 201);
      if (url.endsWith("/course-architecture/drafts/4")) return json(baseDraft);
      if (url.endsWith("/learning-goals")) return json([goal]);
      if (url.includes("/materials?")) return json([material, unavailable]);
      return json([]);
    }));
    renderApp(<App />, "/course-architecture/drafts");
    expect(await screen.findByRole("heading", { name: "课程草案" })).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole("button", { name: "新建课程架构" })[0]);
    expect(screen.getByText(/暂不可用：需要完成处理/)).toBeInTheDocument();
    const options = screen.getAllByRole("checkbox");
    expect(options[1]).toBeDisabled();
    await userEvent.click(options[0]);
    await userEvent.click(screen.getByRole("button", { name: "创建草案" }));
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([url, init]) => {
      if (!String(url).endsWith("/course-architecture/drafts") || init?.method !== "POST") return false;
      return JSON.parse(String(init.body)).material_ids[0] === 2;
    })).toBe(true));
    expect(await screen.findByRole("heading", { name: "MCP 课程架构" })).toBeInTheDocument();
  });

  it("展示真实来源、质量阻塞和前置关系，并可添加片段来源", async () => {
    const withSource = { ...baseDraft, version: 7, courses: [{ ...baseDraft.courses[0], knowledge_points: [{ ...baseDraft.courses[0].knowledge_points[0], sources: [source], source_status: "valid" }, baseDraft.courses[0].knowledge_points[1]] }] };
    vi.stubGlobal("fetch", vi.fn((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/course-architecture/drafts/4") && !init?.method) return json(baseDraft);
      if (url.includes("/materials/2/chunks")) return json({ items: [{ id: 20, material_id: 2, chunk_index: 0, content: "Tools 是模型可请求的受控动作。", char_count: 20, content_hash: "h", page_number: 1, section_title: "Tools", created_at: now, updated_at: now }], total: 1, page: 1, page_size: 20, pages: 1 });
      if (url.endsWith("/knowledge-points/7/sources") && init?.method === "POST") return json(withSource);
      return json([]);
    }));
    renderApp(<App />, "/course-architecture/drafts/4");
    expect(await screen.findByRole("heading", { name: "MCP 课程架构" })).toBeInTheDocument();
    expect(screen.getByText("1 个阻塞")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "确认发布" })).toBeDisabled();
    expect(screen.getAllByText("Tools").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Resources").length).toBeGreaterThan(0);
    await userEvent.click(await screen.findByRole("button", { name: "添加来源" }));
    await userEvent.selectOptions(await screen.findByLabelText("选择来源片段"), "20");
    await userEvent.click(screen.getAllByRole("button", { name: "添加来源" }).at(-1)!);
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([url, init]) => String(url).endsWith("/knowledge-points/7/sources") && init?.method === "POST" && JSON.parse(String(init.body)).material_chunk_id === 20)).toBe(true));
    expect(await screen.findByText("真实片段")).toBeInTheDocument();
    expect(screen.queryByText(/Tool Call|Planner|Raw JSON|Node/)).not.toBeInTheDocument();
  });

  it("质量通过后显示完整发布确认并提交显式确认", async () => {
    const ready = { ...baseDraft, status: "ready", quality_status: "ready", quality_report: { status: "ready", blocker_count: 0, warning_count: 0, info_count: 1, source_coverage: 100, issues: [] }, courses: [{ ...baseDraft.courses[0], knowledge_points: baseDraft.courses[0].knowledge_points.map((point) => ({ ...point, sources: [source], source_status: "valid" })) }] };
    vi.stubGlobal("fetch", vi.fn((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/course-architecture/drafts/4") && !init?.method) return json(ready);
      if (url.endsWith("/course-architecture/drafts/4/publish") && init?.method === "POST") return json({ draft_id: 4, publish_request_id: "p", course_ids: [12], knowledge_point_ids: [13, 14], material_link_count: 1, source_count: 2, prerequisite_count: 1, published_at: now });
      return json([]);
    }));
    renderApp(<App />, "/course-architecture/drafts/4");
    await userEvent.click(await screen.findByRole("button", { name: "确认发布" }));
    expect(screen.getByText(/失败不会留下半套课程/)).toBeInTheDocument();
    expect(screen.getAllByText("2", { selector: "dd" }).length).toBeGreaterThan(0);
    await userEvent.click(screen.getAllByRole("button", { name: "确认发布" }).at(-1)!);
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([url, init]) => {
      if (!String(url).endsWith("/course-architecture/drafts/4/publish")) return false;
      return JSON.parse(String(init?.body)).confirmed === true;
    })).toBe(true));
    expect(await screen.findByText(/发布完成/)).toBeInTheDocument();
    expect(document.querySelector("[class*='avatar']")).toBeNull();
  });

  it("生成失败时说明原因并允许从同一草案重试", async () => {
    const failed = {
      ...baseDraft,
      status: "failed",
      generation_status: "failed",
      last_error_message: "模型生成失败，可稍后重试或手动编辑草案",
      courses: [],
      prerequisites: [],
    };
    const regenerated = { ...baseDraft, version: 7, status: "review_required", generation_status: "completed" };
    vi.stubGlobal("fetch", vi.fn((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/course-architecture/drafts/4") && !init?.method) return json(failed);
      if (url.endsWith("/course-architecture/drafts/4/generate") && init?.method === "POST") return json(regenerated);
      return json([]);
    }));

    renderApp(<App />, "/course-architecture/drafts/4");
    expect(await screen.findByText("模型生成失败，可稍后重试或手动编辑草案")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "重新生成" }));
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([url, init]) =>
      String(url).endsWith("/course-architecture/drafts/4/generate") && init?.method === "POST"
    )).toBe(true));
    expect((await screen.findAllByText("MCP 基础")).length).toBeGreaterThan(0);
  });

  it("生成进行中允许请求停止且不显示第二个分析入口", async () => {
    const running = {
      ...baseDraft,
      status: "generating",
      generation_status: "running",
      generation_progress: { stage: "analysis.started", completed_batches: 0, total_batches: 2, events: [] },
    };
    const cancelled = {
      ...running,
      version: running.version + 1,
      status: "review_required",
      generation_status: "cancelled",
    };
    vi.stubGlobal("fetch", vi.fn((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/course-architecture/drafts/4") && !init?.method) return json(running);
      if (url.endsWith("/course-architecture/drafts/4/generate/cancel") && init?.method === "POST") return json(cancelled);
      return json([]);
    }));

    renderApp(<App />, "/course-architecture/drafts/4");
    expect(await screen.findByRole("button", { name: "停止分析" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "分析资料" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "停止分析" }));
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([url, init]) =>
      String(url).endsWith("/course-architecture/drafts/4/generate/cancel") && init?.method === "POST"
    )).toBe(true));
  });
});
