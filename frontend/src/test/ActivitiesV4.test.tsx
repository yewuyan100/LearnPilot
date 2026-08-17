import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import type {
  ActivityDetail,
  Material,
  QuizAttempt,
  WrongAnswer,
} from "../types";
import { renderApp } from "./render";

const now = "2026-07-30T10:00:00";
const source = {
  id: 1,
  question_id: 1,
  source_label: "S1",
  material_id: 8,
  chunk_id: 91,
  rank: 1,
  score: 0.9,
  original_filename: "mcp.md",
  chunk_index: 0,
  page_number: null,
  section_title: "Tools",
  content_excerpt: "Tools 由模型调用，Resources 由应用控制。",
  source_available: true,
  created_at: now,
  updated_at: now,
};
const question = {
  id: 1,
  activity_id: 1,
  question_index: 1,
  question_type: "single_choice" as const,
  stem: "Tools 由谁调用？",
  options: [
    { id: "A", text: "模型" },
    { id: "B", text: "资源" },
    { id: "C", text: "用户文件" },
  ],
  correct_answer: ["A"],
  reference_answer: null,
  grading_rubric: null,
  explanation: "Tools 由模型主动调用。",
  difficulty: "easy",
  points: 2,
  status: "active",
  sources: [source],
  created_at: now,
  updated_at: now,
};
const activity: ActivityDetail = {
  id: 1,
  title: "MCP 测验",
  description: "基于本地资料",
  activity_type: "quiz",
  status: "draft",
  course_id: 1,
  knowledge_point_id: 1,
  course_title: "MCP 基础",
  knowledge_point_title: "控制方向",
  question_count: 1,
  total_points: 2,
  published_at: null,
  completed_attempt_count: 0,
  source_scope: { material_ids: [8] },
  generation_request_id: "request-1",
  prompt_version: "activity-generation-v1",
  model_name: "fake",
  validation_warnings: [],
  questions: [question],
  created_at: now,
  updated_at: now,
};
const indexedMaterial: Material = {
  id: 8,
  title: "MCP",
  original_filename: "mcp.md",
  stored_filename: "mcp-8.md",
  file_path: "uploads/mcp-8.md",
  source_type: "md",
  mime_type: "text/markdown",
  file_size: 100,
  processing_status: "ready",
  ingestion_status: "completed",
  indexing_status: "completed",
  chunk_count: 3,
  indexed_chunk_count: 3,
  processed_at: now,
  indexed_at: now,
  error_message: null,
  deletion_status: "active",
  deletion_error: null,
  deletion_requested_at: null,
  deletion_attempts: 0,
  created_at: now,
  updated_at: now,
};
const pendingMaterial = {
  ...indexedMaterial,
  id: 9,
  original_filename: "pending.md",
  ingestion_status: "pending",
  indexing_status: "pending",
};

function response(data: unknown, status = 200) {
  return Promise.resolve(
    new Response(status === 204 ? null : JSON.stringify(data), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

const attemptBase: QuizAttempt = {
  id: 3,
  activity_id: 1,
  activity_title: "MCP 测验",
  learning_session_id: null,
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
  questions: [
    {
      id: 1,
      question_index: 1,
      question_type: "single_choice",
      stem: "Tools 由谁调用？",
      options: question.options,
      difficulty: "easy",
      points: 2,
      saved_answer: null,
      saved_answer_text: null,
    },
    {
      id: 2,
      question_index: 2,
      question_type: "multiple_choice",
      stem: "选择核心原语",
      options: question.options,
      difficulty: "medium",
      points: 2,
      saved_answer: null,
      saved_answer_text: null,
    },
    {
      id: 3,
      question_index: 3,
      question_type: "true_false",
      stem: "Resources 由应用控制。",
      options: null,
      difficulty: "easy",
      points: 2,
      saved_answer: null,
      saved_answer_text: null,
    },
    {
      id: 4,
      question_index: 4,
      question_type: "short_answer",
      stem: "说明控制方向。",
      options: null,
      difficulty: "medium",
      points: 4,
      saved_answer: null,
      saved_answer_text: null,
    },
  ],
  answers: [],
  idempotent_replay: false,
  created_at: now,
  updated_at: now,
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("学习活动 V4", () => {
  it("生成表单只显示已索引资料并提交真实配置", async () => {
    const fetchMock = vi.fn((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/learning-activities?")) {
        return response({ items: [], total: 0, page: 1, page_size: 100, pages: 0 });
      }
      if (url.endsWith("/courses")) {
        return response([{ id: 1, title: "MCP 基础", description: "", status: "active", learning_goal_id: 1, learning_goal_title: "目标", knowledge_point_count: 1, created_at: now, updated_at: now }]);
      }
      if (url.endsWith("/courses/1/knowledge-points")) {
        return response([{ id: 1, course_id: 1, title: "控制方向", description: "", order_index: 0, estimated_minutes: 20, status: "learning", created_at: now, updated_at: now }]);
      }
      if (url.includes("/materials?")) return response([indexedMaterial, pendingMaterial]);
      if (url.endsWith("/learning-activities/generate") && init?.method === "POST") {
        return response(activity, 201);
      }
      if (url.endsWith("/learning-activities/1")) return response(activity);
      return response([]);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp(<App />, "/activities");

    await userEvent.click(await screen.findByRole("button", { name: "生成活动" }));
    expect(screen.getByText("mcp.md")).toBeInTheDocument();
    expect(screen.queryByText("pending.md")).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("活动标题"), "MCP 测验");
    await userEvent.selectOptions(screen.getByLabelText("活动课程"), "1");
    await userEvent.selectOptions(await screen.findByLabelText("活动知识点"), "1");
    await userEvent.click(screen.getByRole("checkbox", { name: /mcp.md/ }));
    await userEvent.click(screen.getByRole("button", { name: "生成题目草稿" }));
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([url]) =>
        String(url).endsWith("/learning-activities/generate"),
      );
      expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({
        title: "MCP 测验",
        course_id: 1,
        knowledge_point_id: 1,
        material_ids: [8],
      });
    });
  });

  it("草稿预览支持排序、删除和发布确认", async () => {
    const second = { ...question, id: 2, question_index: 2, stem: "Resources 由谁控制？" };
    const draft = { ...activity, question_count: 2, questions: [question, second] };
    const fetchMock = vi.fn((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/learning-activities/1/questions/reorder")) return response(draft);
      if (url.includes("/learning-activities/1/questions/") && init?.method === "DELETE") return response(activity);
      if (url.endsWith("/learning-activities/1/publish")) return response({ ...draft, status: "published" });
      if (url.endsWith("/learning-activities/1")) return response(draft);
      if (url.includes("/learning-activities?")) return response({ items: [], total: 0, page: 1, page_size: 100, pages: 0 });
      return response([]);
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderApp(<App />, "/activities/1");

    expect((await screen.findAllByText("标准答案")).length).toBe(2);
    await userEvent.click(screen.getByRole("button", { name: "上移第 2 题" }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/questions/reorder"),
        expect.objectContaining({ method: "POST" }),
      ),
    );
    await userEvent.click(screen.getByRole("button", { name: "删除第 1 题" }));
    await userEvent.click(screen.getByRole("button", { name: "发布活动" }));
    expect(window.confirm).toHaveBeenCalledWith(
      expect.stringContaining("发布后题目内容将固定"),
    );
  });

  it("答题页支持四类题型、保存和未作答提交确认", async () => {
    let completed = false;
    const resultAnswer = {
      id: 11,
      question_id: 1,
      question_type: "single_choice" as const,
      stem: "Tools 由谁调用？",
      answer: ["A"],
      answer_text: null,
      is_correct: true,
      grading_status: "completed" as const,
      earned_points: 2,
      max_points: 2,
      feedback: "回答正确",
      matched_rubric_items: null,
      missing_rubric_items: null,
      grader_confidence: 1,
      correct_answer: ["A"],
      reference_answer: null,
      grading_rubric: null,
      explanation: "解析",
      sources: [source],
      wrong_answer_id: null,
      wrong_answer_status: null,
      created_at: now,
      updated_at: now,
    };
    const completedAttempt: QuizAttempt = {
      ...attemptBase,
      status: "completed",
      submitted_at: now,
      graded_at: now,
      total_points: 10,
      earned_points: 8,
      score_percentage: 80,
      correct_count: 2,
      incorrect_count: 1,
      partial_count: 1,
      answers: [resultAnswer],
    };
    const fetchMock = vi.fn((input: string | URL) => {
      const url = String(input);
      if (url.endsWith("/quiz-attempts/3/submit")) {
        completed = true;
        return response(completedAttempt);
      }
      if (url.includes("/quiz-attempts/3/answers/")) return response(attemptBase);
      if (url.endsWith("/quiz-attempts/3")) return response(completed ? completedAttempt : attemptBase);
      return response([]);
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderApp(<App />, "/quiz-attempts/3");

    const radios = await screen.findAllByRole("radio");
    await userEvent.click(radios[0]);
    expect(screen.getAllByRole("checkbox").length).toBeGreaterThan(0);
    expect(screen.getByRole("radio", { name: "正确" })).toBeInTheDocument();
    const textarea = screen.getByLabelText("第 4 题简答");
    await userEvent.type(textarea, "模型调用，应用控制。");
    fireEvent.blur(textarea);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/answers/4"), expect.objectContaining({ method: "PUT" })));
    await userEvent.click(screen.getByRole("button", { name: "提交测验" }));
    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining("未作答"));
    expect(await screen.findByText("80%")).toBeInTheDocument();
  });

  it("结果展示部分得分、来源，错题可加入复习", async () => {
    const wrong: WrongAnswer = {
      id: 5,
      question_id: 1,
      attempt_id: 3,
      answer_id: 11,
      course_id: 1,
      knowledge_point_id: 1,
      course_title: "MCP 基础",
      knowledge_point_title: "控制方向",
      status: "active",
      error_type: "incorrect",
      review_count: 0,
      last_reviewed_at: null,
      resolved_at: null,
      question_type: "single_choice",
      stem: "Tools 由谁调用？",
      explanation: "Tools 由模型调用。",
      answer: ["B"],
      answer_text: null,
      correct_answer: ["A"],
      reference_answer: null,
      sources: [source],
      created_at: now,
      updated_at: now,
    };
    const fetchMock = vi.fn((input: string | URL) => {
      const url = String(input);
      if (url.includes("/wrong-answers?")) return response({ items: [wrong], total: 1, page: 1, page_size: 100, pages: 1 });
      if (url.endsWith("/wrong-answers/review")) return response(attemptBase, 201);
      if (url.endsWith("/quiz-attempts/3")) return response(attemptBase);
      return response([]);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp(<App />, "/wrong-answers");

    expect(await screen.findByText("Tools 由谁调用？")).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText("选择错题 5"));
    await userEvent.click(screen.getByRole("button", { name: /复习所选/ }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/wrong-answers/review"),
        expect.objectContaining({ method: "POST" }),
      ),
    );
  });
});
