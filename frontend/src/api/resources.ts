import { api, jsonBody, streamPost } from "./client";
import type {
  Course,
  ActivityDetail,
  ActivityPage,
  DailyTask,
  KnowledgePoint,
  KnowledgePointChangeResult,
  KnowledgePointImpact,
  LearningGoal,
  LearningSession,
  Lesson,
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
  AgentConversationContext,
  AgentConversationDetail,
  AgentRun,
  AdaptiveRecommendation,
  AdaptiveReview,
  MasteryDetail,
  MasteryPageData,
  WeakPoint,
  Note,
  NoteLink,
  NotePage,
  NoteSource,
  MaintenanceStatus,
  EffectiveMaterial,
  KnowledgePointSource,
  MaterialLearningBatchResult,
  MaterialLearningContext,
  MaterialLearningLink,
  MaterialRelationType,
  MaterialTargetType,
  SourceChunkPage,
  CourseArchitectureDraft,
  CourseArchitectureDraftList,
  CourseArchitecturePublishResult,
  CourseArchitectureQualityReport,
  DiagnosticHistory,
  DiagnosticSession,
  StudyPlan,
  StudyPlanHistory,
  StudyPlanPublishResult,
  NextLearningAction,
  NextActionAcceptResult,
  LearningRuntimeRequest,
  LearningRuntimeResponse,
  CurriculumProposal,
  CurriculumPublishResult,
  PlanAdjustmentProposal,
} from "../types";

export const goalsApi = {
  list: () => api<LearningGoal[]>("/learning-goals"),
  get: (id: number) => api<LearningGoal>(`/learning-goals/${id}`),
  create: (data: unknown) => api<LearningGoal>("/learning-goals", { method: "POST", ...jsonBody(data) }),
  update: (id: number, data: unknown) =>
    api<LearningGoal>(`/learning-goals/${id}`, { method: "PATCH", ...jsonBody(data) }),
  remove: (id: number) => api<void>(`/learning-goals/${id}`, { method: "DELETE" }),
};

export const curriculumApi = {
  generate: (goalId: number) =>
    api<CurriculumProposal>(`/learning-goals/${goalId}/curriculum-proposals`, {
      method: "POST",
      ...jsonBody({ request_id: crypto.randomUUID() }),
    }),
  get: (proposalId: string) =>
    api<CurriculumProposal>(`/curriculum-proposals/${proposalId}`),
  decide: (
    proposalId: string,
    decision: "accept" | "reject",
    expectedVersion: number,
  ) =>
    api<CurriculumProposal>(`/curriculum-proposals/${proposalId}/decision`, {
      method: "POST",
      ...jsonBody({
        decision,
        expected_version: expectedVersion,
        request_id: crypto.randomUUID(),
        confirmed: true,
      }),
    }),
  publish: (proposal: CurriculumProposal) =>
    api<CurriculumPublishResult>(
      `/curriculum-proposals/${proposal.proposal_id}/publish`,
      {
        method: "POST",
        ...jsonBody({
          expected_proposal_version: proposal.version,
          draft_version: proposal.architecture.version,
          publish_request_id: crypto.randomUUID(),
          confirmed: true,
        }),
      },
    ),
};

export const materialsApi = {
  get: (id: number) => api<Material>(`/materials/${id}`),
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
  retryDelete: (id: number) => api<MaintenanceStatus>(`/materials/${id}/delete/retry`, { method: "POST" }),
  process: (id: number) =>
    api<Material>(`/materials/${id}/process`, { method: "POST" }),
  archive: (id: number) => api<Material>(`/materials/${id}/archive`, { method: "POST" }),
  unarchive: (id: number) => api<Material>(`/materials/${id}/unarchive`, { method: "POST" }),
  archiveBulk: (materialIds: number[]) =>
    api<{ archived_ids: number[] }>("/materials/archive/bulk", {
      method: "POST", ...jsonBody({ material_ids: materialIds }),
    }),
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

export type MaterialLinkInput = {
  target_type: MaterialTargetType;
  learning_goal_id?: number;
  course_id?: number;
  knowledge_point_id?: number;
  relation_type: MaterialRelationType;
  is_primary: boolean;
};

export const materialLearningApi = {
  all: (materialIds?: number[]) =>
    api<MaterialLearningContext[]>(
      `/material-learning-links${materialIds ? `?material_ids=${materialIds.join(",")}` : ""}`,
    ),
  list: (materialId: number) =>
    api<MaterialLearningLink[]>(`/materials/${materialId}/learning-links`),
  create: (materialId: number, data: MaterialLinkInput) =>
    api<MaterialLearningLink>(`/materials/${materialId}/learning-links`, {
      method: "POST", ...jsonBody(data),
    }),
  update: (materialId: number, linkId: number, data: { relation_type?: MaterialRelationType; is_primary?: boolean }) =>
    api<MaterialLearningLink>(`/materials/${materialId}/learning-links/${linkId}`, {
      method: "PATCH", ...jsonBody(data),
    }),
  remove: (materialId: number, linkId: number) =>
    api<void>(`/materials/${materialId}/learning-links/${linkId}`, { method: "DELETE" }),
  bulkMaterials: (materialIds: number[], link: MaterialLinkInput) =>
    api<MaterialLearningBatchResult>("/material-learning-links/bulk-materials", {
      method: "POST", ...jsonBody({ material_ids: materialIds, link }),
    }),
  goalMaterials: (id: number) => api<EffectiveMaterial[]>(`/learning-goals/${id}/materials`),
  courseMaterials: (id: number) => api<EffectiveMaterial[]>(`/courses/${id}/materials`),
  pointMaterials: (id: number) => api<EffectiveMaterial[]>(`/knowledge-points/${id}/materials`),
};

export const knowledgePointSourcesApi = {
  list: (pointId: number) => api<KnowledgePointSource[]>(`/knowledge-points/${pointId}/sources`),
  chunks: (pointId: number, materialId: number, search = "", page = 1) => {
    const params = new URLSearchParams({ material_id: String(materialId), page: String(page), page_size: "20" });
    if (search) params.set("search", search);
    return api<SourceChunkPage>(`/knowledge-points/${pointId}/source-chunks?${params}`);
  },
  create: (pointId: number, data: unknown) =>
    api<KnowledgePointSource>(`/knowledge-points/${pointId}/sources`, { method: "POST", ...jsonBody(data) }),
  remove: (pointId: number, sourceId: number) =>
    api<void>(`/knowledge-points/${pointId}/sources/${sourceId}`, { method: "DELETE" }),
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
  getPoint: (id: number) => api<KnowledgePoint>(`/knowledge-points/${id}`),
  inspectPoint: (
    id: number,
    data: { action: "archive" | "supersede"; superseded_by_id?: number | null; lifecycle_reason: string },
  ) => api<KnowledgePointImpact>(`/knowledge-points/${id}/impact`, { method: "POST", ...jsonBody(data) }),
  archivePoint: (id: number, data: unknown) =>
    api<KnowledgePointChangeResult>(`/knowledge-points/${id}/archive`, { method: "POST", ...jsonBody(data) }),
  supersedePoint: (id: number, data: unknown) =>
    api<KnowledgePointChangeResult>(`/knowledge-points/${id}/supersede`, { method: "POST", ...jsonBody(data) }),
};

export const diagnosticsApi = {
  latest: (courseId: number) =>
    api<DiagnosticSession | null>(`/courses/${courseId}/diagnostics/latest`),
  history: (courseId: number) =>
    api<DiagnosticHistory>(`/courses/${courseId}/diagnostics/history`),
  get: (id: number) => api<DiagnosticSession>(`/diagnostics/${id}`),
  create: (courseId: number, data: unknown) =>
    api<DiagnosticSession>(`/courses/${courseId}/diagnostics`, {
      method: "POST", ...jsonBody(data),
    }),
  reassess: (courseId: number, data: unknown) =>
    api<DiagnosticSession>(`/courses/${courseId}/diagnostics/reassess`, {
      method: "POST", ...jsonBody(data),
    }),
  saveAnswer: (diagnosticId: number, questionId: number, data: unknown) =>
    api<DiagnosticSession>(`/diagnostics/${diagnosticId}/answers/${questionId}`, {
      method: "PUT", ...jsonBody(data),
    }),
  submit: (diagnosticId: number, data: unknown) =>
    api<DiagnosticSession>(`/diagnostics/${diagnosticId}/submit`, {
      method: "POST", ...jsonBody(data),
    }),
};

export const studyPlansApi = {
  create: (data: unknown) =>
    api<StudyPlan>("/study-plans", { method: "POST", ...jsonBody(data) }),
  get: (id: number) => api<StudyPlan>(`/study-plans/${id}`),
  active: (learningGoalId?: number, courseId?: number) => {
    const params = new URLSearchParams();
    if (learningGoalId) params.set("learning_goal_id", String(learningGoalId));
    if (courseId) params.set("course_id", String(courseId));
    return api<StudyPlan | null>(`/study-plans/active${params.size ? `?${params}` : ""}`);
  },
  history: (id: number) => api<StudyPlanHistory>(`/study-plans/${id}/versions`),
  publish: (id: number, expectedVersion: number, requestId: string) =>
    api<StudyPlanPublishResult>(`/study-plans/${id}/publish`, {
      method: "POST",
      ...jsonBody({ request_id: requestId, expected_version: expectedVersion, confirmed: true }),
    }),
  replan: (id: number, data: unknown) =>
    api<StudyPlan>(`/study-plans/${id}/replan`, { method: "POST", ...jsonBody(data) }),
  cancel: (id: number, expectedVersion: number, requestId: string) =>
    api<StudyPlan>(`/study-plans/${id}/cancel`, {
      method: "POST",
      ...jsonBody({ request_id: requestId, expected_version: expectedVersion, confirmed: true }),
    }),
};

export const nextActionApi = {
  get: (availableMinutes?: number) =>
    api<NextLearningAction>(
      `/next-learning-action${availableMinutes ? `?available_minutes=${availableMinutes}` : ""}`,
    ),
  accept: (actionSignature: string, requestId: string, availableMinutes?: number) =>
    api<NextActionAcceptResult>("/next-learning-action/accept", {
      method: "POST",
      ...jsonBody({
        request_id: requestId,
        action_signature: actionSignature,
        available_minutes: availableMinutes ?? null,
      }),
    }),
};

export const planAdjustmentsApi = {
  get: (proposalId: string) =>
    api<PlanAdjustmentProposal>(`/plan-adjustments/${proposalId}`),
  decide: (
    proposal: PlanAdjustmentProposal,
    decision: "accept" | "reject",
  ) =>
    api<PlanAdjustmentProposal>(
      `/plan-adjustments/${proposal.proposal_id}/decision`,
      {
        method: "POST",
        ...jsonBody({
          request_id: crypto.randomUUID(),
          decision,
          expected_version: proposal.version,
          context_version: proposal.context_version,
          confirmed: true,
        }),
      },
    ),
};

export const courseArchitectureApi = {
  list: (includeArchived = false) =>
    api<CourseArchitectureDraftList>(`/course-architecture/drafts?include_archived=${includeArchived}`),
  get: (id: number) => api<CourseArchitectureDraft>(`/course-architecture/drafts/${id}`),
  create: (data: { learning_goal_id: number; material_ids: number[]; title?: string; description?: string }) =>
    api<CourseArchitectureDraft>("/course-architecture/drafts", { method: "POST", ...jsonBody(data) }),
  createVersion: (id: number) =>
    api<CourseArchitectureDraft>(`/course-architecture/drafts/${id}/versions`, { method: "POST" }),
  update: (id: number, data: unknown) =>
    api<CourseArchitectureDraft>(`/course-architecture/drafts/${id}`, { method: "PATCH", ...jsonBody(data) }),
  archive: (id: number, version: number) =>
    api<void>(`/course-architecture/drafts/${id}?version=${version}`, { method: "DELETE" }),
  replaceMaterials: (id: number, version: number, materialIds: number[]) =>
    api<CourseArchitectureDraft>(`/course-architecture/drafts/${id}/materials`, { method: "PUT", ...jsonBody({ version, material_ids: materialIds }) }),
  addCourse: (id: number, data: unknown) =>
    api<CourseArchitectureDraft>(`/course-architecture/drafts/${id}/courses`, { method: "POST", ...jsonBody(data) }),
  updateCourse: (id: number, courseId: number, data: unknown) =>
    api<CourseArchitectureDraft>(`/course-architecture/drafts/${id}/courses/${courseId}`, { method: "PATCH", ...jsonBody(data) }),
  removeCourse: (id: number, courseId: number, version: number) =>
    api<CourseArchitectureDraft>(`/course-architecture/drafts/${id}/courses/${courseId}?version=${version}`, { method: "DELETE" }),
  reorderCourses: (id: number, version: number, items: Array<{ id: number; order_index: number }>) =>
    api<CourseArchitectureDraft>(`/course-architecture/drafts/${id}/courses/reorder`, { method: "POST", ...jsonBody({ version, items }) }),
  addPoint: (id: number, data: unknown) =>
    api<CourseArchitectureDraft>(`/course-architecture/drafts/${id}/knowledge-points`, { method: "POST", ...jsonBody(data) }),
  updatePoint: (id: number, pointId: number, data: unknown) =>
    api<CourseArchitectureDraft>(`/course-architecture/drafts/${id}/knowledge-points/${pointId}`, { method: "PATCH", ...jsonBody(data) }),
  removePoint: (id: number, pointId: number, version: number) =>
    api<CourseArchitectureDraft>(`/course-architecture/drafts/${id}/knowledge-points/${pointId}?version=${version}`, { method: "DELETE" }),
  reorderPoints: (id: number, version: number, items: Array<{ id: number; order_index: number }>) =>
    api<CourseArchitectureDraft>(`/course-architecture/drafts/${id}/knowledge-points/reorder`, { method: "POST", ...jsonBody({ version, items }) }),
  movePoint: (id: number, data: unknown) =>
    api<CourseArchitectureDraft>(`/course-architecture/drafts/${id}/knowledge-points/move`, { method: "POST", ...jsonBody(data) }),
  mergePoints: (id: number, data: unknown) =>
    api<CourseArchitectureDraft>(`/course-architecture/drafts/${id}/knowledge-points/merge`, { method: "POST", ...jsonBody(data) }),
  addSource: (id: number, pointId: number, data: unknown) =>
    api<CourseArchitectureDraft>(`/course-architecture/drafts/${id}/knowledge-points/${pointId}/sources`, { method: "POST", ...jsonBody(data) }),
  removeSource: (id: number, sourceId: number, version: number) =>
    api<CourseArchitectureDraft>(`/course-architecture/drafts/${id}/sources/${sourceId}?version=${version}`, { method: "DELETE" }),
  addPrerequisite: (id: number, data: unknown) =>
    api<CourseArchitectureDraft>(`/course-architecture/drafts/${id}/prerequisites`, { method: "POST", ...jsonBody(data) }),
  removePrerequisite: (id: number, edgeId: number, version: number) =>
    api<CourseArchitectureDraft>(`/course-architecture/drafts/${id}/prerequisites/${edgeId}?version=${version}`, { method: "DELETE" }),
  quality: (id: number) => api<CourseArchitectureQualityReport>(`/course-architecture/drafts/${id}/quality-report`),
  validate: (id: number, version: number) =>
    api<CourseArchitectureDraft>(`/course-architecture/drafts/${id}/validate`, { method: "POST", ...jsonBody({ version }) }),
  generate: (id: number, version: number, requestId: string) =>
    api<CourseArchitectureDraft>(`/course-architecture/drafts/${id}/generate`, { method: "POST", ...jsonBody({ version, request_id: requestId }) }),
  cancel: (id: number, version: number) =>
    api<CourseArchitectureDraft>(`/course-architecture/drafts/${id}/generate/cancel`, { method: "POST", ...jsonBody({ version }) }),
  publish: (id: number, version: number, publishRequestId: string) =>
    api<CourseArchitecturePublishResult>(`/course-architecture/drafts/${id}/publish`, { method: "POST", ...jsonBody({ version, publish_request_id: publishRequestId, confirmed: true }) }),
};

export const dashboardApi = {
  today: () => api<TodayData>("/today"),
  progress: () => api<ProgressData>("/progress"),
  reviews: () => api<ReviewData>("/review-items"),
  meta: () => api<MetaData>("/meta"),
};

export const notesApi = {
  list: (filters: {
    q?: string;
    noteType?: string;
    tag?: string;
    pinned?: boolean;
    archived?: boolean;
    entityType?: string;
    entityId?: number;
    pageSize?: number;
  } = {}) => {
    const params = new URLSearchParams({
      page: "1",
      page_size: String(filters.pageSize ?? 100),
      sort: "updated_desc",
    });
    if (filters.q) params.set("q", filters.q);
    if (filters.noteType) params.set("note_type", filters.noteType);
    if (filters.tag) params.set("tag", filters.tag);
    if (filters.pinned !== undefined) params.set("pinned", String(filters.pinned));
    if (filters.archived !== undefined) params.set("archived", String(filters.archived));
    if (filters.entityType && filters.entityId) {
      params.set("entity_type", filters.entityType);
      params.set("entity_id", String(filters.entityId));
    }
    return api<NotePage>(`/notes?${params}`);
  },
  get: (id: number) => api<Note>(`/notes/${id}`),
  create: (data: unknown) => api<Note>("/notes", { method: "POST", ...jsonBody(data) }),
  update: (id: number, data: unknown) =>
    api<Note>(`/notes/${id}`, { method: "PATCH", ...jsonBody(data) }),
  archive: (id: number) => api<void>(`/notes/${id}`, { method: "DELETE" }),
  remove: (id: number) =>
    api<void>(`/notes/${id}?permanent=true&confirmed=true`, { method: "DELETE" }),
  addLink: (id: number, data: unknown) =>
    api<NoteLink>(`/notes/${id}/links`, { method: "POST", ...jsonBody(data) }),
  removeLink: (noteId: number, linkId: number) =>
    api<void>(`/notes/${noteId}/links/${linkId}`, { method: "DELETE" }),
  addSource: (id: number, data: unknown) =>
    api<NoteSource>(`/notes/${id}/sources`, { method: "POST", ...jsonBody(data) }),
  removeSource: (noteId: number, sourceId: number) =>
    api<void>(`/notes/${noteId}/sources/${sourceId}`, { method: "DELETE" }),
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

export const lessonsApi = {
  list: (courseId: number) => api<Lesson[]>(`/courses/${courseId}/lessons`),
  get: (id: number) => api<Lesson>(`/lessons/${id}`),
  create: (courseId: number, data: unknown) =>
    api<Lesson>(`/courses/${courseId}/lessons`, { method: "POST", ...jsonBody(data) }),
  generate: (id: number, data: unknown) =>
    api<Lesson>(`/lessons/${id}/generate`, { method: "POST", ...jsonBody(data) }),
  publish: (id: number, versionNumber: number, expectedVersionNumber: number) =>
    api<Lesson>(`/lessons/${id}/versions/${versionNumber}/publish`, {
      method: "POST",
      ...jsonBody({ expected_version_number: expectedVersionNumber, confirmed: true }),
    }),
  archive: (id: number) =>
    api<Lesson>(`/lessons/${id}/archive`, {
      method: "POST",
      ...jsonBody({ confirmed: true }),
    }),
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
      learning_goal_id?: number | null;
      course_id?: number | null;
      knowledge_point_id?: number | null;
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
  forContext: (courseId: number, knowledgePointId: number) =>
    api<ActivityPage>(
      `/learning-activities?page=1&page_size=100&course_id=${courseId}&knowledge_point_id=${knowledgePointId}`,
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
  list: (context: AgentConversationContext = { context_type: "general", context_id: null }) => {
    const query = context.context_type === "general"
      ? "?context_type=general"
      : `?context_type=${context.context_type}&context_id=${context.context_id}`;
    return api<AgentConversation[]>(`/agent/conversations${query}`);
  },
  get: (id: number) => api<AgentConversationDetail>(`/agent/conversations/${id}`),
  create: (title = "新建学习助手会话", context: AgentConversationContext = { context_type: "general", context_id: null }) =>
    api<AgentConversation>("/agent/conversations", { method: "POST", ...jsonBody({ title, context }) }),
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

export const learningRuntimeApi = {
  run: (data: LearningRuntimeRequest) =>
    api<LearningRuntimeResponse>("/learning/runtime/runs", {
      method: "POST",
      ...jsonBody(data),
    }),
  resume: (runId: string, decision: "approve" | "reject", requestId: string) =>
    api<LearningRuntimeResponse>(`/learning/runtime/runs/${runId}/resume`, {
      method: "POST",
      ...jsonBody({ decision, request_id: requestId }),
    }),
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
  refreshStatus: (knowledgePointId: number) =>
    api<MaintenanceStatus>(`/adaptive-recommendations/refresh-status/${knowledgePointId}`),
  retryRefresh: (taskId: number) =>
    api<MaintenanceStatus>(`/adaptive-recommendations/refresh-tasks/${taskId}/retry`, { method: "POST" }),
};
