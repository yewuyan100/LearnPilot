import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { renderApp } from "./render";

const now = "2026-08-01T08:00:00Z";
const masteryItem = {
  knowledge_point_id: 7, knowledge_point_title: "LangGraph Checkpoint",
  course_id: 2, course_title: "Agent 工程", mastery_score: 45,
  confidence_score: 32, mastery_level: "developing", evidence_count: 4,
  active_wrong_answers: 2, last_practiced_at: now, next_review_at: "2026-08-02T00:00:00Z",
};
const review = {
  id: 4, knowledge_point_id: 7, knowledge_point_title: "LangGraph Checkpoint",
  status: "pending", priority_score: 82, recommended_at: now,
  due_at: "2026-07-31T00:00:00Z", overdue: true, reason_code: "review_overdue",
  reason_summary: "存在 2 条未解决错题，建议尽快复习。", completed_task_id: null,
};
const recommendation = {
  id: 9, knowledge_point_id: 7, recommendation_type: "review_task", status: "pending",
  priority: "high", title: "复习：LangGraph Checkpoint", reason_code: "wrong_answer_due",
  reason_details: { reason_summary: "存在 2 条未解决错题，建议尽快复习。" },
  suggested_date: "2026-08-02", suggested_minutes: 30, created_task_id: null,
};

function response(data: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } }));
}

describe("V6 掌握度与自适应复习", () => {
  beforeEach(() => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.stubGlobal("fetch", vi.fn((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/mastery?page")) return response({ items: [masteryItem, { ...masteryItem, knowledge_point_id: 8, knowledge_point_title: "首次测评", mastery_score: null, confidence_score: 0, mastery_level: "unassessed", evidence_count: 0, active_wrong_answers: 0, last_practiced_at: null, next_review_at: null }], total: 2, page: 1, page_size: 100, pages: 1 });
      if (url.includes("/mastery/weak-points")) return response([{ ...masteryItem, classification: "weak", weakness_score: 78, recent_failure: true, overdue: true, review_status: "pending" }]);
      if (url.endsWith("/mastery/7")) return response({ ...masteryItem, algorithm_version: "mastery-rule-v1", calculated_at: now, evidence_summary: { category_scores: { objective_quiz: 40, task_completion: 70 } }, evidence: [{ id: 1, evidence_type: "objective_quiz", source_type: "quiz_answer", source_id: "11", occurred_at: now, normalized_score: 40, weight: .4, metadata: { question_type: "single_choice" } }], snapshots: [{ id: 1, mastery_score: 45, confidence_score: 32, mastery_level: "developing", evidence_count: 4, trigger_type: "quiz_completed", calculated_at: now }], review_schedule: review, recommendation });
      if (url.endsWith("/reviews?limit=200")) return response([review]);
      if (url.includes("/adaptive-recommendations?")) return response([recommendation]);
      if (url.endsWith("/adaptive-recommendations/9/accept") && init?.method === "POST") return response({ recommendation: { ...recommendation, status: "executed", created_task_id: 33 }, task: { id: 33 }, idempotent_replay: false });
      if (url.endsWith("/adaptive-recommendations/9/reject") && init?.method === "POST") return response({ ...recommendation, status: "rejected" });
      return response([]);
    }));
  });

  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it("区分掌握度、置信度和未评估状态", async () => {
    renderApp(<App />, "/mastery");
    expect(await screen.findByRole("heading", { name: "掌握度" })).toBeInTheDocument();
    expect(screen.getByText("LangGraph Checkpoint")).toBeInTheDocument();
    expect(screen.getAllByText("未评估").length).toBeGreaterThan(0);
    expect(screen.getByText("4 条 · 2 条错题")).toBeInTheDocument();
  });

  it("显示证据组成、历史和复习原因且隐藏内部字段", async () => {
    renderApp(<App />, "/mastery/7");
    expect(await screen.findByRole("heading", { name: "LangGraph Checkpoint" })).toBeInTheDocument();
    expect(screen.queryByText(/mastery-rule-v1/)).not.toBeInTheDocument();
    expect(screen.queryByText(/quiz_completed/)).not.toBeInTheDocument();
    expect(screen.queryByText(/quiz_answer/)).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "证据组成" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "掌握度历史" })).toBeInTheDocument();
    expect(screen.getByText("存在 2 条未解决错题，建议尽快复习。")).toBeInTheDocument();
    expect(screen.getByText(/不代表正式教育测评结果/)).toBeInTheDocument();
  });

  it("按逾期分组并在确认后创建真实任务", async () => {
    renderApp(<App />, "/reviews");
    expect(await screen.findByRole("heading", { name: "复习计划" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "待确认建议" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "已逾期" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /创建任务/ }));
    await waitFor(() => expect(window.confirm).toHaveBeenCalled());
    await waitFor(() => expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/adaptive-recommendations/9/accept"), expect.objectContaining({ method: "POST" })));
  });

  it("允许拒绝建议且不触发接受接口", async () => {
    renderApp(<App />, "/reviews");
    await userEvent.click(await screen.findByRole("button", { name: /忽略/ }));
    await waitFor(() => expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/adaptive-recommendations/9/reject"), expect.objectContaining({ method: "POST" })));
    const calls = vi.mocked(fetch).mock.calls.map(([input]) => String(input));
    expect(calls.some((url) => url.endsWith("/adaptive-recommendations/9/accept"))).toBe(false);
  });
});
