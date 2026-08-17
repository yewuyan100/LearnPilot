from functools import lru_cache
from pathlib import Path
from datetime import datetime

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "LearnPilot"
    app_version: str = "6.0.0"
    api_prefix: str = "/api"
    database_url: str = "sqlite:///./data/personal_learning.sqlite3"
    upload_dir: Path = Path("./uploads")
    max_upload_size_mb: int = 20
    allowed_file_extensions: tuple[str, ...] = (".pdf", ".md", ".markdown", ".txt")
    cors_origins: tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    )
    demo_data_enabled: bool = False
    material_chunk_size: int = 800
    material_chunk_overlap: int = 120
    material_min_chunk_size: int = 80
    hf_home: Path | None = None
    embedding_model_name: str = "BAAI/bge-m3"
    embedding_model_revision: str = "local-cache"
    embedding_local_files_only: bool = True
    embedding_device: str = "cpu"
    embedding_batch_size: int = 8
    embedding_normalize: bool = True
    faiss_index_path: Path = Path("./data/materials.faiss")
    faiss_manifest_path: Path = Path("./data/materials.faiss.manifest.json")
    search_top_k_default: int = 5
    search_top_k_max: int = 20
    llm_provider: str = "openai_compatible"
    llm_api_key: SecretStr | None = None
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_timeout_seconds: int = 60
    llm_max_retries: int = 2
    llm_temperature: float = 0.1
    llm_max_output_tokens: int = 1200
    llm_structured_model: str | None = None
    llm_structured_reasoning_enabled: bool = False
    llm_structured_max_output_tokens: int = 2400
    curriculum_generation_max_output_tokens: int = 8000
    agent_planning_max_output_tokens: int = 2400
    rag_candidate_top_k: int = 18
    rag_final_context_top_k: int = 6
    rag_top_k_max: int = 12
    rag_min_score: float = 0.35
    rag_max_sources_per_material: int = 3
    rag_max_context_chars: int = 12000
    rag_max_chunk_chars: int = 2200
    rag_history_messages: int = 6
    rag_history_chars: int = 6000
    rag_query_rewrite_enabled: bool = True
    rag_max_question_chars: int = 2000
    rag_prompt_version: str = "rag-answer-v2-evidence-binding"
    rag_rewrite_prompt_version: str = "rag-rewrite-v1"
    rag_citation_excerpt_chars: int = 800
    rag_reranker_enabled: bool = False
    rag_reranker_model_path: Path | None = None
    rag_reranker_device: str = "cuda"
    activity_max_question_count: int = 20
    activity_default_question_count: int = 8
    activity_max_sources: int = 8
    activity_max_context_chars: int = 16000
    activity_max_chunk_chars: int = 2400
    activity_generation_prompt_version: str = "activity-generation-v1"
    activity_generation_max_output_tokens: int = 6000
    short_answer_grading_prompt_version: str = "short-answer-grading-v1"
    short_answer_max_chars: int = 4000
    short_answer_grading_temperature: float = 0.0
    short_answer_grading_max_retries: int = 1
    wrong_answer_short_answer_threshold: float = 0.6
    diagnostic_prompt_version: str = "diagnostic-generation-v1"
    diagnostic_questions_per_point: int = 2
    diagnostic_max_sources_per_point: int = 6
    diagnostic_short_answer_confidence_threshold: float = 0.65
    question_source_excerpt_chars: int = 800
    app_timezone: str = "Asia/Shanghai"
    agent_enabled: bool = True
    agent_max_history_messages: int = 10
    agent_max_history_chars: int = 8000
    agent_max_steps: int = 4
    agent_max_read_tools: int = 3
    agent_max_write_tools: int = 1
    agent_recursion_limit: int = 16
    agent_confirmation_ttl_minutes: int = 1440
    agent_classification_prompt_version: str = "agent-classification-v1"
    agent_planning_prompt_version: str = "agent-planning-v1"
    agent_response_prompt_version: str = "agent-response-v1"
    agent_checkpoint_enabled: bool = True
    agent_checkpoint_db_path: Path = Path("./data/agent_checkpoints.sqlite")
    agent_tool_result_max_chars: int = 6000
    agent_stream_chunk_chars: int = 24
    mastery_algorithm_version: str = "mastery-rule-v1"
    mastery_max_evidence_per_type: int = 10
    mastery_evidence_half_life_days: int = 30
    mastery_objective_weight: float = 0.40
    mastery_short_answer_weight: float = 0.25
    mastery_review_weight: float = 0.15
    mastery_task_weight: float = 0.08
    mastery_session_weight: float = 0.07
    mastery_self_assessment_weight: float = 0.05
    mastery_diagnostic_weight: float = 0.20
    mastery_beginner_max: float = 39
    mastery_developing_max: float = 59
    mastery_proficient_max: float = 79
    review_interval_beginner_days: int = 1
    review_interval_developing_days: int = 3
    review_interval_proficient_days: int = 7
    review_interval_strong_days: int = 14
    review_failed_interval_days: int = 1
    review_unresolved_wrong_answer_days: int = 3
    clock_fixed_now: datetime | None = None
    adaptive_fixed_now: datetime | None = None
    course_architecture_max_materials_per_draft: int = 5
    course_architecture_max_chunks_per_batch: int = 12
    course_architecture_max_characters_per_batch: int = 18000
    course_architecture_max_batches: int = 24
    course_architecture_max_generated_courses: int = 8
    course_architecture_max_knowledge_points_per_course: int = 20
    course_architecture_max_total_knowledge_points: int = 80
    course_architecture_max_sources_per_knowledge_point: int = 6
    course_architecture_generation_timeout_seconds: int = 180
    course_architecture_generation_retries: int = 1
    course_architecture_prompt_version: str = "course-architecture-v1"

    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        enable_decoding=False,
    )

    @field_validator("allowed_file_extensions", "cors_origins", mode="before")
    @classmethod
    def split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return tuple(item.strip() for item in value.split(",") if item.strip())
        return value

    @model_validator(mode="after")
    def validate_knowledge_base_settings(self) -> "Settings":
        if self.material_chunk_size <= 0:
            raise ValueError("MATERIAL_CHUNK_SIZE 必须大于 0")
        if self.material_chunk_overlap < 0:
            raise ValueError("MATERIAL_CHUNK_OVERLAP 不能小于 0")
        if self.material_chunk_overlap >= self.material_chunk_size:
            raise ValueError("MATERIAL_CHUNK_OVERLAP 必须小于 MATERIAL_CHUNK_SIZE")
        if not 0 < self.material_min_chunk_size < self.material_chunk_size:
            raise ValueError("MATERIAL_MIN_CHUNK_SIZE 必须大于 0 且小于 MATERIAL_CHUNK_SIZE")
        if self.embedding_batch_size <= 0:
            raise ValueError("EMBEDDING_BATCH_SIZE 必须大于 0")
        if self.search_top_k_default <= 0:
            raise ValueError("SEARCH_TOP_K_DEFAULT 必须大于 0")
        if self.search_top_k_max < self.search_top_k_default:
            raise ValueError("SEARCH_TOP_K_MAX 不能小于 SEARCH_TOP_K_DEFAULT")
        if self.llm_provider != "openai_compatible":
            raise ValueError("V3 仅支持 openai_compatible LLM Provider")
        if self.llm_timeout_seconds <= 0 or self.llm_max_retries < 0:
            raise ValueError("LLM 超时必须大于 0，重试次数不能小于 0")
        if min(
            self.llm_max_output_tokens,
            self.llm_structured_max_output_tokens,
            self.curriculum_generation_max_output_tokens,
            self.agent_planning_max_output_tokens,
        ) <= 0:
            raise ValueError("LLM output token limits must be greater than zero")
        if not 0 <= self.llm_temperature <= 2:
            raise ValueError("LLM_TEMPERATURE 必须在 0 到 2 之间")
        if self.rag_candidate_top_k <= 0:
            raise ValueError("RAG_CANDIDATE_TOP_K 必须大于 0")
        if self.rag_final_context_top_k <= 0:
            raise ValueError("RAG_FINAL_CONTEXT_TOP_K 必须大于 0")
        if self.rag_final_context_top_k > self.rag_candidate_top_k:
            raise ValueError("RAG_FINAL_CONTEXT_TOP_K 不能超过 RAG_CANDIDATE_TOP_K")
        if self.rag_top_k_max <= 0:
            raise ValueError("RAG_TOP_K_MAX 必须大于 0")
        if not -1 <= self.rag_min_score <= 1:
            raise ValueError("RAG_MIN_SCORE 必须在 -1 到 1 之间")
        if self.rag_reranker_enabled and self.rag_reranker_model_path is None:
            raise ValueError("启用 RAG reranker 时必须配置 RAG_RERANKER_MODEL_PATH")
        if not (
            self.rag_reranker_device == "cuda"
            or (
                self.rag_reranker_device.startswith("cuda:")
                and self.rag_reranker_device.removeprefix("cuda:").isdigit()
            )
        ):
            raise ValueError("RAG_RERANKER_DEVICE 必须是 cuda 或 cuda:<index>")
        if min(
            self.rag_max_sources_per_material,
            self.rag_max_context_chars,
            self.rag_max_chunk_chars,
            self.rag_history_messages,
            self.rag_history_chars,
            self.rag_max_question_chars,
            self.rag_citation_excerpt_chars,
        ) <= 0:
            raise ValueError("RAG 限制配置必须大于 0")
        if not 1 <= self.activity_default_question_count <= self.activity_max_question_count:
            raise ValueError("默认题目数必须在 1 到 ACTIVITY_MAX_QUESTION_COUNT 之间")
        if min(
            self.activity_max_sources,
            self.activity_max_context_chars,
            self.activity_max_chunk_chars,
            self.activity_generation_max_output_tokens,
            self.short_answer_max_chars,
            self.question_source_excerpt_chars,
        ) <= 0:
            raise ValueError("V4 活动与批改限制配置必须大于 0")
        if not 0 <= self.short_answer_grading_temperature <= 2:
            raise ValueError("SHORT_ANSWER_GRADING_TEMPERATURE 必须在 0 到 2 之间")
        if self.short_answer_grading_max_retries < 0:
            raise ValueError("SHORT_ANSWER_GRADING_MAX_RETRIES 不能小于 0")
        if not 0 <= self.wrong_answer_short_answer_threshold <= 1:
            raise ValueError("WRONG_ANSWER_SHORT_ANSWER_THRESHOLD 必须在 0 到 1 之间")
        if not 1 <= self.diagnostic_questions_per_point <= 4:
            raise ValueError("DIAGNOSTIC_QUESTIONS_PER_POINT 必须在 1 到 4 之间")
        if self.diagnostic_max_sources_per_point <= 0:
            raise ValueError("DIAGNOSTIC_MAX_SOURCES_PER_POINT 必须大于 0")
        if not 0 <= self.diagnostic_short_answer_confidence_threshold <= 1:
            raise ValueError("DIAGNOSTIC_SHORT_ANSWER_CONFIDENCE_THRESHOLD 必须在 0 到 1 之间")
        if min(
            self.agent_max_history_messages,
            self.agent_max_history_chars,
            self.agent_max_steps,
            self.agent_max_read_tools,
            self.agent_max_write_tools,
            self.agent_recursion_limit,
            self.agent_confirmation_ttl_minutes,
            self.agent_tool_result_max_chars,
            self.agent_stream_chunk_chars,
        ) <= 0:
            raise ValueError("Agent limits must be greater than zero")
        if self.agent_max_write_tools != 1:
            raise ValueError("AGENT_MAX_WRITE_TOOLS must be 1")
        if self.mastery_max_evidence_per_type <= 0 or self.mastery_evidence_half_life_days <= 0:
            raise ValueError("Mastery evidence limits must be greater than zero")
        mastery_weights = (
            self.mastery_objective_weight, self.mastery_short_answer_weight,
            self.mastery_review_weight, self.mastery_task_weight,
            self.mastery_session_weight, self.mastery_self_assessment_weight,
            self.mastery_diagnostic_weight,
        )
        if any(weight <= 0 or weight > 1 for weight in mastery_weights):
            raise ValueError("Mastery weights must be in (0, 1]")
        if not (0 <= self.mastery_beginner_max < self.mastery_developing_max < self.mastery_proficient_max < 100):
            raise ValueError("Mastery level thresholds are invalid")
        if min(
            self.review_interval_beginner_days, self.review_interval_developing_days,
            self.review_interval_proficient_days, self.review_interval_strong_days,
            self.review_failed_interval_days, self.review_unresolved_wrong_answer_days,
        ) <= 0:
            raise ValueError("Review intervals must be greater than zero")
        architecture_limits = (
            self.course_architecture_max_materials_per_draft,
            self.course_architecture_max_chunks_per_batch,
            self.course_architecture_max_characters_per_batch,
            self.course_architecture_max_batches,
            self.course_architecture_max_generated_courses,
            self.course_architecture_max_knowledge_points_per_course,
            self.course_architecture_max_total_knowledge_points,
            self.course_architecture_max_sources_per_knowledge_point,
            self.course_architecture_generation_timeout_seconds,
        )
        if min(architecture_limits) <= 0 or self.course_architecture_generation_retries < 0:
            raise ValueError("Course architecture generation limits are invalid")
        if (
            self.course_architecture_max_total_knowledge_points
            < self.course_architecture_max_knowledge_points_per_course
        ):
            raise ValueError("Course architecture total point limit is too small")
        return self

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def llm_configured(self) -> bool:
        key = self.llm_api_key.get_secret_value().strip() if self.llm_api_key else ""
        return bool(key and self.llm_base_url and self.llm_model)

    @property
    def llm_structured_model_name(self) -> str | None:
        return self.llm_structured_model or self.llm_model


@lru_cache
def get_settings() -> Settings:
    return Settings()
