"""Initial V1 schema."""

from alembic import op
import sqlalchemy as sa

revision = "20260729_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learning_goals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("daily_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("current_level", sa.String(200), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("daily_minutes >= 5 AND daily_minutes <= 1440", name="ck_learning_goals_daily_minutes_range"),
    )
    op.create_index("ix_learning_goals_status", "learning_goals", ["status"])
    op.create_index("ix_learning_goals_is_demo", "learning_goals", ["is_demo"])

    op.create_table(
        "materials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("stored_filename", sa.String(255), nullable=False, unique=True),
        sa.Column("file_path", sa.String(1000), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("mime_type", sa.String(120), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("processing_status", sa.String(32), nullable=False, server_default="uploaded"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_materials_source_type", "materials", ["source_type"])
    op.create_index("ix_materials_processing_status", "materials", ["processing_status"])

    op.create_table(
        "courses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("learning_goal_id", sa.Integer(), sa.ForeignKey("learning_goals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_courses_learning_goal_id", "courses", ["learning_goal_id"])
    op.create_index("ix_courses_status", "courses", ["status"])

    op.create_table(
        "knowledge_points",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("status", sa.String(32), nullable=False, server_default="not_started"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("course_id", "order_index", name="uq_knowledge_points_course_order"),
        sa.CheckConstraint("estimated_minutes >= 1", name="ck_knowledge_points_estimated_minutes_positive"),
    )
    op.create_index("ix_knowledge_points_course_id", "knowledge_points", ["course_id"])
    op.create_index("ix_knowledge_points_status", "knowledge_points", ["status"])

    op.create_table(
        "daily_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("learning_goal_id", sa.Integer(), sa.ForeignKey("learning_goals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id", ondelete="SET NULL"), nullable=True),
        sa.Column("knowledge_point_id", sa.Integer(), sa.ForeignKey("knowledge_points.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("task_type", sa.String(32), nullable=False, server_default="learning"),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("scheduled_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("estimated_minutes >= 1", name="ck_daily_tasks_estimated_minutes_positive"),
    )
    for column in ("learning_goal_id", "course_id", "knowledge_point_id", "scheduled_date", "status"):
        op.create_index(f"ix_daily_tasks_{column}", "daily_tasks", [column])

    op.create_table(
        "learning_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("learning_goal_id", sa.Integer(), sa.ForeignKey("learning_goals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id", ondelete="SET NULL"), nullable=True),
        sa.Column("knowledge_point_id", sa.Integer(), sa.ForeignKey("knowledge_points.id", ondelete="SET NULL"), nullable=True),
        sa.Column("daily_task_id", sa.Integer(), sa.ForeignKey("daily_tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    for column in ("learning_goal_id", "course_id", "knowledge_point_id", "daily_task_id", "status"):
        op.create_index(f"ix_learning_sessions_{column}", "learning_sessions", [column])


def downgrade() -> None:
    op.drop_table("learning_sessions")
    op.drop_table("daily_tasks")
    op.drop_table("knowledge_points")
    op.drop_table("courses")
    op.drop_table("materials")
    op.drop_table("learning_goals")
