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
  error_message: string | null;
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

