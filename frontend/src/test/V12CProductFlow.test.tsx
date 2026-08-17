import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { prepareFirstLesson, prepareLessonAssessment } from "../api/productFlow";
import { activitiesApi, coursesApi, lessonsApi } from "../api/resources";
import type { CurriculumProposal, Lesson, LessonVersion } from "../types";
import { renderApp } from "./render";

const now = "2026-08-08T08:00:00Z";
const proposal = {
  proposal_id: "route-1", proposal_type: "curriculum", status: "accepted", version: 2,
  context_version: null, generation_request_id: "generate-route-1",
  goal: { id: 1, title: "提升 AI 应用开发能力", description: "", current_level: "入门", target_date: null, daily_minutes: 30 },
  grounding_mode: "goal_only", material_ids: [],
  curriculum: {
    course_title: "AI 应用开发路线", course_description: "从应用边界开始。",
    knowledge_points: [{ title: "建立应用边界", description: "", learning_objectives: [], key_terms: [], difficulty_label: "beginner", source_chunk_ids: [] }],
    prerequisites: [], learning_order: ["建立应用边界"], estimated_duration: 30,
    lesson_blueprints: [{ knowledge_point: "建立应用边界", lesson_goal: "能够说明应用边界", estimated_minutes: 25, requires_lesson_generation: true }],
    assumptions: [], coverage_report: { goal_alignment: "", covered_topics: [], gaps: [], material_grounding: "goal_only_unverified" },
  },
  architecture: { draft_id: 1, public_id: "draft-1", version: 2, status: "published", quality_status: "ready", quality_report: { status: "ready", blocker_count: 0, warning_count: 0, info_count: 0, source_coverage: 0, issues: [] } },
  expires_at: null, decided_at: now, created_at: now, updated_at: now,
} as CurriculumProposal;

const readyVersion: LessonVersion = {
  id: 41, lesson_id: 21, version_number: 1, status: "ready", objectives: [], content_markdown: "内容",
  examples: [], guided_practice: [], checks: [], estimated_minutes: 25, source_snapshot_hash: "hash",
  generation_request_id: "lesson-generate-1", model_name: "test", prompt_version: "v1", quality_report: {},
  published_at: null, created_at: now, updated_at: now,
  knowledge_points: [{ knowledge_point_id: 13, title: "建立应用边界", order_index: 1, role: "primary" }], sources: [],
};
const draftLesson = {
  id: 21, public_id: "lesson-21", course_id: 12, course_title: "AI 应用开发路线", learning_goal_id: 1,
  title: "建立应用边界", description: "能够说明应用边界", order_index: 1, status: "draft",
  current_version_number: 0, active_version_number: null, latest_version: null, active_version: null,
  idempotent_replay: false, created_at: now, updated_at: now,
} as Lesson;
const publishedLesson = { ...draftLesson, status: "published", current_version_number: 1, active_version_number: 1, latest_version: { ...readyVersion, status: "published", published_at: now }, active_version: { ...readyVersion, status: "published", published_at: now } } as Lesson;

function json(data: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } }));
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("V12C 产品闭环", () => {
  it("Scenario A：确认路线后只准备第一步正式内容", async () => {
    vi.spyOn(coursesApi, "list").mockResolvedValue([{ id: 12, learning_goal_id: 1, learning_goal_title: proposal.goal.title, title: proposal.curriculum.course_title, description: "", status: "active", knowledge_point_count: 1, created_at: now, updated_at: now }]);
    vi.spyOn(coursesApi, "points").mockResolvedValue([{ id: 13, course_id: 12, title: "建立应用边界", description: "", order_index: 1, estimated_minutes: 25, status: "not_started", lifecycle_status: "active", superseded_by_id: null, lifecycle_reason: null, archived_at: null, version: 1, created_at: now, updated_at: now }]);
    vi.spyOn(lessonsApi, "list").mockResolvedValue([]);
    const create = vi.spyOn(lessonsApi, "create").mockResolvedValue(draftLesson);
    const generate = vi.spyOn(lessonsApi, "generate").mockResolvedValue({ ...draftLesson, current_version_number: 1, latest_version: readyVersion });
    const publish = vi.spyOn(lessonsApi, "publish").mockResolvedValue(publishedLesson);

    const result = await prepareFirstLesson(proposal, [12]);
    expect(result.lesson.id).toBe(21);
    expect(create).toHaveBeenCalledTimes(1);
    expect(generate).toHaveBeenCalledWith(21, expect.objectContaining({ knowledge_point_ids: [13], target_minutes: 25 }));
    expect(publish).toHaveBeenCalledWith(21, 1, 1);
  });

  it("Scenario B：Lesson 完成后复用正式练习链路并开始 Quiz", async () => {
    const lesson: Lesson = { ...publishedLesson, active_version: { ...publishedLesson.active_version!, sources: [{ material_id: 5, material_title: "来源", material_chunk_id: 8, source_role: "primary", source_locator: "第 1 节", quoted_text: "内容" }] } };
    vi.spyOn(activitiesApi, "forContext").mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100, pages: 0 });
    const generate = vi.spyOn(activitiesApi, "generate").mockResolvedValue({ id: 51, title: "理解检查", description: "", activity_type: "quiz", status: "draft", course_id: 12, knowledge_point_id: 13, course_title: "路线", knowledge_point_title: "边界", question_count: 5, total_points: 5, published_at: null, completed_attempt_count: 0, source_scope: {}, generation_request_id: "activity-generate-1", prompt_version: "v1", model_name: "test", validation_warnings: [], questions: [], created_at: now, updated_at: now });
    vi.spyOn(activitiesApi, "publish").mockResolvedValue({ id: 51, title: "理解检查", description: "", activity_type: "quiz", status: "published", course_id: 12, knowledge_point_id: 13, course_title: "路线", knowledge_point_title: "边界", question_count: 5, total_points: 5, published_at: now, completed_attempt_count: 0, source_scope: {}, generation_request_id: "activity-generate-1", prompt_version: "v1", model_name: "test", validation_warnings: [], questions: [], created_at: now, updated_at: now });
    const start = vi.spyOn(activitiesApi, "start").mockResolvedValue({ id: 61, activity_id: 51, activity_title: "理解检查", learning_session_id: 77, request_id: null, status: "in_progress", started_at: now, submitted_at: null, graded_at: null, total_points: null, earned_points: null, score_percentage: null, correct_count: 0, incorrect_count: 0, partial_count: 0, grading_model: null, grading_prompt_version: null, error_message: null, questions: [], answers: [], idempotent_replay: false, created_at: now, updated_at: now });

    const attempt = await prepareLessonAssessment(lesson, 77);
    expect(generate).toHaveBeenCalledWith(expect.objectContaining({ source_mode: "materials", material_ids: [5], course_id: 12, knowledge_point_id: 13 }));
    expect(start).toHaveBeenCalledWith(51, 77);
    expect(attempt.id).toBe(61);
  });

  it("Scenario C：Quiz 反馈承接调整建议和下一步", async () => {
    vi.stubGlobal("fetch", vi.fn((input: string | URL) => {
      const url = String(input);
      if (url.endsWith("/quiz-attempts/31")) return json({ id: 31, activity_id: 9, activity_title: "边界理解检查", learning_session_id: 7, status: "completed", started_at: now, submitted_at: now, graded_at: now, total_points: 5, earned_points: 3, score_percentage: 60, correct_count: 2, incorrect_count: 1, partial_count: 0, grading_model: "test", grading_prompt_version: "v1", error_message: null, questions: [], answers: [{ id: 1, question_id: 1, question_type: "short_answer", stem: "边界是什么？", answer: null, answer_text: "限制", is_correct: false, grading_status: "completed", earned_points: 0, max_points: 1, feedback: "补充输入与输出约束", matched_rubric_items: [], missing_rubric_items: ["输入约束"], grader_confidence: .9, correct_answer: null, reference_answer: "明确输入输出", grading_rubric: [], explanation: "边界限定责任", sources: [], wrong_answer_id: 2, wrong_answer_status: "active", created_at: now, updated_at: now }], idempotent_replay: false, created_at: now, updated_at: now });
      if (url.endsWith("/learning-activities/9")) return json({ id: 9, course_id: 12, knowledge_point_id: 13, status: "published" });
      if (url.endsWith("/courses/12")) return json({ id: 12, learning_goal_id: 1, title: "路线" });
      if (url.endsWith("/mastery/13")) return json({ mastery_level: "developing" });
      if (url.includes("/next-learning-action")) return json({ action_type: "review_proposal", learning_goal_id: 1, title: "调整接下来的安排", reason: "这次练习暴露了一个需要加强的步骤。", cta_label: "查看建议", cta_href: "/plan-adjustments/adjust-1" });
      return json({});
    }));
    renderApp(<App/>, "/quiz-attempts/31/result?origin=goal&goal_id=1");
    expect(await screen.findByText("这次表现")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "需要加强" })).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: /查看调整建议/ })).toHaveAttribute("href", "/plan-adjustments/adjust-1");
    expect(screen.queryByText(/Evidence|PlanVersion|MasteryChanged/)).not.toBeInTheDocument();
  });

  it("Scenario D：知识库默认聚合真实最近内容，并保留资料入口", async () => {
    vi.stubGlobal("fetch", vi.fn((input: string | URL) => {
      const url = String(input);
      if (url.includes("/materials?")) return json([{ id: 5, title: "AI 应用笔记", original_filename: "ai.md", stored_filename: "5.md", file_path: "hidden", source_type: "md", mime_type: "text/markdown", file_size: 100, processing_status: "completed", ingestion_status: "completed", indexing_status: "completed", chunk_count: 2, indexed_chunk_count: 2, processed_at: now, indexed_at: now, archived_at: null, error_message: null, deletion_status: "active", deletion_error: null, deletion_requested_at: null, deletion_attempts: 0, created_at: now, updated_at: now }]);
      if (url.includes("/notes?")) return json({ items: [{ id: 6, title: "资料问答整理", content_markdown: "回答", note_type: "study", status: "active", is_pinned: false, archived_at: null, tags: [], links: [{ id: 1, entity_type: "rag_message", entity_id: 8, relation_type: "derived_from", entity_title: "资料回答", source_available: true, created_at: now }], sources: [], created_at: now, updated_at: now }], total: 1, page: 1, page_size: 100, pages: 1 });
      return json([]);
    }));
    renderApp(<App/>, "/knowledge");
    expect(await screen.findByRole("heading", { name: "最近内容" })).toBeInTheDocument();
    expect(screen.queryByText("工作视图")).not.toBeInTheDocument();
    expect(screen.getByText("AI 整理")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "资料与来源" }));
    expect(await screen.findByRole("heading", { name: "资料与来源" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "ai.md" })).toHaveAttribute("href", "/materials/5");
  });

  it("Scenario E：AI 协作从无上下文、事项和资料入口工作且不要求选择 Agent", async () => {
    vi.stubGlobal("fetch", vi.fn((input: string | URL) => {
      const url = String(input);
      if (url.endsWith("/today")) return json({ date: "2026-08-08", current_goal: null, tasks: [], pending_count: 0, blocked_count: 0, recent_course: null, recent_session: null });
      if (url.endsWith("/learning-goals/1")) return json({ id: 1, title: proposal.goal.title, description: "", target_date: null, daily_minutes: 30, current_level: "入门", status: "active", is_demo: false, created_at: now, updated_at: now });
      if (url.endsWith("/materials/5")) return json({ id: 5, title: "AI 应用笔记", original_filename: "ai.md" });
      if (url.endsWith("/agent/conversations")) return json([]);
      if (url.endsWith("/courses")) return json([]);
      return json([]);
    }));
    renderApp(<App/>, "/ai");
    expect(await screen.findByRole("heading", { name: "你希望 AI 帮你做什么" })).toBeInTheDocument();
    expect(screen.getByText("尚未选择事项")).toBeInTheDocument();
    cleanup();
    renderApp(<App/>, "/ai?goal_id=1");
    expect(await screen.findByRole("heading", { name: proposal.goal.title })).toBeInTheDocument();
    cleanup();
    renderApp(<App/>, "/ai?material_id=5");
    expect(await screen.findByRole("heading", { name: "AI 应用笔记" })).toBeInTheDocument();
    expect(screen.getByText("理解与讨论")).toBeInTheDocument();
    expect(screen.getByText("结合资料思考")).toBeInTheDocument();
    expect(screen.getByText("推进事项")).toBeInTheDocument();
    expect(screen.queryByText(/Tutor Agent|Operations Agent|RAG Agent/)).not.toBeInTheDocument();
  });
});
