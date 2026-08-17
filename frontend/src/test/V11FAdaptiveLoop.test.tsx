import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import type { PlanAdjustmentProposal } from "../types";
import { renderApp } from "./render";


const now = "2026-08-08T01:00:00Z";
const pending: PlanAdjustmentProposal = {
  proposal_id: "plan-adjustment-v11f-1",
  proposal_type: "plan_adjustment",
  status: "pending",
  version: 1,
  context_version: "f".repeat(64),
  source_event_id: "mastery-event-v11f-1",
  study_plan_id: 7,
  study_plan_version: 2,
  active_plan_version: 1,
  reason: "最近 2 条有效学习证据显示《State 合并语义》当前掌握等级为“入门”（置信度 42%），需要在后续计划中补一次复习。",
  suggestion: "在正式计划中为《State 合并语义》增加一次复习。",
  impact: "接受后，确定性调度器会按现有时间预算、冲突和前置条件生成并发布一个新计划版本；确认前现有计划和每日任务保持不变。",
  adjustment_kind: "add_review",
  affected_items: [{ kind: "knowledge_point", id: 3, title: "State 合并语义", proposed_change: "add_review" }],
  mastery_change: {
    knowledge_point_id: 3,
    knowledge_point_title: "State 合并语义",
    old_level: "unassessed",
    new_level: "beginner",
    confidence: 42,
    evidence_ids: [8, 9],
  },
  mastery_evidence_ids: [8, 9],
  application: null,
  expires_at: "2026-08-15T01:00:00Z",
  decided_at: null,
  created_at: now,
  updated_at: now,
};

function json(data: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  }));
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("V11F Adaptive Plan Proposal", () => {
  it("只展示用户可审查的原因、建议和影响，并在明确接受后显示新安排", async () => {
    let current = structuredClone(pending);
    vi.stubGlobal("fetch", vi.fn((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/plan-adjustments/plan-adjustment-v11f-1") && !init?.method) {
        return json(current);
      }
      if (url.endsWith("/plan-adjustments/plan-adjustment-v11f-1/decision") && init?.method === "POST") {
        current = {
          ...current,
          status: "accepted",
          version: 2,
          decided_at: now,
          application: {
            new_plan_version: 2,
            active_plan_version: 2,
            created_task_ids: [12],
            reused_task_ids: [4],
            rescheduled_task_ids: [],
            idempotent_replay: false,
          },
        };
        return json(current);
      }
      return json({});
    }));

    renderApp(<App />, "/plan-adjustments/plan-adjustment-v11f-1");

    expect(await screen.findByRole("heading", { name: "审查接下来的安排" })).toBeInTheDocument();
    expect(screen.getByText(pending.reason)).toBeInTheDocument();
    expect(screen.getByText(pending.suggestion)).toBeInTheDocument();
    expect(screen.getByText(pending.impact)).toBeInTheDocument();
    expect(screen.getByText("依据 2 条最近练习与评估记录")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "拒绝调整" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "接受调整" })).toBeInTheDocument();
    expect(screen.queryByText(/Raw JSON|chain-of-thought|思维链/)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "接受调整" }));
    expect(await screen.findByText("新的安排已经生效")).toBeInTheDocument();
    expect(screen.getByText(/新增 1 项、沿用 1 项、\s*调整 0 项/)).toBeInTheDocument();

    await waitFor(() => {
      const decision = vi.mocked(fetch).mock.calls.find(
        ([url, init]) => String(url).endsWith("/decision") && init?.method === "POST",
      );
      expect(JSON.parse(String(decision?.[1]?.body))).toMatchObject({
        decision: "accept",
        expected_version: 1,
        context_version: "f".repeat(64),
        confirmed: true,
      });
    });
  });
});
