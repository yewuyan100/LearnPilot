"""Add knowledge-point lifecycle and preserve historical learning facts.

Revision ID: 20260807_0016
Revises: 20260805_0015
"""

from alembic import op
import sqlalchemy as sa


revision = "20260807_0016"
down_revision = "20260805_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("knowledge_points") as batch:
        batch.add_column(
            sa.Column(
                "lifecycle_status",
                sa.String(32),
                server_default="active",
                nullable=False,
            )
        )
        batch.add_column(sa.Column("superseded_by_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("lifecycle_reason", sa.Text(), nullable=True))
        batch.add_column(sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(
            sa.Column("version", sa.Integer(), server_default="1", nullable=False)
        )
        batch.create_check_constraint(
            op.f("ck_knowledge_points_lifecycle_status_valid"),
            "lifecycle_status IN ('active','archived','superseded')",
        )
        batch.create_check_constraint(
            op.f("ck_knowledge_points_version_positive"), "version >= 1"
        )
        batch.create_foreign_key(
            op.f("fk_knowledge_points_superseded_by_id_knowledge_points"),
            "knowledge_points",
            ["superseded_by_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_index(
            op.f("ix_knowledge_points_lifecycle_status"), ["lifecycle_status"]
        )
        batch.create_index(
            op.f("ix_knowledge_points_superseded_by_id"), ["superseded_by_id"]
        )

    with op.batch_alter_table("study_plan_versions") as batch:
        batch.add_column(sa.Column("stale_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("stale_reason", sa.Text(), nullable=True))
        batch.add_column(sa.Column("stale_source_type", sa.String(32), nullable=True))
        batch.add_column(sa.Column("stale_source_id", sa.Integer(), nullable=True))
        batch.create_index(op.f("ix_study_plan_versions_stale_at"), ["stale_at"])

    with op.batch_alter_table("daily_tasks") as batch:
        batch.add_column(sa.Column("blocked_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("blocked_reason", sa.Text(), nullable=True))
        batch.add_column(sa.Column("blocked_source_type", sa.String(32), nullable=True))
        batch.add_column(sa.Column("blocked_source_id", sa.Integer(), nullable=True))
        batch.create_index(op.f("ix_daily_tasks_blocked_at"), ["blocked_at"])
        batch.drop_constraint(
            "fk_daily_tasks_knowledge_point_id_knowledge_points", type_="foreignkey"
        )
        batch.create_foreign_key(
            op.f("fk_daily_tasks_knowledge_point_id_knowledge_points"),
            "knowledge_points",
            ["knowledge_point_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    with op.batch_alter_table("learning_sessions") as batch:
        batch.add_column(
            sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(sa.Column("invalidation_reason", sa.Text(), nullable=True))
        batch.create_index(op.f("ix_learning_sessions_invalidated_at"), ["invalidated_at"])
        batch.drop_constraint(
            "fk_learning_sessions_knowledge_point_id_knowledge_points", type_="foreignkey"
        )
        batch.create_foreign_key(
            op.f("fk_learning_sessions_knowledge_point_id_knowledge_points"),
            "knowledge_points",
            ["knowledge_point_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    with op.batch_alter_table("study_plan_items") as batch:
        batch.drop_constraint(
            "fk_study_plan_items_knowledge_point_id_knowledge_points", type_="foreignkey"
        )
        batch.create_foreign_key(
            op.f("fk_study_plan_items_knowledge_point_id_knowledge_points"),
            "knowledge_points",
            ["knowledge_point_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    op.create_table(
        "knowledge_point_lifecycle_changes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("knowledge_point_id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(100), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("arguments_hash", sa.String(64), nullable=False),
        sa.Column("from_status", sa.String(32), nullable=False),
        sa.Column("to_status", sa.String(32), nullable=False),
        sa.Column("superseded_by_id", sa.Integer(), nullable=True),
        sa.Column("expected_version", sa.Integer(), nullable=False),
        sa.Column("resulting_version", sa.Integer(), nullable=False),
        sa.Column("impact_snapshot", sa.JSON(), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "resulting_version >= 1",
            name=op.f("ck_knowledge_point_lifecycle_changes_resulting_version_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_point_id"],
            ["knowledge_points.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["superseded_by_id"],
            ["knowledge_points.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "request_id", name="uq_knowledge_point_lifecycle_changes_request_id"
        ),
    )
    for column in ("knowledge_point_id", "request_id", "action"):
        op.create_index(
            op.f(f"ix_knowledge_point_lifecycle_changes_{column}"),
            "knowledge_point_lifecycle_changes",
            [column],
        )

    # Deterministic repair only follows existing plan-item -> task -> session links.
    op.execute(
        sa.text(
            """
            UPDATE study_plan_versions
               SET stale_at = CURRENT_TIMESTAMP,
                   stale_reason = '计划包含已丢失知识点关联的历史计划项，需要重新生成学习计划',
                   stale_source_type = 'data_repair',
                   stale_source_id = NULL,
                   updated_at = CURRENT_TIMESTAMP
             WHERE stale_at IS NULL
               AND status IN ('draft','validating','ready','infeasible','active')
               AND EXISTS (
                   SELECT 1 FROM study_plan_items spi
                    WHERE spi.study_plan_version_id = study_plan_versions.id
                      AND spi.knowledge_point_id IS NULL
               )
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE daily_tasks
               SET blocked_at = CURRENT_TIMESTAMP,
                   blocked_reason = '该任务对应课程内容已变化，需要重新规划',
                   blocked_source_type = 'data_repair',
                   blocked_source_id = NULL,
                   updated_at = CURRENT_TIMESTAMP
             WHERE blocked_at IS NULL
               AND status IN ('pending','in_progress')
               AND EXISTS (
                   SELECT 1 FROM study_plan_items spi
                    WHERE spi.daily_task_id = daily_tasks.id
                      AND spi.knowledge_point_id IS NULL
               )
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE learning_sessions
               SET invalidated_at = CURRENT_TIMESTAMP,
                   invalidation_reason = '该学习会话关联的历史任务已失去知识点关联，不能继续学习',
                   updated_at = CURRENT_TIMESTAMP
             WHERE invalidated_at IS NULL
               AND status IN ('active','paused')
               AND knowledge_point_id IS NULL
               AND EXISTS (
                   SELECT 1 FROM daily_tasks dt
                    WHERE dt.id = learning_sessions.daily_task_id
                      AND dt.blocked_at IS NOT NULL
               )
            """
        )
    )


def downgrade() -> None:
    op.drop_table("knowledge_point_lifecycle_changes")

    with op.batch_alter_table("study_plan_items") as batch:
        batch.drop_constraint(
            "fk_study_plan_items_knowledge_point_id_knowledge_points", type_="foreignkey"
        )
        batch.create_foreign_key(
            op.f("fk_study_plan_items_knowledge_point_id_knowledge_points"),
            "knowledge_points",
            ["knowledge_point_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("learning_sessions") as batch:
        batch.drop_constraint(
            "fk_learning_sessions_knowledge_point_id_knowledge_points", type_="foreignkey"
        )
        batch.create_foreign_key(
            op.f("fk_learning_sessions_knowledge_point_id_knowledge_points"),
            "knowledge_points",
            ["knowledge_point_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.drop_index(op.f("ix_learning_sessions_invalidated_at"))
        batch.drop_column("invalidation_reason")
        batch.drop_column("invalidated_at")

    with op.batch_alter_table("daily_tasks") as batch:
        batch.drop_constraint(
            "fk_daily_tasks_knowledge_point_id_knowledge_points", type_="foreignkey"
        )
        batch.create_foreign_key(
            op.f("fk_daily_tasks_knowledge_point_id_knowledge_points"),
            "knowledge_points",
            ["knowledge_point_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.drop_index(op.f("ix_daily_tasks_blocked_at"))
        batch.drop_column("blocked_source_id")
        batch.drop_column("blocked_source_type")
        batch.drop_column("blocked_reason")
        batch.drop_column("blocked_at")

    with op.batch_alter_table("study_plan_versions") as batch:
        batch.drop_index(op.f("ix_study_plan_versions_stale_at"))
        batch.drop_column("stale_source_id")
        batch.drop_column("stale_source_type")
        batch.drop_column("stale_reason")
        batch.drop_column("stale_at")

    with op.batch_alter_table("knowledge_points") as batch:
        batch.drop_index(op.f("ix_knowledge_points_superseded_by_id"))
        batch.drop_index(op.f("ix_knowledge_points_lifecycle_status"))
        batch.drop_constraint(
            "fk_knowledge_points_superseded_by_id_knowledge_points", type_="foreignkey"
        )
        batch.drop_constraint(
            op.f("ck_knowledge_points_version_positive"), type_="check"
        )
        batch.drop_constraint(
            op.f("ck_knowledge_points_lifecycle_status_valid"), type_="check"
        )
        batch.drop_column("version")
        batch.drop_column("archived_at")
        batch.drop_column("lifecycle_reason")
        batch.drop_column("superseded_by_id")
        batch.drop_column("lifecycle_status")
