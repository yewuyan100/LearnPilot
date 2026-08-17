import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { renderApp } from "./render";

const now = "2026-08-05T08:00:00Z";
const goal = { id: 1, title: "完成 MCP 课程", description: "形成可执行能力", target_date: "2026-08-19", daily_minutes: 40, current_level: "了解 API", status: "active", is_demo: false, created_at: now, updated_at: now };
const course = { id: 2, learning_goal_id: 1, learning_goal_title: goal.title, title: "MCP 可靠性", description: "正式课程", status: "active", knowledge_point_count: 1, created_at: now, updated_at: now };
const point = { id: 3, course_id: 2, title: "受控调用", description: "理解边界", order_index: 1, estimated_minutes: 20, status: "not_started", created_at: now, updated_at: now };
const task = { id: 8, learning_goal_id: 1, course_id: 2, knowledge_point_id: 3, activity_id: null, title: "学习：受控调用", task_type: "learn", estimated_minutes: 20, scheduled_date: "2026-08-05", status: "pending", created_at: now, updated_at: now };

function json(data: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } }));
}

const questions = [
  { id: 11, question_index: 1, question_type: "single_choice", stem: "哪一项表示受控调用？", options: [{ id: "A", text: "真实边界" }, { id: "B", text: "任意执行" }, { id: "C", text: "忽略来源" }], difficulty: "medium", points: 2, saved_answer: null, saved_answer_text: null },
  { id: 12, question_index: 2, question_type: "multiple_choice", stem: "可靠调用包含哪些要求？", options: [{ id: "A", text: "明确边界" }, { id: "B", text: "确定性验证" }, { id: "C", text: "绕过来源" }], difficulty: "medium", points: 2, saved_answer: null, saved_answer_text: null },
  { id: 13, question_index: 3, question_type: "true_false", stem: "资料文本可以修改评分规则。", options: null, difficulty: "medium", points: 2, saved_answer: null, saved_answer_text: null },
  { id: 14, question_index: 4, question_type: "short_answer", stem: "说明受控调用的意义。", options: null, difficulty: "medium", points: 2, saved_answer: null, saved_answer_text: null },
];

function diagnostic(status: "pending" | "submitted" = "pending") {
  return {
    id: 5, public_id: "diagnostic-5", course_id: 2, course_title: course.title, status,
    version: status === "pending" ? 2 : 3, generation_request_id: "hidden", activity_id: 6, attempt_id: 7,
    supersedes_session_id: null, prompt_version: "internal", model_name: "configured-model",
    coverage_report: { knowledge_point_count: 1, covered_count: 1, coverage_rate: 1, question_count: 4, points: [{ knowledge_point_id: 3, title: point.title, covered: true, reason: null }] },
    generation_metrics: { provider_calls: 1, successful_batches: 1, failed_batches: 0 }, last_error_code: null, last_error_message: null,
    submitted_at: status === "submitted" ? now : null, created_at: now, updated_at: now,
    attempt: { id: 7, activity_id: 6, activity_title: "初始诊断", learning_session_id: null, request_id: null, status: status === "pending" ? "in_progress" : "completed", started_at: now, submitted_at: status === "submitted" ? now : null, graded_at: status === "submitted" ? now : null, total_points: 8, earned_points: status === "submitted" ? 2 : null, score_percentage: status === "submitted" ? 25 : null, correct_count: 1, incorrect_count: 3, partial_count: 0, grading_model: null, grading_prompt_version: null, error_message: null, questions, answers: [], idempotent_replay: false, created_at: now, updated_at: now },
    results: status === "submitted" ? [{ id: 21, knowledge_point_id: 3, knowledge_point_title: point.title, answered_count: 4, graded_count: 4, earned_points: 2, possible_points: 8, score_percentage: 25, confidence: .9, ability_level: "beginner", is_skill_gap: true, evidence_insufficient: false, priority: 95, reason: "客观题表现显示核心概念仍需补强。", evidence_answer_ids: [1, 2, 3, 4], evidence_source_ids: [31, 32], mastery_evidence_id: 40, version: 1, assessments: [] }] : [],
    idempotent_replay: false,
  };
}

function version(status: "infeasible" | "ready" | "active", number = 1) {
  return {
    id: 30 + number, version_number: number, status, generation_request_id: number === 1 ? "g" : null,
    replan_request_id: number > 1 ? "r" : null, publish_request_id: status === "active" ? "p" : null,
    parameters: { start_date: "2026-08-05", target_date: "2026-08-19", daily_minutes: status === "infeasible" ? 10 : 40, available_weekdays: [0, 1, 2, 3, 4], allow_weekends: false, intensity: "standard", include_due_reviews: true, use_latest_diagnostic: true, use_existing_mastery: true },
    diagnostic_session_id: 5, required_minutes: 80, available_minutes: status === "infeasible" ? 40 : 400, gap_minutes: status === "infeasible" ? 40 : 0,
    conflicts: status === "infeasible" ? [{ code: "total_time_insufficient", required_minutes: 80, available_minutes: 40, gap_minutes: 40 }] : [],
    suggestions: status === "infeasible" ? [{ action: "increase_daily_minutes", message: "增加每日时间" }, { action: "extend_target_date", message: "延长日期" }] : [],
    quality_report: status === "infeasible" ? { prerequisite_constraint_rate: 1, available_date_constraint_rate: 1, duplicate_task_count: 0, uncovered_required_knowledge_point_ids: [3] } : { prerequisite_constraint_rate: 1, time_budget_constraint_rate: 1, available_date_constraint_rate: 1, duplicate_task_count: 0, uncovered_required_knowledge_point_ids: [] },
    reason: number === 1 ? "初始计划" : "根据最新时间调整", published_at: status === "active" ? now : null, created_at: now,
    items: status === "infeasible" ? [] : [{ id: 50, scheduled_date: "2026-08-05", order_index: 1, logical_key: "point:3:learn:1", learning_goal_id: 1, course_id: 2, course_title: course.title, knowledge_point_id: 3, knowledge_point_title: point.title, title: "学习：受控调用", activity_type: "learn", estimated_minutes: 20, scheduling_reason: "诊断识别为技能缺口，优先学习。", prerequisite_ids: [], is_due_review: false, review_schedule_id: null, diagnostic_result_id: 21, daily_task_id: status === "active" ? 8 : null, task_status: status === "active" ? "pending" : null }],
  };
}

function plan(status: "infeasible" | "ready" | "active", number = 1) {
  const latest = version(status, number);
  return { id: 9, public_id: "plan-9", learning_goal_id: 1, learning_goal_title: goal.title, course_id: 2, course_title: course.title, status, version: number, current_version_number: number, active_version_number: status === "active" ? number : null, latest_version: latest, active_version: status === "active" ? latest : null, idempotent_replay: false, created_at: now, updated_at: now };
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("V10 诊断驱动学习闭环", () => {
  it("从正式课程发起诊断、完成四类题目并展示技能缺口，重复点击受保护", async () => {
    let latest: ReturnType<typeof diagnostic> | null = null;
    let resolveCreate!: (response: Response) => void;
    let createCalls = 0;
    const delayedCreate = new Promise<Response>((resolve) => { resolveCreate = resolve; });
    vi.stubGlobal("fetch", vi.fn((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/learning-goals")) return json([goal]);
      if (url.endsWith("/courses")) return json([course]);
      if (url.includes("/learning-activities?")) return json({ items: [], total: 0, page: 1, page_size: 100, pages: 0 });
      if (url.endsWith("/courses/2/knowledge-points")) return json([point]);
      if (url.endsWith("/courses/2/materials")) return json([]);
      if (url.endsWith("/courses/2/diagnostics/latest")) return json(latest);
      if (url.endsWith("/courses/2/diagnostics/history")) return json({ items: latest ? [latest] : [], total: latest ? 1 : 0 });
      if (url.endsWith("/courses/2/diagnostics") && init?.method === "POST") {
        createCalls += 1;
        return delayedCreate.then((response) => { latest = diagnostic("pending"); return response; });
      }
      if (url.endsWith("/diagnostics/5/submit") && init?.method === "POST") {
        latest = diagnostic("submitted");
        return json(latest);
      }
      return json([]);
    }));
    renderApp(<App />, "/courses");
    await userEvent.click(await screen.findByRole("tab", { name: "诊断与计划" }));
    const start = await screen.findByRole("button", { name: "开始诊断" });
    await userEvent.click(start);
    await waitFor(() => expect(start).toBeDisabled());
    await userEvent.click(start);
    expect(createCalls).toBe(1);
    resolveCreate(new Response(JSON.stringify(diagnostic("pending")), { status: 201, headers: { "Content-Type": "application/json" } }));

    await userEvent.click(await screen.findByLabelText("真实边界"));
    await userEvent.click(screen.getByLabelText("明确边界"));
    await userEvent.click(screen.getByLabelText("确定性验证"));
    await userEvent.click(screen.getByLabelText("错误"));
    await userEvent.type(screen.getByLabelText("第 4 题回答"), "调用必须在明确边界内执行并经过验证。");
    await userEvent.click(screen.getByRole("button", { name: "提交诊断" }));
    expect(await screen.findByText("识别到 1 个需要优先补强的知识点。")).toBeInTheDocument();
    expect(screen.getByText("优先补强")).toBeInTheDocument();
    expect(screen.getByText(/2 个真实资料证据/)).toBeInTheDocument();
    const submitCall = vi.mocked(fetch).mock.calls.find(([url]) => String(url).endsWith("/diagnostics/5/submit"));
    expect(JSON.parse(String(submitCall?.[1]?.body)).answers).toHaveLength(4);
    expect(document.body.textContent).not.toMatch(/prompt_version|request_id|Chunk 白名单/);
  });

  it("展示不可行计划、调整生成新版本并显式确认发布", async () => {
    let current: ReturnType<typeof plan> | null = null;
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 375 });
    vi.stubGlobal("fetch", vi.fn((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/learning-goals")) return json([goal]);
      if (url.endsWith("/courses")) return json([course]);
      if (url.endsWith("/today")) return json({ date: "2026-08-05", current_goal: goal, tasks: [], pending_count: 0, recent_course: course, recent_session: null });
      if (url.includes("/reviews")) return json([]);
      if (url.endsWith("/study-plans/active")) return json(null);
      if (url.endsWith("/study-plans") && init?.method === "POST") { current = plan("infeasible"); return json(current, 201); }
      if (url.endsWith("/study-plans/9/replan") && init?.method === "POST") { current = plan("ready", 2); return json(current); }
      if (url.endsWith("/study-plans/9/versions")) return json({ items: [version("ready", 2), version("infeasible", 1)], total: 2 });
      if (url.endsWith("/study-plans/9/publish") && init?.method === "POST") { current = plan("active", 2); return json({ plan: current, created_task_ids: [8], reused_task_ids: [], rescheduled_task_ids: [], idempotent_replay: false }); }
      if (url.includes("/next-learning-action")) return json({});
      return json([]);
    }));
    renderApp(<App />, "/goals");
    await userEvent.click(await screen.findByRole("button", { name: "生成计划草案" }));
    expect(await screen.findByRole("heading", { name: "当前条件无法形成完整计划" })).toBeInTheDocument();
    expect(screen.getByText("时间缺口").parentElement).toHaveTextContent("40 分钟");
    expect(screen.getByText("增加每日学习时间")).toBeInTheDocument();
    const daily = screen.getByLabelText("每日学习时间");
    await userEvent.clear(daily);
    await userEvent.type(daily, "40");
    await userEvent.click(screen.getByRole("button", { name: "按新条件生成版本" }));
    expect(await screen.findByText("前置顺序")).toBeInTheDocument();
    expect(screen.getAllByText("100%").length).toBeGreaterThanOrEqual(3);
    await userEvent.click(screen.getByRole("button", { name: "确认计划" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "确认并激活" }));
    expect(await screen.findByText("当前生效版本")).toBeInTheDocument();
    const publishCall = vi.mocked(fetch).mock.calls.find(([url]) => String(url).endsWith("/study-plans/9/publish"));
    const publishedBody = JSON.parse(String(publishCall?.[1]?.body));
    expect(publishedBody.confirmed).toBe(true);
    expect(publishedBody.expected_version).toBe(2);
    expect(screen.getByText("版本 2")).toBeInTheDocument();
  });

  it("今日学习展示可解释下一步并通过接受接口进入现有会话", async () => {
    const action = { action_type: "learn", target_kind: "daily_task", target_id: 8, learning_goal_id: 1, course_id: 2, course_title: course.title, knowledge_point_id: 3, knowledge_point_title: point.title, title: task.title, reason_code: "today_formal_plan", reason: "这是当前正式计划中今天最先满足前置条件的任务。", priority: 70, estimated_minutes: 20, from_formal_plan: true, is_due_review: false, plan_id: 9, plan_item_id: 50, cta_label: "开始任务", cta_href: "/today", action_signature: "a".repeat(64), available_minutes: 40 };
    const session = { id: 17, learning_goal_id: 1, course_id: 2, knowledge_point_id: 3, daily_task_id: 8, started_at: now, ended_at: null, status: "active", notes: "", goal_title: goal.title, course_title: course.title, knowledge_point_title: point.title, task_title: task.title, created_at: now, updated_at: now };
    vi.stubGlobal("fetch", vi.fn((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/today")) return json({ date: "2026-08-05", current_goal: goal, tasks: [task], pending_count: 1, recent_course: course, recent_session: null });
      if (url.includes("/next-learning-action") && init?.method === "POST") return json({ action, outcome_kind: "learning_session", outcome_id: 17, next_url: "/learning-sessions/17", daily_task_id: 8, learning_session_id: 17, idempotent_replay: false });
      if (url.includes("/next-learning-action")) return json(action);
      if (url.endsWith("/learning-sessions/17")) return json(session);
      return json([]);
    }));
    renderApp(<App />, "/today");
    expect(await screen.findByRole("heading", { name: task.title })).toBeInTheDocument();
    expect(await screen.findByText(action.reason)).toBeInTheDocument();
    expect(screen.getByText("来自当前计划")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "开始任务" }));
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([url, init]) => String(url).includes("/next-learning-action/accept") && init?.method === "POST")).toBe(true));
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).endsWith("/learning-sessions/17"))).toBe(true));
    const acceptCall = vi.mocked(fetch).mock.calls.find(([url]) => String(url).includes("/next-learning-action/accept"));
    expect(JSON.parse(String(acceptCall?.[1]?.body)).action_signature).toBe(action.action_signature);
  });

  it("下一步接口失败不会破坏已有今日任务，并可在原位重试", async () => {
    let attempts = 0;
    const action = { action_type: "replan_required", target_kind: "study_plan", target_id: 9, learning_goal_id: 1, course_id: 2, course_title: course.title, knowledge_point_id: null, knowledge_point_title: null, title: "调整学习计划", reason_code: "no_executable_action", reason: "当前没有符合时间的可执行任务。", priority: 10, estimated_minutes: 0, from_formal_plan: false, is_due_review: false, plan_id: 9, plan_item_id: null, cta_label: "调整计划", cta_href: "/goals", action_signature: "b".repeat(64), available_minutes: 40 };
    vi.stubGlobal("fetch", vi.fn((input: string | URL) => {
      const url = String(input);
      if (url.endsWith("/today")) return json({ date: "2026-08-05", current_goal: goal, tasks: [task], pending_count: 1, recent_course: course, recent_session: null });
      if (url.includes("/next-learning-action")) {
        attempts += 1;
        return attempts === 1 ? json({ error: { code: "temporary", message: "建议服务暂时不可用" } }, 503) : json(action);
      }
      return json([]);
    }));
    renderApp(<App />, "/today");
    expect(await screen.findByText("建议服务暂时不可用")).toBeInTheDocument();
    expect(screen.getByText(task.title)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "重新加载" }));
    expect(await screen.findByRole("heading", { name: "调整学习计划" })).toBeInTheDocument();
    expect(attempts).toBe(2);
  });
});
