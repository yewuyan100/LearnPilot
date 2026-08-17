import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useLocation, Routes, Route } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as productFlow from "../api/productFlow";
import {
  activitiesApi,
  attemptsApi,
  coursesApi,
  dashboardApi,
  goalsApi,
  lessonsApi,
  masteryApi,
  materialLearningApi,
  materialsApi,
  nextActionApi,
  notesApi,
  sessionsApi,
  wrongAnswersApi,
} from "../api/resources";
import { GoalDetailPage } from "../pages/GoalDetailPage";
import { LessonPage } from "../pages/LessonPage";
import { MaterialDetailPage } from "../pages/MaterialDetailPage";
import { QuizAttemptPage } from "../pages/QuizAttemptPage";
import { QuizResultPage } from "../pages/QuizResultPage";
import type { QuizAttempt } from "../types";
import { renderApp } from "./render";

const now = "2026-08-10T08:00:00Z";

const question = {
  id: 41,
  question_index: 1,
  question_type: "short_answer" as const,
  stem: "什么是稳定重试身份？",
  options: null,
  difficulty: "medium",
  points: 2,
  saved_answer: null,
  saved_answer_text: "原答案",
};

function attempt(overrides: Partial<QuizAttempt> = {}): QuizAttempt {
  return {
    id: 31,
    activity_id: 9,
    activity_title: "稳定重试检查",
    learning_session_id: 17,
    request_id: null,
    status: "in_progress",
    started_at: now,
    submitted_at: null,
    graded_at: null,
    total_points: null,
    earned_points: null,
    score_percentage: null,
    correct_count: 0,
    incorrect_count: 0,
    partial_count: 0,
    grading_model: null,
    grading_prompt_version: null,
    error_message: null,
    questions: [question],
    answers: [],
    idempotent_replay: false,
    created_at: now,
    updated_at: now,
    ...overrides,
  };
}

const lesson = {
  id: 4,
  public_id: "lesson-4",
  course_id: 2,
  course_title: "稳定性路线",
  learning_goal_id: 1,
  title: "稳定重试课节",
  description: "验证来源上下文。",
  order_index: 1,
  status: "published",
  current_version_number: 1,
  active_version_number: 1,
  latest_version: null,
  active_version: {
    id: 41,
    lesson_id: 4,
    version_number: 1,
    status: "published",
    objectives: ["保持上下文"],
    content_markdown: "课节内容",
    examples: [],
    guided_practice: [],
    checks: [],
    estimated_minutes: 10,
    source_snapshot_hash: "a".repeat(64),
    generation_request_id: "lesson-request-1",
    model_name: "test",
    prompt_version: "v1",
    quality_report: {},
    published_at: now,
    created_at: now,
    updated_at: now,
    knowledge_points: [{ knowledge_point_id: 3, title: "稳定性", order_index: 1, role: "primary" }],
    sources: [],
  },
  idempotent_replay: false,
  created_at: now,
  updated_at: now,
};

const session = {
  id: 17,
  learning_goal_id: 1,
  course_id: 2,
  knowledge_point_id: 3,
  daily_task_id: null,
  lesson_version_id: 41,
  started_at: now,
  ended_at: null,
  status: "active",
  notes: "",
  invalidated_at: null,
  invalidation_reason: null,
  goal_title: "Goal A",
  course_title: "稳定性路线",
  knowledge_point_title: "稳定性",
  task_title: null,
  lesson_id: 4,
  lesson_title: "稳定重试课节",
  lesson_version_number: 1,
  created_at: now,
  updated_at: now,
};

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname}{location.search}</output>;
}

function FlowRoutes() {
  return <>
    <Routes>
      <Route path="/lessons/:id" element={<LessonPage />} />
      <Route path="/quiz-attempts/:id" element={<QuizAttemptPage />} />
      <Route path="/quiz-attempts/:id/result" element={<QuizResultPage />} />
      <Route path="/items/:id" element={<div>事项上下文</div>} />
      <Route path="/activities/:id" element={<div>活动上下文</div>} />
      <Route path="/workspace" element={<div>安全工作台</div>} />
    </Routes>
    <LocationProbe />
  </>;
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("Final Fix Batch 2A · H05", () => {
  it("failed attempt 在 remount 后复用后端返回的原 request_id", async () => {
    const failed = attempt({
      status: "failed",
      request_id: "stable-submit-request-31",
      submitted_at: now,
      error_message: "批改服务暂时不可用",
    });
    const get = vi.spyOn(attemptsApi, "get").mockResolvedValue(failed);
    const submit = vi.spyOn(attemptsApi, "submit").mockRejectedValue(new Error("批改服务暂时不可用"));
    vi.spyOn(window, "confirm").mockReturnValue(true);

    const first = renderApp(<FlowRoutes />, "/quiz-attempts/31?origin=goal&goal_id=1");
    expect(await screen.findByRole("button", { name: "重试批改" })).toBeInTheDocument();
    first.unmount();

    renderApp(<FlowRoutes />, "/quiz-attempts/31?origin=goal&goal_id=1");
    await userEvent.click(await screen.findByRole("button", { name: "重试批改" }));
    await waitFor(() => expect(submit).toHaveBeenCalled());
    expect(submit.mock.calls[0][1]).toMatchObject({
      request_id: "stable-submit-request-31",
      answers: [{ question_id: 41, answer_text: "原答案" }],
    });
    expect(get).toHaveBeenCalledTimes(3);
  });

  it("不同 failed attempts 各自恢复身份，completed attempt 不显示 Retry", async () => {
    vi.spyOn(attemptsApi, "get").mockImplementation(async (id) => attempt({
      id,
      status: id === 33 ? "completed" : "failed",
      request_id: id === 31 ? "stable-request-31" : id === 32 ? "stable-request-32" : "stable-request-33",
      submitted_at: now,
      graded_at: id === 33 ? now : null,
      total_points: id === 33 ? 2 : null,
      earned_points: id === 33 ? 2 : null,
      score_percentage: id === 33 ? 100 : null,
      error_message: id === 33 ? null : "暂时失败",
      questions: id === 33 ? [] : [question],
    }));
    const submit = vi.spyOn(attemptsApi, "submit").mockRejectedValue(new Error("暂时失败"));
    vi.spyOn(window, "confirm").mockReturnValue(true);

    for (const id of [31, 32]) {
      const rendered = renderApp(<FlowRoutes />, `/quiz-attempts/${id}`);
      await userEvent.click(await screen.findByRole("button", { name: "重试批改" }));
      await waitFor(() => expect(submit).toHaveBeenCalledTimes(id - 30));
      rendered.unmount();
    }
    expect(submit.mock.calls.map((call) => call[1].request_id)).toEqual([
      "stable-request-31",
      "stable-request-32",
    ]);

    vi.spyOn(activitiesApi, "get").mockResolvedValue({ id: 9, knowledge_point_id: null } as never);
    renderApp(<FlowRoutes />, "/quiz-attempts/33");
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/quiz-attempts/33/result"));
    expect(screen.queryByRole("button", { name: "重试批改" })).not.toBeInTheDocument();
  });
});

describe("Final Fix Batch 2A · H08", () => {
  it("Lesson → Quiz 写入来源，Exit 返回同一 Lesson 与 session", async () => {
    vi.spyOn(lessonsApi, "get").mockResolvedValue(lesson as never);
    vi.spyOn(sessionsApi, "get").mockResolvedValue(session as never);
    vi.spyOn(sessionsApi, "update").mockResolvedValue({ ...session, status: "completed" } as never);
    vi.spyOn(productFlow, "prepareLessonAssessment").mockResolvedValue(attempt());
    vi.spyOn(attemptsApi, "get").mockResolvedValue(attempt());

    renderApp(<FlowRoutes />, "/lessons/4?session=17");
    await userEvent.click(await screen.findByRole("button", { name: "检查一下理解" }));
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent(
      "/quiz-attempts/31?origin=lesson&lesson_id=4&goal_id=1&session_id=17",
    ));
    await userEvent.click(await screen.findByRole("button", { name: "退出测验" }));
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/lessons/4?session=17"));
  });

  it("Result 刷新后仍返回 Lesson；Goal A 不使用 Goal B 的全局 next action", async () => {
    const completed = attempt({
      status: "completed",
      request_id: "stable-result-31",
      submitted_at: now,
      graded_at: now,
      total_points: 2,
      earned_points: 2,
      score_percentage: 100,
      correct_count: 1,
      questions: [],
    });
    vi.spyOn(attemptsApi, "get").mockResolvedValue(completed);
    vi.spyOn(activitiesApi, "get").mockResolvedValue({ id: 9, knowledge_point_id: null } as never);
    const next = vi.spyOn(nextActionApi, "get").mockResolvedValue({
      learning_goal_id: 2,
      action_type: "review_proposal",
      title: "Goal B 的建议",
      reason: "不属于当前事项",
      cta_label: "去 Goal B",
      cta_href: "/items/2",
    } as never);

    const lessonResult = renderApp(
      <FlowRoutes />,
      "/quiz-attempts/31/result?origin=lesson&lesson_id=4&goal_id=1&session_id=17",
    );
    expect(await screen.findByRole("link", { name: "返回课节" })).toHaveAttribute("href", "/lessons/4?session=17");
    await waitFor(() => expect(next).toHaveBeenCalled());
    expect(screen.queryByText("Goal B 的建议")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "去 Goal B" })).not.toBeInTheDocument();
    lessonResult.unmount();

    renderApp(<FlowRoutes />, "/quiz-attempts/31/result?origin=goal&goal_id=1");
    expect(await screen.findByRole("link", { name: "返回事项" })).toHaveAttribute("href", "/items/1");
    expect(screen.queryByText("Goal B 的建议")).not.toBeInTheDocument();
  });

  it("没有合法 origin 的 direct Quiz 使用 /workspace，绝不返回 /activities", async () => {
    vi.spyOn(attemptsApi, "get").mockResolvedValue(attempt());
    renderApp(<FlowRoutes />, "/quiz-attempts/31");
    await userEvent.click(await screen.findByRole("button", { name: "退出测验" }));
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/workspace"));
    expect(screen.getByText("安全工作台")).toBeInTheDocument();
  });
});

function mockGoalDependencies() {
  vi.spyOn(coursesApi, "list").mockResolvedValue([]);
  vi.spyOn(materialLearningApi, "goalMaterials").mockResolvedValue([]);
  vi.spyOn(dashboardApi, "today").mockResolvedValue({ current_goal: null, tasks: [], recent_session: null } as never);
  vi.spyOn(notesApi, "list").mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100, pages: 0 });
  vi.spyOn(masteryApi, "weakPoints").mockResolvedValue([]);
  vi.spyOn(masteryApi, "list").mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100, pages: 0 });
  vi.spyOn(activitiesApi, "list").mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100, pages: 0 });
  vi.spyOn(wrongAnswersApi, "list").mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100, pages: 0 });
  vi.spyOn(dashboardApi, "reviews").mockResolvedValue({ knowledge_points: [] } as never);
}

function mockMaterialDependencies() {
  vi.spyOn(materialLearningApi, "list").mockResolvedValue([]);
  vi.spyOn(notesApi, "list").mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100, pages: 0 });
  vi.spyOn(activitiesApi, "list").mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100, pages: 0 });
  vi.spyOn(materialsApi, "chunks").mockResolvedValue({ items: [], total: 0, page: 1, page_size: 10, pages: 0 });
}

function DetailRoutes() {
  return <Routes>
    <Route path="/items/:id" element={<GoalDetailPage />} />
    <Route path="/materials/:id" element={<MaterialDetailPage />} />
  </Routes>;
}

describe("Final Fix Batch 2A · H09", () => {
  it.each(["/items/foo", "/items/0", "/items/-1"])("%s 不请求 detail API 且安全显示", async (path) => {
    const get = vi.spyOn(goalsApi, "get");
    renderApp(<DetailRoutes />, path);
    expect(await screen.findByText("页面不存在")).toBeInTheDocument();
    expect(get).not.toHaveBeenCalled();
  });

  it.each(["/materials/foo", "/materials/0", "/materials/-1"])("%s 不请求 detail API 且安全显示", async (path) => {
    const get = vi.spyOn(materialsApi, "get");
    renderApp(<DetailRoutes />, path);
    expect(await screen.findByText("页面不存在")).toBeInTheDocument();
    expect(get).not.toHaveBeenCalled();
  });

  it("合法但不存在的 items/materials ID 显示正常错误状态", async () => {
    mockGoalDependencies();
    vi.spyOn(goalsApi, "get").mockRejectedValue(new Error("事项不存在"));
    const missingGoal = renderApp(<DetailRoutes />, "/items/999999999");
    expect(await screen.findByText("事项不存在")).toBeInTheDocument();
    missingGoal.unmount();
    vi.restoreAllMocks();

    mockMaterialDependencies();
    vi.spyOn(materialsApi, "get").mockRejectedValue(new Error("资料不存在"));
    renderApp(<DetailRoutes />, "/materials/999999999");
    expect(await screen.findByText("资料不存在")).toBeInTheDocument();
  });

  it("合法存在的 items/materials ID 仍正常加载", async () => {
    mockGoalDependencies();
    vi.spyOn(goalsApi, "get").mockResolvedValue({
      id: 1,
      title: "合法事项",
      description: "",
      target_date: null,
      daily_minutes: 30,
      current_level: "入门",
      status: "active",
      created_at: now,
      updated_at: now,
    } as never);
    const validGoal = renderApp(<DetailRoutes />, "/items/1");
    expect(await screen.findByRole("heading", { name: "合法事项" })).toBeInTheDocument();
    validGoal.unmount();
    vi.restoreAllMocks();

    mockMaterialDependencies();
    vi.spyOn(materialsApi, "get").mockResolvedValue({
      id: 1,
      title: "合法资料",
      original_filename: "valid.md",
      ingestion_status: "completed",
      indexing_status: "completed",
      deletion_status: "active",
      archived_at: null,
      chunk_count: 1,
      indexed_chunk_count: 1,
      processed_at: now,
      indexed_at: now,
      created_at: now,
      updated_at: now,
    } as never);
    renderApp(<DetailRoutes />, "/materials/1");
    expect(await screen.findByRole("heading", { name: "合法资料" })).toBeInTheDocument();
  });
});
