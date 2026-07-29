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
  error_message: string | null;
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
}

export interface DailyTask extends Timestamped {
  learning_goal_id: number;
  course_id: number | null;
  knowledge_point_id: number | null;
  title: string;
  task_type: string;
  estimated_minutes: number;
  scheduled_date: string;
  status: string;
}

export interface LearningSession extends Timestamped {
  learning_goal_id: number;
  course_id: number | null;
  knowledge_point_id: number | null;
  daily_task_id: number | null;
  started_at: string;
  ended_at: string | null;
  status: string;
  notes: string;
  goal_title: string | null;
  course_title: string | null;
  knowledge_point_title: string | null;
  task_title: string | null;
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
  recent_course: null | { id: number; title: string; status: string };
  recent_session: null | {
    id: number;
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
