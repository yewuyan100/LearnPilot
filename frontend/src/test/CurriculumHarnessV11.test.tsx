import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import type { CurriculumProposal } from "../types";
import { renderApp } from "./render";

const now = "2026-08-07T08:00:00Z";
const goal = { id: 1, title: "7 天学习 LangGraph", description: "能够构建带恢复能力的状态图", target_date: "2026-08-14", daily_minutes: 45, current_level: "会 Python", status: "active", is_demo: false, created_at: now, updated_at: now };
const curriculum = {
  proposal_id: "proposal-v11d-1",
  proposal_type: "curriculum",
  status: "review_required",
  version: 1,
  context_version: "a".repeat(64),
  generation_request_id: "v11d-ui-generate-1",
  goal,
  grounding_mode: "goal_only",
  material_ids: [],
  curriculum: {
    course_title: "LangGraph 七天核心路径",
    course_description: "从 State 与 Reducer 到 Checkpoint。",
    knowledge_points: [
      { title: "State 与 Reducer", description: "理解共享状态聚合。", learning_objectives: ["说明 reducer 边界"], key_terms: ["State", "Reducer"], difficulty_label: "beginner", source_chunk_ids: [] },
      { title: "Checkpoint", description: "理解恢复边界。", learning_objectives: ["说明 checkpoint 恢复"], key_terms: ["Checkpoint"], difficulty_label: "intermediate", source_chunk_ids: [] },
    ],
    prerequisites: [{ prerequisite_title: "State 与 Reducer", dependent_title: "Checkpoint", rationale: "先理解状态再恢复", confidence: 0.9 }],
    learning_order: ["State 与 Reducer", "Checkpoint"],
    estimated_duration: 75,
    lesson_blueprints: [
      { knowledge_point: "State 与 Reducer", lesson_goal: "建立状态聚合心智模型", estimated_minutes: 40, requires_lesson_generation: true },
      { knowledge_point: "Checkpoint", lesson_goal: "识别执行恢复边界", estimated_minutes: 35, requires_lesson_generation: true },
    ],
    assumptions: ["学习者具备 Python 基础", "当前没有有效资料，本提案尚未经过资料验证。"],
    coverage_report: { goal_alignment: "覆盖七天入门的状态与恢复能力。", covered_topics: ["状态聚合", "恢复"], gaps: ["生产部署"], material_grounding: "goal_only_unverified" },
  },
  architecture: { draft_id: 4, public_id: "draft-4", version: 2, status: "ready", quality_status: "ready", quality_report: { status: "ready", blocker_count: 0, warning_count: 3, info_count: 0, source_coverage: 0, issues: [] } },
  expires_at: "2026-08-14T08:00:00Z",
  decided_at: null,
  created_at: now,
  updated_at: now,
};

function json(data: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } }));
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("V11D Curriculum 主流程", () => {
  it("从 Goal 生成提案，审查蓝图后显式接受并经既有架构发布", async () => {
    let current = structuredClone(curriculum) as CurriculumProposal;
    vi.stubGlobal("fetch", vi.fn((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/learning-goals/1") && !init?.method) return json(goal);
      if (url.endsWith("/learning-goals/1/materials")) return json([]);
      if (url.endsWith("/courses") && !init?.method) return json([]);
      if (url.endsWith("/learning-goals/1/curriculum-proposals") && init?.method === "POST") return json(current, 201);
      if (url.endsWith("/curriculum-proposals/proposal-v11d-1") && !init?.method) return json(current);
      if (url.endsWith("/curriculum-proposals/proposal-v11d-1/decision") && init?.method === "POST") {
        current = { ...current, status: "accepted", version: 2, decided_at: now };
        return json(current);
      }
      if (url.endsWith("/curriculum-proposals/proposal-v11d-1/publish") && init?.method === "POST") {
        current = { ...current, architecture: { ...current.architecture, status: "published", version: 3 } };
        return json({ proposal: current, publication: { draft_id: 4, publish_request_id: "publish-ui-1", course_ids: [12], knowledge_point_ids: [13, 14], material_link_count: 0, source_count: 0, prerequisite_count: 1, published_at: now } });
      }
      return json([]);
    }));

    renderApp(<App />, "/goals/1");
    expect(await screen.findByRole("heading", { name: goal.title })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "内容" }));
    expect(screen.getByText(/尚未关联资料/)).toBeInTheDocument();
    expect(screen.getByText("高级路线编辑")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "概览" }));
    await userEvent.click(screen.getByRole("button", { name: "生成路线建议" }));
    expect(await screen.findByRole("heading", { name: "LangGraph 七天核心路径" })).toBeInTheDocument();
    expect(screen.getByText("State 与 Reducer", { selector: "h3" })).toBeInTheDocument();
    expect(screen.getByText("Checkpoint", { selector: "h3" })).toBeInTheDocument();
    expect(screen.getByText("建立状态聚合心智模型")).toBeInTheDocument();
    expect(screen.getByText(/不会提前生成讲解、例子、练习或检查内容/)).toBeInTheDocument();
    expect(screen.queryByText(/内部推理|思维链|Raw JSON/)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "接受建议" }));
    expect(await screen.findByRole("button", { name: "确认使用这条路线" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "确认使用这条路线" }));
    expect(await screen.findByRole("link", { name: "查看事项" })).toBeInTheDocument();

    await waitFor(() => {
      const calls = vi.mocked(fetch).mock.calls;
      const generate = calls.find(([url, init]) => String(url).endsWith("/learning-goals/1/curriculum-proposals") && init?.method === "POST");
      const decision = calls.find(([url, init]) => String(url).endsWith("/decision") && init?.method === "POST");
      const publish = calls.find(([url, init]) => String(url).endsWith("/publish") && init?.method === "POST");
      expect(generate).toBeTruthy();
      expect(JSON.parse(String(decision?.[1]?.body))).toMatchObject({ decision: "accept", expected_version: 1, confirmed: true });
      expect(JSON.parse(String(publish?.[1]?.body))).toMatchObject({ expected_proposal_version: 2, draft_version: 2, confirmed: true });
    });
  });
});
