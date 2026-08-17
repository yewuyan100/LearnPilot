export interface Timestamped {
  id: number;
  created_at: string;
  updated_at: string;
}

export interface LearningGoal extends Timestamped {
  title: string;
  description: string;
  target_date: string | null;
  daily_minutes: number;
  current_level: string;
  status: string;
  is_demo: boolean;
}

export interface Material extends Timestamped {
  title: string;
  original_filename: string;
  stored_filename: string;
  file_path: string;
  source_type: string;
  mime_type: string;
  file_size: number;
  processing_status: string;
  ingestion_status: string;
  indexing_status: string;
  chunk_count: number;
  indexed_chunk_count: number;
  processed_at: string | null;
  indexed_at: string | null;
  archived_at?: string | null;
  error_message: string | null;
  deletion_status: "active" | "pending" | "failed";
  deletion_error: string | null;
  deletion_requested_at: string | null;
  deletion_attempts: number;
}

export interface MaterialChunk extends Timestamped {
  material_id: number;
  chunk_index: number;
  content: string;
  char_count: number;
  content_hash: string;
  page_number: number | null;
  section_title: string | null;
}

export interface MaterialChunkPage {
  items: MaterialChunk[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface MaterialIndexStatus {
  available: boolean;
  building: boolean;
  model_name: string;
  embedding_dimension: number | null;
  chunk_count: number;
  built_at: string | null;
  index_version: string | null;
  stale: boolean;
  error_message: string | null;
}

export interface MaterialIndexBuildResult {
  index_version: string | null;
  chunk_count: number;
  model_name: string;
  embedding_dimension: number | null;
  built_at: string | null;
}

export interface MaterialSearchResult {
  rank: number;
  score: number;
  chunk_id: number;
  material_id: number;
  original_filename: string;
  chunk_index: number;
  content: string;
  page_number: number | null;
  section_title: string | null;
}

export interface MaterialSearchResponse {
  query: string;
  model_name: string;
  index_version: string;
  results: MaterialSearchResult[];
  duration_ms: number;
  retrieved_count: number;
  filtered_count: number;
}

export interface Course extends Timestamped {
  learning_goal_id: number;
  learning_goal_title: string | null;
  title: string;
  description: string;
  status: string;
  knowledge_point_count: number;
}

export interface KnowledgePoint extends Timestamped {
  course_id: number;
  title: string;
  description: string;
  order_index: number;
  estimated_minutes: number;
  status: string;
  lifecycle_status: "active" | "archived" | "superseded";
  superseded_by_id: number | null;
  lifecycle_reason: string | null;
  archived_at: string | null;
  version: number;
}

export interface KnowledgePointImpact {
  knowledge_point_id: number;
  knowledge_point_title: string;
  course_id: number;
  point_version: number;
  lifecycle_status: string;
  action: "archive" | "supersede";
  superseded_by_id: number | null;
  prerequisite_edge_ids: number[];
  study_plan_ids: number[];
  study_plan_version_ids: number[];
  study_plan_item_ids: number[];
  daily_task_ids: number[];
  actionable_daily_task_ids: number[];
  learning_session_ids: number[];
  active_learning_session_ids: number[];
  activity_ids: number[];
  mastery_ids: number[];
  review_schedule_ids: number[];
  impact_hash: string;
  requires_confirmation: boolean;
}

export interface KnowledgePointChangeResult {
  point: KnowledgePoint;
  impact: KnowledgePointImpact;
  idempotent_replay: boolean;
}

export type MaterialTargetType = "learning_goal" | "course" | "knowledge_point";
export type MaterialRelationType = "reference" | "primary_source" | "supplementary" | "prerequisite" | "practice_source";

export interface MaterialLearningLink extends Timestamped {
  material_id: number;
  target_type: MaterialTargetType;
  target_id: number;
  target_title: string;
  relation_type: MaterialRelationType;
  is_primary: boolean;
}

export interface MaterialLearningContext extends MaterialLearningLink {
  material_title: string;
  original_filename: string;
  source_type: string;
  processing_status: string;
  ingestion_status: string;
  indexing_status: string;
  deletion_status: string;
  visibility: "direct" | "inherited" | "descendant";
}

export interface EffectiveMaterial {
  material_id: number;
  material_title: string;
  original_filename: string;
  source_type: string;
  processing_status: string;
  ingestion_status: string;
  indexing_status: string;
  deletion_status: string;
  contexts: MaterialLearningContext[];
}

export interface MaterialLearningBatchResult {
  requested: number;
  succeeded: number;
  failed: number;
  items: Array<{
    material_id: number;
    success: boolean;
    link: MaterialLearningLink | null;
    error_code: string | null;
    error_message: string | null;
  }>;
}

export interface KnowledgePointSource {
  id: number;
  knowledge_point_id: number;
  knowledge_point_title: string;
  material_id: number;
  material_title: string;
  original_filename: string;
  material_chunk_id: number | null;
  chunk_index: number | null;
  source_type: "material" | "chunk" | "manual_reference";
  source_locator: string | null;
  quoted_text: string | null;
  note: string | null;
  source_available: boolean;
  context_url: string;
  created_at: string;
  updated_at: string;
}

export interface SourceChunk {
  id: number;
  material_id: number;
  material_title: string;
  chunk_index: number;
  content: string;
  page_number: number | null;
  section_title: string | null;
  source_locator: string;
  previous_chunk_id: number | null;
  next_chunk_id: number | null;
}

export interface SourceChunkPage {
  items: SourceChunk[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface DailyTask extends Timestamped {
  learning_goal_id: number;
  course_id: number | null;
  knowledge_point_id: number | null;
  activity_id: number | null;
  title: string;
  task_type: string;
  estimated_minutes: number;
  scheduled_date: string;
  status: string;
  blocked_at: string | null;
  blocked_reason: string | null;
  blocked_source_type: string | null;
  blocked_source_id: number | null;
}

export interface LearningSession extends Timestamped {
  learning_goal_id: number;
  course_id: number | null;
  knowledge_point_id: number | null;
  daily_task_id: number | null;
  lesson_version_id: number | null;
  started_at: string;
  ended_at: string | null;
  status: string;
  notes: string;
  invalidated_at: string | null;
  invalidation_reason: string | null;
  goal_title: string | null;
  course_title: string | null;
  knowledge_point_title: string | null;
  task_title: string | null;
  lesson_id: number | null;
  lesson_title: string | null;
  lesson_version_number: number | null;
}

export interface LessonKnowledgePoint {
  knowledge_point_id: number;
  title: string;
  order_index: number;
  role: "primary" | "supporting" | "prerequisite_context";
}

export interface LessonSource {
  material_id: number;
  material_title: string;
  material_chunk_id: number | null;
  source_role: "primary" | "supporting";
  source_locator: string;
  quoted_text: string;
}

export interface LessonExample {
  title: string;
  explanation_markdown: string;
}

export interface LessonGuidedPractice {
  prompt: string;
  hint: string;
  expected_approach: string;
}

export interface LessonUnderstandingCheck {
  prompt: string;
  check_type: "reflection" | "single_choice" | "short_answer";
  options: string[];
  expected_concepts: string[];
}

export interface LessonVersion {
  id: number;
  lesson_id: number;
  version_number: number;
  status: string;
  objectives: string[];
  content_markdown: string;
  examples: LessonExample[];
  guided_practice: LessonGuidedPractice[];
  checks: LessonUnderstandingCheck[];
  estimated_minutes: number;
  source_snapshot_hash: string;
  generation_request_id: string;
  model_name: string;
  prompt_version: string;
  quality_report: Record<string, unknown>;
  published_at: string | null;
  created_at: string;
  updated_at: string;
  knowledge_points: LessonKnowledgePoint[];
  sources: LessonSource[];
}

export interface Lesson extends Timestamped {
  public_id: string;
  course_id: number;
  course_title: string;
  learning_goal_id: number;
  title: string;
  description: string;
  order_index: number;
  status: string;
  current_version_number: number;
  active_version_number: number | null;
  latest_version: LessonVersion | null;
  active_version: LessonVersion | null;
  idempotent_replay: boolean;
}

export interface TodayData {
  date: string;
  current_goal: null | {
    id: number;
    title: string;
    target_date: string | null;
    daily_minutes: number;
    current_level: string;
  };
  tasks: DailyTask[];
  pending_count: number;
  blocked_count: number;
  recent_course: null | { id: number; title: string; status: string };
  recent_session: null | {
    id: number;
    learning_goal_id: number;
    started_at: string;
    ended_at: string | null;
    status: string;
    notes: string;
  };
}

export interface ProgressData {
  goal_count: number;
  active_course_count: number;
  knowledge_point_count: number;
  completed_knowledge_point_count: number;
  today_task_total: number;
  today_task_completed: number;
  sessions_last_7_days: number;
  daily_sessions: Array<{ date: string; count: number }>;
  recent_sessions: Array<{
    id: number;
    started_at: string;
    ended_at: string | null;
    status: string;
    notes: string;
  }>;
}

export interface ReviewData {
  knowledge_points: Array<{
    id: number;
    course_id: number;
    title: string;
    status: string;
    estimated_minutes: number;
  }>;
  unfinished_tasks: Array<{
    id: number;
    title: string;
    scheduled_date: string;
    status: string;
    estimated_minutes: number;
  }>;
}

export interface MetaData {
  backend_status: string;
  database_type: string;
  upload_directory: string;
  allowed_file_types: string[];
  max_file_size_mb: number;
  app_version: string;
  demo_data_enabled: boolean;
  llm_configured: boolean;
  llm_model: string | null;
  embedding_model: string;
  embedding_device: string;
  embedding_local_only: boolean;
  index_ready: boolean;
  index_directory: string;
  server_date: string;
  server_time: string;
}

export interface RagConversation extends Timestamped {
  title: string;
  status: "active" | "archived";
  default_top_k: number | null;
  last_message_at: string | null;
}

export interface RagCitation {
  id: number;
  source_label: string;
  chunk_id: number | null;
  material_id: number | null;
  rank: number;
  score: number;
  original_filename: string;
  chunk_index: number;
  page_number: number | null;
  section_title: string | null;
  content_excerpt: string;
  source_available: boolean;
  learning_context: {
    requested_scope?: Record<string, number | number[] | null>;
    material_links?: Array<{
      target_type: MaterialTargetType;
      target_id: number;
      target_title: string;
      relation_type: MaterialRelationType;
    }>;
  };
  created_at: string;
}

export interface RagMessage extends Timestamped {
  conversation_id: number;
  reply_to_message_id: number | null;
  role: "user" | "assistant";
  content: string;
  status: "pending" | "completed" | "failed";
  request_id: string | null;
  original_query: string | null;
  retrieval_query: string | null;
  retrieval_scope: Record<string, unknown>;
  answerable: boolean | null;
  refusal_reason: string | null;
  prompt_version: string | null;
  model_name: string | null;
  latency_ms: number | null;
  citations: RagCitation[];
}

export interface RagConversationPage {
  items: RagConversation[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface RagConversationDetail extends RagConversation {
  messages: RagMessage[];
  message_total: number;
  message_page: number;
  message_page_size: number;
  message_pages: number;
}

export interface RagStatus {
  llm_configured: boolean;
  provider: string;
  model: string | null;
  index_available: boolean;
  index_stale: boolean;
  index_version: string | null;
  rag_prompt_version: string;
  rewrite_prompt_version: string;
}

export interface QuestionOption {
  id: string;
  text: string;
}

export interface RubricItem {
  criterion: string;
  points: number;
  required_concepts: string[];
}

export interface QuestionSource extends Timestamped {
  question_id: number;
  source_label: string;
  material_id: number | null;
  chunk_id: number | null;
  rank: number;
  score: number;
  original_filename: string;
  chunk_index: number;
  page_number: number | null;
  section_title: string | null;
  content_excerpt: string;
  source_available: boolean;
}

export interface ActivityQuestion extends Timestamped {
  activity_id: number;
  question_index: number;
  question_type: "single_choice" | "multiple_choice" | "true_false" | "short_answer";
  stem: string;
  options: QuestionOption[] | null;
  correct_answer: Array<string | boolean> | null;
  reference_answer: string | null;
  grading_rubric: RubricItem[] | null;
  explanation: string;
  difficulty: string;
  points: number;
  status: string;
  sources: QuestionSource[];
}

export interface ActivityListItem extends Timestamped {
  title: string;
  description: string;
  activity_type: string;
  status: "draft" | "published" | "archived" | "generation_failed";
  course_id: number | null;
  knowledge_point_id: number | null;
  course_title: string | null;
  knowledge_point_title: string | null;
  question_count: number;
  total_points: number;
  published_at: string | null;
  completed_attempt_count: number;
  source_scope: Record<string, unknown>;
}

export interface ActivityDetail extends ActivityListItem {
  generation_request_id: string;
  prompt_version: string;
  model_name: string | null;
  validation_warnings: string[];
  questions: ActivityQuestion[];
}

export interface ActivityPage {
  items: ActivityListItem[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface AttemptQuestion {
  id: number;
  question_index: number;
  question_type: ActivityQuestion["question_type"];
  stem: string;
  options: QuestionOption[] | null;
  difficulty: string;
  points: number;
  saved_answer: Array<string | boolean> | null;
  saved_answer_text: string | null;
}

export interface QuizAnswer extends Timestamped {
  question_id: number;
  question_type: ActivityQuestion["question_type"];
  stem: string;
  answer: Array<string | boolean> | null;
  answer_text: string | null;
  is_correct: boolean | null;
  grading_status: "pending" | "completed" | "failed";
  earned_points: number | null;
  max_points: number;
  feedback: string | null;
  matched_rubric_items: string[] | null;
  missing_rubric_items: string[] | null;
  grader_confidence: number | null;
  correct_answer: Array<string | boolean> | null;
  reference_answer: string | null;
  grading_rubric: RubricItem[] | null;
  explanation: string | null;
  sources: QuestionSource[];
  wrong_answer_id: number | null;
  wrong_answer_status: string | null;
}

export interface QuizAttempt extends Timestamped {
  activity_id: number;
  activity_title: string;
  learning_session_id: number | null;
  request_id: string | null;
  status: "in_progress" | "submitted" | "grading" | "completed" | "failed" | "abandoned";
  started_at: string;
  submitted_at: string | null;
  graded_at: string | null;
  total_points: number | null;
  earned_points: number | null;
  score_percentage: number | null;
  correct_count: number;
  incorrect_count: number;
  partial_count: number;
  grading_model: string | null;
  grading_prompt_version: string | null;
  error_message: string | null;
  questions: AttemptQuestion[];
  answers: QuizAnswer[];
  idempotent_replay: boolean;
}

export interface WrongAnswer extends Timestamped {
  question_id: number;
  attempt_id: number;
  answer_id: number;
  course_id: number | null;
  knowledge_point_id: number | null;
  course_title: string | null;
  knowledge_point_title: string | null;
  status: "active" | "reviewing" | "resolved" | "dismissed";
  error_type: "incorrect" | "partial" | "unanswered";
  review_count: number;
  last_reviewed_at: string | null;
  resolved_at: string | null;
  question_type: ActivityQuestion["question_type"];
  stem: string;
  explanation: string;
  answer: Array<string | boolean> | null;
  answer_text: string | null;
  correct_answer: Array<string | boolean> | null;
  reference_answer: string | null;
  sources: QuestionSource[];
}

export interface WrongAnswerPage {
  items: WrongAnswer[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface AgentCitation {
  source_label: string;
  material_id: number | null;
  chunk_id: number | null;
  original_filename: string;
  page_number: number | null;
  section_title: string | null;
  content_excerpt: string;
}

export interface AgentConversation extends Timestamped {
  title: string;
  status: "active" | "archived";
  thread_id: string;
  context: AgentConversationContext;
  last_message_at: string | null;
}

export interface AgentConversationContext {
  context_type: "general" | "goal" | "material" | "lesson";
  context_id: number | null;
}

export interface AgentMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  citations: AgentCitation[];
  run_id: number | null;
  created_at: string;
}

export interface AgentConversationDetail extends AgentConversation {
  messages: AgentMessage[];
}

export interface AgentConfirmation {
  id: number;
  summary: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  status: string;
  expires_at: string;
}

export interface AgentToolCall {
  id: number;
  step_index: number;
  tool_name: string;
  tool_kind: "read" | "write";
  arguments: Record<string, unknown>;
  status: string;
  result: null | { success: boolean; user_summary: string };
  duration_ms: number | null;
}

export interface AgentRun {
  id: number;
  conversation_id: number;
  request_id: string;
  input: string;
  status: string;
  intent: string | null;
  final_answer: string | null;
  citations: AgentCitation[];
  error_code: string | null;
  error: { code: string; safe_message: string; retryable: boolean } | null;
  idempotent_replay: boolean;
  confirmation: AgentConfirmation | null;
  tool_calls: AgentToolCall[];
  performance: Record<string, number | boolean>;
  created_at: string;
  updated_at: string;
}

export interface MasteryListItem {
  knowledge_point_id: number;
  knowledge_point_title: string;
  course_id: number;
  course_title: string;
  mastery_score: number | null;
  confidence_score: number;
  mastery_level: "unassessed" | "beginner" | "developing" | "proficient" | "strong";
  evidence_count: number;
  active_wrong_answers: number;
  last_practiced_at: string | null;
  next_review_at: string | null;
}

export interface MasteryPageData {
  items: MasteryListItem[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface MasteryEvidence {
  id: number;
  evidence_type: string;
  source_type: string;
  source_id: string;
  occurred_at: string;
  normalized_score: number;
  weight: number;
  metadata: Record<string, unknown>;
}

export interface MasterySnapshot {
  id: number;
  mastery_score: number | null;
  confidence_score: number;
  mastery_level: string;
  evidence_count: number;
  trigger_type: string;
  calculated_at: string;
}

export interface AdaptiveReview {
  id: number;
  knowledge_point_id: number;
  knowledge_point_title: string;
  status: "pending" | "scheduled" | "completed" | "dismissed" | "superseded";
  priority_score: number;
  recommended_at: string;
  due_at: string;
  overdue: boolean;
  reason_code: string;
  reason_summary: string;
  completed_task_id: number | null;
}

export interface AdaptiveRecommendation {
  id: number;
  knowledge_point_id: number;
  recommendation_type: "review_task";
  status: "pending" | "accepted" | "rejected" | "executed" | "expired" | "superseded";
  priority: "low" | "medium" | "high";
  title: string;
  reason_code: string;
  reason_details: Record<string, unknown>;
  suggested_date: string;
  suggested_minutes: number;
  created_task_id: number | null;
}

export interface MasteryDetail extends MasteryListItem {
  algorithm_version: string;
  calculated_at: string;
  evidence_summary: Record<string, unknown>;
  evidence: MasteryEvidence[];
  snapshots: MasterySnapshot[];
  review_schedule: AdaptiveReview | null;
  recommendation: AdaptiveRecommendation | null;
}

export interface WeakPoint extends MasteryListItem {
  classification: "weak" | "unassessed";
  weakness_score: number | null;
  recent_failure: boolean;
  overdue: boolean;
  review_status: string | null;
}

export type NoteType = "quick" | "study" | "course" | "knowledge_point" | "material" | "reflection";

export interface NoteLink {
  id: number;
  entity_type: string;
  entity_id: number;
  relation_type: string;
  entity_title: string;
  source_available: boolean;
  created_at: string;
}

export interface NoteSource {
  id: number;
  material_id: number | null;
  chunk_id: number | null;
  source_title: string;
  source_locator: string | null;
  quoted_text: string;
  source_available: boolean;
  created_at: string;
}

export interface Note extends Timestamped {
  title: string;
  content_markdown: string;
  note_type: NoteType;
  status: "active" | "archived";
  is_pinned: boolean;
  archived_at: string | null;
  tags: string[];
  links: NoteLink[];
  sources: NoteSource[];
}

export interface NotePage {
  items: Note[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface MaintenanceStatus {
  id?: number;
  entity_id: string;
  status: "idle" | "pending" | "running" | "failed" | "completed";
  stage?: string;
  attempts?: number;
  error_code?: string | null;
  error_message?: string | null;
  updated_at?: string;
}

export type CourseArchitectureDraftStatus = "draft" | "generating" | "review_required" | "ready" | "publishing" | "published" | "failed" | "archived";

export interface DraftMaterial extends Timestamped {
  draft_id: number;
  material_id: number;
  material_title: string;
  original_filename: string;
  order_index: number;
  material_updated_at_snapshot: string;
  chunk_count_snapshot: number;
  index_state_snapshot: string;
  current_chunk_count: number;
  current_indexing_status: string;
  stale: boolean;
}

export interface DraftSource extends Timestamped {
  draft_knowledge_point_id: number;
  material_id: number;
  material_title: string;
  material_chunk_id: number;
  chunk_index: number;
  source_locator: string | null;
  quoted_text: string | null;
  source_role: "primary" | "supporting" | "example" | "prerequisite_context";
  relevance_score: number | null;
  origin: "generated" | "manual" | "curriculum";
  context_url: string;
}

export interface DraftKnowledgePoint extends Timestamped {
  draft_course_id: number;
  title: string;
  description: string;
  order_index: number;
  learning_objectives: string[];
  key_terms: string[];
  granularity_label: string | null;
  difficulty_label: string | null;
  origin: "generated" | "manual" | "curriculum";
  is_locked: boolean;
  user_modified: boolean;
  source_status: string;
  validation_status: string;
  published_knowledge_point_id: number | null;
  sources: DraftSource[];
}

export interface DraftCourse extends Timestamped {
  draft_id: number;
  title: string;
  description: string;
  order_index: number;
  learning_outcomes: string[];
  origin: "generated" | "manual" | "curriculum";
  is_locked: boolean;
  user_modified: boolean;
  published_course_id: number | null;
  knowledge_points: DraftKnowledgePoint[];
}

export interface DraftPrerequisite extends Timestamped {
  draft_id: number;
  prerequisite_knowledge_point_id: number;
  prerequisite_title: string;
  dependent_knowledge_point_id: number;
  dependent_title: string;
  rationale: string | null;
  confidence: number | null;
  origin: "generated" | "manual" | "curriculum";
  validation_status: string;
}

export interface QualityIssue {
  code: string;
  severity: "blocker" | "warning" | "info";
  message: string;
  course_id: number | null;
  knowledge_point_id: number | null;
}

export interface CourseArchitectureQualityReport {
  status: "blocked" | "ready" | "stale";
  blocker_count: number;
  warning_count: number;
  info_count: number;
  source_coverage: number;
  issues: QualityIssue[];
}

export interface CourseArchitectureDraft extends Timestamped {
  public_id: string;
  learning_goal_id: number;
  learning_goal_title: string;
  title: string;
  description: string;
  status: CourseArchitectureDraftStatus;
  generation_status: string;
  version: number;
  source_snapshot_version: number;
  generation_mode: string;
  model_name: string | null;
  prompt_version: string | null;
  generation_progress: { stage?: string; completed_batches?: number; total_batches?: number; events?: Array<{ event: string; message: string }> };
  last_error_code: string | null;
  last_error_message: string | null;
  quality_status: string;
  quality_report: Partial<CourseArchitectureQualityReport>;
  publish_request_id: string | null;
  published_at: string | null;
  archived_at: string | null;
  materials: DraftMaterial[];
  courses: DraftCourse[];
  prerequisites: DraftPrerequisite[];
}

export interface CourseArchitectureDraftListItem extends Timestamped {
  public_id: string;
  learning_goal_id: number;
  learning_goal_title: string;
  title: string;
  status: CourseArchitectureDraftStatus;
  generation_status: string;
  version: number;
  quality_status: string;
  material_count: number;
  course_count: number;
  knowledge_point_count: number;
}

export interface CourseArchitectureDraftList {
  items: CourseArchitectureDraftListItem[];
  total: number;
}

export interface CourseArchitecturePublishResult {
  draft_id: number;
  publish_request_id: string;
  course_ids: number[];
  knowledge_point_ids: number[];
  material_link_count: number;
  source_count: number;
  prerequisite_count: number;
  published_at: string;
}

export type DiagnosticStatus =
  | "generating"
  | "pending"
  | "submitted"
  | "evidence_insufficient"
  | "generation_failed"
  | "review_required"
  | "cancelled";

export interface DiagnosticAssessment {
  quiz_answer_id: number;
  status: string;
  candidate_score: number | null;
  dimensions: unknown[];
  rationale: string;
  confidence: number | null;
  recommend_manual_review: boolean;
  rubric_version: string | null;
  model_name: string | null;
  error_code: string | null;
}

export interface DiagnosticKnowledgeResult {
  id: number;
  knowledge_point_id: number;
  knowledge_point_title: string;
  answered_count: number;
  graded_count: number;
  earned_points: number | null;
  possible_points: number | null;
  score_percentage: number | null;
  confidence: number;
  ability_level: "evidence_insufficient" | "beginner" | "developing" | "proficient" | "strong";
  is_skill_gap: boolean;
  evidence_insufficient: boolean;
  priority: number;
  reason: string;
  evidence_answer_ids: number[];
  evidence_source_ids: number[];
  mastery_evidence_id: number | null;
  version: number;
  assessments: DiagnosticAssessment[];
}

export interface DiagnosticSession extends Timestamped {
  public_id: string;
  course_id: number;
  course_title: string;
  status: DiagnosticStatus;
  version: number;
  generation_request_id: string;
  activity_id: number | null;
  attempt_id: number | null;
  supersedes_session_id: number | null;
  prompt_version: string;
  model_name: string | null;
  coverage_report: {
    knowledge_point_count?: number;
    covered_count?: number;
    coverage_rate?: number;
    question_count?: number;
    points?: Array<{
      knowledge_point_id: number;
      title: string;
      covered: boolean;
      reason: string | null;
    }>;
  };
  generation_metrics: Record<string, number>;
  last_error_code: string | null;
  last_error_message: string | null;
  submitted_at: string | null;
  attempt: QuizAttempt | null;
  results: DiagnosticKnowledgeResult[];
  idempotent_replay: boolean;
}

export interface DiagnosticHistory {
  items: DiagnosticSession[];
  total: number;
}

export type StudyPlanStatus =
  | "draft"
  | "validating"
  | "ready"
  | "infeasible"
  | "active"
  | "superseded"
  | "completed"
  | "cancelled";

export interface StudyPlanItem {
  id: number;
  scheduled_date: string;
  order_index: number;
  logical_key: string;
  learning_goal_id: number;
  course_id: number;
  course_title: string;
  knowledge_point_id: number | null;
  knowledge_point_title: string | null;
  lesson_id: number | null;
  lesson_title: string | null;
  title: string;
  activity_type: string;
  estimated_minutes: number;
  scheduling_reason: string;
  prerequisite_ids: number[];
  is_due_review: boolean;
  review_schedule_id: number | null;
  diagnostic_result_id: number | null;
  daily_task_id: number | null;
  task_status: string | null;
}

export interface StudyPlanVersion {
  id: number;
  version_number: number;
  status: StudyPlanStatus;
  generation_request_id: string | null;
  replan_request_id: string | null;
  publish_request_id: string | null;
  parameters: {
    start_date: string;
    target_date: string;
    daily_minutes: number;
    available_weekdays: number[];
    allow_weekends: boolean;
    intensity: "basic" | "standard" | "intensive";
    include_due_reviews: boolean;
    use_latest_diagnostic: boolean;
    use_existing_mastery: boolean;
  };
  diagnostic_session_id: number | null;
  required_minutes: number;
  available_minutes: number;
  gap_minutes: number;
  conflicts: Array<Record<string, unknown>>;
  suggestions: Array<Record<string, unknown>>;
  quality_report: {
    prerequisite_constraint_rate?: number;
    time_budget_constraint_rate?: number;
    available_date_constraint_rate?: number;
    duplicate_task_count?: number;
    uncovered_required_knowledge_point_ids?: number[];
  };
  reason: string;
  published_at: string | null;
  stale_at: string | null;
  stale_reason: string | null;
  stale_source_type: string | null;
  stale_source_id: number | null;
  created_at: string;
  items: StudyPlanItem[];
}

export interface StudyPlan extends Timestamped {
  public_id: string;
  learning_goal_id: number;
  learning_goal_title: string;
  course_id: number;
  course_title: string;
  status: StudyPlanStatus;
  version: number;
  current_version_number: number;
  active_version_number: number | null;
  latest_version: StudyPlanVersion;
  active_version: StudyPlanVersion | null;
  idempotent_replay: boolean;
}

export interface StudyPlanHistory {
  items: StudyPlanVersion[];
  total: number;
}

export interface StudyPlanPublishResult {
  plan: StudyPlan;
  created_task_ids: number[];
  reused_task_ids: number[];
  rescheduled_task_ids: number[];
  idempotent_replay: boolean;
}

export type NextLearningActionType =
  | "learn"
  | "practice"
  | "review"
  | "resume_session"
  | "complete_assessment"
  | "review_proposal"
  | "replan_required";

export interface NextLearningAction {
  action_type: NextLearningActionType;
  target_kind: string;
  target_id: number | null;
  learning_goal_id: number | null;
  course_id: number | null;
  course_title: string | null;
  knowledge_point_id: number | null;
  knowledge_point_title: string | null;
  title: string;
  reason_code: string;
  reason: string;
  priority: number;
  estimated_minutes: number;
  from_formal_plan: boolean;
  is_due_review: boolean;
  plan_id: number | null;
  plan_item_id: number | null;
  cta_label: string;
  cta_href: string;
  action_signature: string;
  available_minutes: number | null;
}

export interface NextActionAcceptResult {
  action: NextLearningAction;
  outcome_kind: string;
  outcome_id: number | null;
  next_url: string;
  daily_task_id: number | null;
  learning_session_id: number | null;
  idempotent_replay: boolean;
}

export interface PlanAdjustmentAffectedItem {
  kind: "knowledge_point";
  id: number;
  title: string;
  proposed_change: "add_review";
}

export interface PlanAdjustmentProposal {
  proposal_id: string;
  proposal_type: "plan_adjustment";
  status: LearningProposalStatus;
  version: number;
  context_version: string;
  source_event_id: string;
  study_plan_id: number;
  study_plan_version: number;
  active_plan_version: number;
  reason: string;
  suggestion: string;
  impact: string;
  adjustment_kind: "add_review";
  affected_items: PlanAdjustmentAffectedItem[];
  mastery_change: {
    knowledge_point_id: number;
    knowledge_point_title: string;
    old_level: string;
    new_level: string;
    confidence: number;
    evidence_ids: number[];
  };
  mastery_evidence_ids: number[];
  application: {
    new_plan_version: number;
    active_plan_version: number;
    created_task_ids: number[];
    reused_task_ids: number[];
    rescheduled_task_ids: number[];
    idempotent_replay: boolean;
  } | null;
  expires_at: string | null;
  decided_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface LearningSurfaceContext {
  goal_id?: number | null;
  course_id?: number | null;
  knowledge_point_id?: number | null;
  learning_session_id?: number | null;
  lesson_id?: number | null;
  lesson_version_id?: number | null;
  source_path?: string | null;
  timezone?: string;
}

export interface LearningRuntimeRequest {
  request_id: string;
  actor_key: string;
  input: string;
  conversation_id: number;
  channel?: string;
  surface_context?: LearningSurfaceContext;
  expected_context_version?: string | null;
}

export interface TutorCitation {
  source_label: string;
  material_id: number;
  chunk_id: number;
  original_filename: string;
  page_number: number | null;
  section_title: string | null;
  content_excerpt: string;
  score: number;
}

export interface TutorContextReference {
  kind: "learning_goal" | "course" | "knowledge_point" | "lesson" | "lesson_version" | "learning_session" | "daily_task" | "material";
  id: number;
  title: string;
}

export interface TutorAnswer {
  answer_markdown: string;
  teaching_mode: string;
  citations: TutorCitation[];
  context_references: TutorContextReference[];
  follow_up_check: string | null;
  limitations: string[];
}

export type LearningProposalStatus = "pending" | "review_required" | "accepted" | "rejected" | "expired";

export interface LearningProposalEnvelope {
  proposal_id: string;
  proposal_type: string;
  status: LearningProposalStatus;
  version: number;
  context_version: string | null;
  target_type: string | null;
  target_id: string | null;
  summary: Record<string, unknown>;
  expires_at: string | null;
}

export interface LearningRuntimeResponse {
  run_id: string;
  status: string;
  selected_agent: "operations" | "tutor" | "curriculum" | null;
  answer: string | null;
  proposal: LearningProposalEnvelope | null;
  confirmation: Record<string, unknown> | null;
  citations: Array<Record<string, unknown>>;
  tutor_answer: TutorAnswer | null;
  context_version: string | null;
  warnings: string[];
}

export interface CurriculumKnowledgePoint {
  title: string;
  description: string;
  learning_objectives: string[];
  key_terms: string[];
  difficulty_label: string;
  source_chunk_ids: number[];
}

export interface CurriculumPrerequisite {
  prerequisite_title: string;
  dependent_title: string;
  rationale: string;
  confidence: number;
}

export interface CurriculumLessonBlueprint {
  knowledge_point: string;
  lesson_goal: string;
  estimated_minutes: number;
  requires_lesson_generation: true;
}

export interface CurriculumProposalContent {
  course_title: string;
  course_description: string;
  knowledge_points: CurriculumKnowledgePoint[];
  prerequisites: CurriculumPrerequisite[];
  learning_order: string[];
  estimated_duration: number;
  lesson_blueprints: CurriculumLessonBlueprint[];
  assumptions: string[];
  coverage_report: {
    goal_alignment: string;
    covered_topics: string[];
    gaps: string[];
    material_grounding: "goal_only_unverified" | "source_grounded";
  };
}

export interface CurriculumProposal {
  proposal_id: string;
  proposal_type: "curriculum";
  status: LearningProposalStatus;
  version: number;
  context_version: string | null;
  generation_request_id: string;
  goal: {
    id: number;
    title: string;
    description: string;
    current_level: string;
    target_date: string | null;
    daily_minutes: number;
  };
  grounding_mode: "goal_only" | "source_grounded";
  material_ids: number[];
  curriculum: CurriculumProposalContent;
  architecture: {
    draft_id: number;
    public_id: string;
    version: number;
    status: string;
    quality_status: string;
    quality_report: CourseArchitectureQualityReport;
  };
  expires_at: string | null;
  decided_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CurriculumPublishResult {
  proposal: CurriculumProposal;
  publication: CourseArchitecturePublishResult;
}
