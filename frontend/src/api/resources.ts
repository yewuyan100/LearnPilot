import { api, jsonBody, streamPost } from "./client";
import type {
  Course,
  ActivityDetail,
  ActivityPage,
  DailyTask,
  KnowledgePoint,
  LearningGoal,
  LearningSession,
  Material,
  MaterialChunkPage,
  MaterialIndexBuildResult,
  MaterialIndexStatus,
  MaterialSearchResponse,
  MetaData,
  ProgressData,
  RagConversation,
  RagConversationDetail,
  RagConversationPage,
  RagStatus,
  ReviewData,
  TodayData,
  QuizAttempt,
  WrongAnswer,
  WrongAnswerPage,
  AgentConversation,
  AgentConversationDetail,
  AgentRun,
  AdaptiveRecommendation,
  AdaptiveReview,
  MasteryDetail,
  MasteryPageData,
  WeakPoint,
} from "../types";

export const goalsApi = {
  list: () => api<LearningGoal[]>("/learning-goals"),
  create: (data: unknown) => api<LearningGoal>("/learning-goals", { method: "POST", ...jsonBody(data) }),
  update: (id: number, data: unknown) =>
    api<LearningGoal>(`/learning-goals/${id}`, { method: "PATCH", ...jsonBody(data) }),
  remove: (id: number) => api<void>(`/learning-goals/${id}`, { method: "DELETE" }),
};

export const materialsApi = {
  list: (search = "", sourceType = "") => {
    const params = new URLSearchParams();
    if (search) params.set("search", search);
    if (sourceType) params.set("source_type", sourceType);
    return api<Material[]>(`/materials?${params}`);
  },
  upload: (file: File) => {
    const data = new FormData();
    data.append("file", file);
    return api<Material>("/materials/upload", { method: "POST", body: data });
  },
  remove: (id: number) => api<void>(`/materials/${id}`, { method: "DELETE" }),
  process: (id: number) =>
    api<Material>(`/materials/${id}/process`, { method: "POST" }),
  chunks: (id: number, page = 1, pageSize = 20) =>
    api<MaterialChunkPage>(
      `/materials/${id}/chunks?page=${page}&page_size=${pageSize}`,
    ),
  indexStatus: () => api<MaterialIndexStatus>("/materials/index/status"),
  rebuildIndex: () =>
    api<MaterialIndexBuildResult>("/materials/index/rebuild", { method: "POST" }),
  search: (data: {
    query: string;
    top_k: number;
    material_ids: number[] | null;
    min_score?: number | null;
  }) =>
    api<MaterialSearchResponse>("/materials/search", {
      method: "POST",
      ...jsonBody(data),
    }),
};

export const coursesApi = {
  list: () => api<Course[]>("/courses"),
  get: (id: number) => api<Course>(`/courses/${id}`),
  create: (data: unknown) => api<Course>("/courses", { method: "POST", ...jsonBody(data) }),
  update: (id: number, data: unknown) =>
    api<Course>(`/courses/${id}`, { method: "PATCH", ...jsonBody(data) }),
  remove: (id: number) => api<void>(`/courses/${id}`, { method: "DELETE" }),
  points: (id: number) => api<KnowledgePoint[]>(`/courses/${id}/knowledge-points`),
  createPoint: (id: number, data: unknown) =>
    api<KnowledgePoint>(`/courses/${id}/knowledge-points`, { method: "POST", ...jsonBody(data) }),
  updatePoint: (id: number, data: unknown) =>
    api<KnowledgePoint>(`/knowledge-points/${id}`, { method: "PATCH", ...jsonBody(data) }),
  removePoint: (id: number) => api<void>(`/knowledge-points/${id}`, { method: "DELETE" }),
};

export const dashboardApi = {
  today: () => api<TodayData>("/today"),
  progress: () => api<ProgressData>("/progress"),
  reviews: () => api<ReviewData>("/review-items"),
  meta: () => api<MetaData>("/meta"),
};

export const tasksApi = {
  create: (data: unknown) => api<DailyTask>("/daily-tasks", { method: "POST", ...jsonBody(data) }),
  update: (id: number, data: unknown) =>
    api<DailyTask>(`/daily-tasks/${id}`, { method: "PATCH", ...jsonBody(data) }),
  remove: (id: number) => api<void>(`/daily-tasks/${id}`, { method: "DELETE" }),
};

export const sessionsApi = {
  list: () => api<LearningSession[]>("/learning-sessions"),
  get: (id: number) => api<LearningSession>(`/learning-sessions/${id}`),
  create: (data: unknown) =>
    api<LearningSession>("/learning-sessions", { method: "POST", ...jsonBody(data) }),
  update: (id: number, data: unknown) =>
    api<LearningSession>(`/learning-sessions/${id}`, { method: "PATCH", ...jsonBody(data) }),
};

export const demoApi = {
  seed: () => api<LearningGoal>("/demo-data", { method: "POST" }),
  clear: () => api<{ deleted_goals: number }>("/demo-data", { method: "DELETE" }),
};

export const ragApi = {
  status: () => api<RagStatus>("/rag/status"),
  list: () =>
    api<RagConversationPage>("/rag/conversations?page=1&page_size=100&status=active"),
  get: (id: number) => api<RagConversationDetail>(`/rag/conversations/${id}`),
  create: (title = "新建资料问答") =>
    api<RagConversation>("/rag/conversations", {
      method: "POST",
      ...jsonBody({ title }),
    }),
  archive: (id: number) =>
    api<void>(`/rag/conversations/${id}`, { method: "DELETE" }),
  stream: (
    id: number,
    payload: {
      question: string;
      request_id: string;
      top_k?: number;
      material_ids?: number[] | null;
    },
    signal: AbortSignal,
    onEvent: (event: string, data: unknown) => void,
  ) => streamPost(`/rag/conversations/${id}/stream`, payload, signal, onEvent),
};

export const activitiesApi = {
  list: (status = "") =>
    api<ActivityPage>(
      `/learning-activities?page=1&page_size=100${status ? `&status=${status}` : ""}`,
    ),
  get: (id: number) => api<ActivityDetail>(`/learning-activities/${id}`),
  generate: (data: unknown) =>
    api<ActivityDetail>("/learning-activities/generate", {
      method: "POST",
      ...jsonBody(data),
    }),
  update: (id: number, data: unknown) =>
    api<ActivityDetail>(`/learning-activities/${id}`, {
      method: "PATCH",
      ...jsonBody(data),
    }),
  deleteQuestion: (activityId: number, questionId: number) =>
    api<ActivityDetail>(
      `/learning-activities/${activityId}/questions/${questionId}`,
      { method: "DELETE" },
    ),
  reorder: (id: number, questionIds: number[]) =>
    api<ActivityDetail>(`/learning-activities/${id}/questions/reorder`, {
      method: "POST",
      ...jsonBody({ question_ids: questionIds }),
    }),
  publish: (id: number) =>
    api<ActivityDetail>(`/learning-activities/${id}/publish`, { method: "POST" }),
  start: (id: number, learningSessionId: number | null = null) =>
    api<QuizAttempt>(`/learning-activities/${id}/attempts`, {
      method: "POST",
      ...jsonBody({ learning_session_id: learningSessionId }),
    }),
};

export const attemptsApi = {
  get: (id: number) => api<QuizAttempt>(`/quiz-attempts/${id}`),
  save: (
    attemptId: number,
    questionId: number,
    data: { answer?: Array<string | boolean> | null; answer_text?: string | null },
  ) =>
    api<QuizAttempt>(`/quiz-attempts/${attemptId}/answers/${questionId}`, {
      method: "PUT",
      ...jsonBody(data),
    }),
  submit: (
    id: number,
    data: {
      request_id: string;
      answers: Array<{
        question_id: number;
        answer?: Array<string | boolean> | null;
        answer_text?: string | null;
      }>;
    },
  ) =>
    api<QuizAttempt>(`/quiz-attempts/${id}/submit`, {
      method: "POST",
      ...jsonBody(data),
    }),
};

export const wrongAnswersApi = {
  list: (status = "") =>
    api<WrongAnswerPage>(
      `/wrong-answers?page=1&page_size=100${status ? `&status=${status}` : ""}`,
    ),
  get: (id: number) => api<WrongAnswer>(`/wrong-answers/${id}`),
  update: (id: number, status: "active" | "resolved" | "dismissed") =>
    api<WrongAnswer>(`/wrong-answers/${id}`, {
      method: "PATCH",
      ...jsonBody({ status }),
    }),
  review: (wrongAnswerIds: number[]) =>
    api<QuizAttempt>("/wrong-answers/review", {
      method: "POST",
      ...jsonBody({
        wrong_answer_ids: wrongAnswerIds,
        request_id: crypto.randomUUID(),
      }),
    }),
};

export const agentApi = {
  list: () => api<AgentConversation[]>("/agent/conversations"),
  get: (id: number) => api<AgentConversationDetail>(`/agent/conversations/${id}`),
  create: (title = "新建学习助手会话") =>
    api<AgentConversation>("/agent/conversations", { method: "POST", ...jsonBody({ title }) }),
  archive: (id: number) =>
    api<AgentConversation>(`/agent/conversations/${id}/archive`, { method: "POST" }),
  run: (conversationId: number, input: string, requestId: string) =>
    api<AgentRun>(`/agent/conversations/${conversationId}/runs`, {
      method: "POST", ...jsonBody({ input, request_id: requestId }),
    }),
  stream: (conversationId: number, input: string, requestId: string, signal: AbortSignal,
    onEvent: (event: string, data: unknown) => void) =>
    streamPost(`/agent/conversations/${conversationId}/runs/stream`, { input, request_id: requestId }, signal, onEvent),
  confirm: (runId: number, decision: "approve" | "reject") =>
    api<AgentRun>(`/agent/runs/${runId}/confirm`, { method: "POST", ...jsonBody({ decision }) }),
};

export const masteryApi = {
  list: () => api<MasteryPageData>("/mastery?page=1&page_size=100&sort=weakness"),
  get: (knowledgePointId: number) => api<MasteryDetail>(`/mastery/${knowledgePointId}`),
  weakPoints: () => api<WeakPoint[]>("/mastery/weak-points?limit=100&include_unassessed=true"),
  rebuild: () => api<{ processed: number }>("/mastery/rebuild", {
    method: "POST", ...jsonBody({ course_id: null, knowledge_point_id: null }),
  }),
  selfAssessment: (knowledgePointId: number, rating: number) =>
    api<MasteryDetail>(`/mastery/${knowledgePointId}/self-assessment`, {
      method: "PUT", ...jsonBody({ rating, request_id: crypto.randomUUID() }),
    }),
};

export const adaptiveApi = {
  reviews: () => api<AdaptiveReview[]>("/reviews?limit=200"),
  recommendations: (status = "pending") =>
    api<AdaptiveRecommendation[]>(`/adaptive-recommendations?status=${status}`),
  accept: (id: number) => api<{
    recommendation: AdaptiveRecommendation;
    task: DailyTask;
    idempotent_replay: boolean;
  }>(`/adaptive-recommendations/${id}/accept`, {
    method: "POST", ...jsonBody({ request_id: crypto.randomUUID(), confirmed: true }),
  }),
  reject: (id: number) =>
    api<AdaptiveRecommendation>(`/adaptive-recommendations/${id}/reject`, { method: "POST" }),
};
