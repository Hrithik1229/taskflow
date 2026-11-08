"""Store authentication rate-limit attempts in PostgreSQL.

Revision ID: 0003_shared_auth_rate_limits
Revises: 0002_task_review_attribution
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003_shared_auth_rate_limits"
down_revision: str | None = "0002_task_review_attribution"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auth_rate_limit_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_rate_limit_attempts")),
    )
    op.create_index(
        "ix_auth_rate_limit_attempts_key_requested",
        "auth_rate_limit_attempts",
        ["key_hash", "requested_at"],
    )
    op.create_index(
        "ix_auth_rate_limit_attempts_requested_at",
        "auth_rate_limit_attempts",
        ["requested_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_auth_rate_limit_attempts_requested_at",
        table_name="auth_rate_limit_attempts",
    )
    op.drop_index(
        "ix_auth_rate_limit_attempts_key_requested",
        table_name="auth_rate_limit_attempts",
    )
    op.drop_table("auth_rate_limit_attempts")
