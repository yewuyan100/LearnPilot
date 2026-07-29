"""Add grounded learning activities, grading, and wrong-answer review."""

from alembic import op
import sqlalchemy as sa


revision = "20260730_0004"
down_revision = "20260730_0003"
branch_labels = None
depends_on = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "learning_activities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("activity_type", sa.String(32), nullable=False, server_default="quiz"),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column(
            "course_id",
            sa.Integer(),
            sa.ForeignKey("courses.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "knowledge_point_id",
            sa.Integer(),
            sa.ForeignKey("knowledge_points.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_scope", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("question_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_points", sa.Float(), nullable=False, server_default="0"),
        sa.Column("generation_request_id", sa.String(64), nullable=False),
        sa.Column("generation_config_hash", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("model_name", sa.String(255), nullable=True),
        sa.Column("validation_warnings", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.UniqueConstraint(
            "generation_request_id",
            name="uq_learning_activities_generation_request_id",
        ),
    )
    for column in ("status", "course_id", "knowledge_point_id"):
        op.create_index(
            f"ix_learning_activities_{column}", "learning_activities", [column]
        )
    op.create_index(
        "ix_learning_activities_created",
        "learning_activities",
        ["created_at", "id"],
    )

    with op.batch_alter_table("daily_tasks") as batch:
        batch.add_column(sa.Column("activity_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_daily_tasks_activity_id_learning_activities",
            "learning_activities",
            ["activity_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_daily_tasks_activity_id", ["activity_id"])

    op.create_table(
        "activity_questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "activity_id",
            sa.Integer(),
            sa.ForeignKey("learning_activities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("question_index", sa.Integer(), nullable=False),
        sa.Column("question_type", sa.String(32), nullable=False),
        sa.Column("stem", sa.Text(), nullable=False),
        sa.Column("options_json", sa.JSON(), nullable=True),
        sa.Column("correct_answer_json", sa.JSON(), nullable=True),
        sa.Column("reference_answer", sa.Text(), nullable=True),
        sa.Column("grading_rubric_json", sa.JSON(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("difficulty", sa.String(16), nullable=False),
        sa.Column("points", sa.Float(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("content_hash", sa.String(64), nullable=False),
        *timestamps(),
        sa.UniqueConstraint(
            "activity_id",
            "question_index",
            name="uq_activity_questions_activity_index",
        ),
        sa.CheckConstraint("points > 0", name="ck_activity_questions_points_positive"),
    )
    for column in ("activity_id", "question_type", "content_hash"):
        op.create_index(f"ix_activity_questions_{column}", "activity_questions", [column])

    op.create_table(
        "question_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "question_id",
            sa.Integer(),
            sa.ForeignKey("activity_questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_label", sa.String(16), nullable=False),
        sa.Column(
            "material_id",
            sa.Integer(),
            sa.ForeignKey("materials.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "chunk_id",
            sa.Integer(),
            sa.ForeignKey("material_chunks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("section_title", sa.String(500), nullable=True),
        sa.Column("content_excerpt", sa.Text(), nullable=False),
        *timestamps(),
        sa.UniqueConstraint(
            "question_id",
            "source_label",
            name="uq_question_sources_question_label",
        ),
    )
    op.create_index("ix_question_sources_question_id", "question_sources", ["question_id"])

    op.create_table(
        "quiz_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "activity_id",
            sa.Integer(),
            sa.ForeignKey("learning_activities.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "learning_session_id",
            sa.Integer(),
            sa.ForeignKey("learning_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("submission_hash", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="in_progress"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("graded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_points", sa.Float(), nullable=True),
        sa.Column("earned_points", sa.Float(), nullable=True),
        sa.Column("score_percentage", sa.Float(), nullable=True),
        sa.Column("correct_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("incorrect_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("partial_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("grading_model", sa.String(255), nullable=True),
        sa.Column("grading_prompt_version", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        *timestamps(),
        sa.UniqueConstraint("request_id", name="uq_quiz_attempts_request_id"),
    )
    for column in ("activity_id", "learning_session_id", "status"):
        op.create_index(f"ix_quiz_attempts_{column}", "quiz_attempts", [column])
    op.create_index(
        "ix_quiz_attempts_activity_created",
        "quiz_attempts",
        ["activity_id", "created_at", "id"],
    )

    op.create_table(
        "quiz_answers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "attempt_id",
            sa.Integer(),
            sa.ForeignKey("quiz_attempts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            sa.Integer(),
            sa.ForeignKey("activity_questions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("answer_json", sa.JSON(), nullable=True),
        sa.Column("answer_text", sa.Text(), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("grading_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("earned_points", sa.Float(), nullable=True),
        sa.Column("max_points", sa.Float(), nullable=False),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("matched_rubric_items_json", sa.JSON(), nullable=True),
        sa.Column("missing_rubric_items_json", sa.JSON(), nullable=True),
        sa.Column("grader_confidence", sa.Float(), nullable=True),
        *timestamps(),
        sa.UniqueConstraint(
            "attempt_id", "question_id", name="uq_quiz_answers_attempt_question"
        ),
    )
    for column in ("attempt_id", "question_id", "grading_status"):
        op.create_index(f"ix_quiz_answers_{column}", "quiz_answers", [column])

    op.create_table(
        "wrong_answers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "question_id",
            sa.Integer(),
            sa.ForeignKey("activity_questions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "attempt_id",
            sa.Integer(),
            sa.ForeignKey("quiz_attempts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "answer_id",
            sa.Integer(),
            sa.ForeignKey("quiz_answers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "course_id",
            sa.Integer(),
            sa.ForeignKey("courses.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "knowledge_point_id",
            sa.Integer(),
            sa.ForeignKey("knowledge_points.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("error_type", sa.String(16), nullable=False),
        sa.Column("review_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.UniqueConstraint(
            "attempt_id", "answer_id", name="uq_wrong_answers_attempt_answer"
        ),
    )
    for column in (
        "question_id",
        "attempt_id",
        "answer_id",
        "course_id",
        "knowledge_point_id",
        "status",
        "error_type",
    ):
        op.create_index(f"ix_wrong_answers_{column}", "wrong_answers", [column])


def downgrade() -> None:
    op.drop_table("wrong_answers")
    op.drop_table("quiz_answers")
    op.drop_table("quiz_attempts")
    op.drop_table("question_sources")
    op.drop_table("activity_questions")
    with op.batch_alter_table("daily_tasks") as batch:
        batch.drop_index("ix_daily_tasks_activity_id")
        batch.drop_constraint(
            "fk_daily_tasks_activity_id_learning_activities", type_="foreignkey"
        )
        batch.drop_column("activity_id")
    op.drop_table("learning_activities")
