import { api, jsonBody, streamPost } from "./client";
import type {
  Course,
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
