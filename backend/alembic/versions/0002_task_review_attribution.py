"""Add task review and status attribution.

Revision ID: 0002_task_review_attribution
Revises: 0001_initial_schema
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_task_review_attribution"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("reviewer_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "tasks",
        sa.Column("review_requested_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "tasks",
        sa.Column("status_changed_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "tasks",
        sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tasks",
        sa.Column("completed_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "tasks",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_tasks_reviewer_id_users",
        "tasks",
        "users",
        ["reviewer_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_tasks_review_requested_by_users",
        "tasks",
        "users",
        ["review_requested_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_tasks_status_changed_by_users",
        "tasks",
        "users",
        ["status_changed_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_tasks_completed_by_users",
        "tasks",
        "users",
        ["completed_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_tasks_reviewer_id", "tasks", ["reviewer_id"])
    op.create_index("ix_tasks_completed_by", "tasks", ["completed_by"])
    op.execute(
        sa.text(
            """
            WITH latest_moves AS (
                SELECT DISTINCT ON (entity_id)
                    entity_id, actor_id, created_at
                FROM activity_logs
                WHERE entity_type = 'task' AND action = 'task.moved'
                ORDER BY entity_id, created_at DESC, id DESC
            )
            UPDATE tasks AS task
            SET status_changed_by = latest_moves.actor_id,
                status_changed_at = latest_moves.created_at
            FROM latest_moves
            WHERE task.id = latest_moves.entity_id
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_tasks_completed_by", table_name="tasks")
    op.drop_index("ix_tasks_reviewer_id", table_name="tasks")
    op.drop_constraint("fk_tasks_completed_by_users", "tasks", type_="foreignkey")
    op.drop_constraint("fk_tasks_status_changed_by_users", "tasks", type_="foreignkey")
    op.drop_constraint(
        "fk_tasks_review_requested_by_users", "tasks", type_="foreignkey"
    )
    op.drop_constraint("fk_tasks_reviewer_id_users", "tasks", type_="foreignkey")
    op.drop_column("tasks", "completed_at")
    op.drop_column("tasks", "completed_by")
    op.drop_column("tasks", "status_changed_at")
    op.drop_column("tasks", "status_changed_by")
    op.drop_column("tasks", "review_requested_by")
    op.drop_column("tasks", "reviewer_id")
