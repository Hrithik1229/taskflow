from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuthRateLimitAttempt(Base):
    __tablename__ = "auth_rate_limit_attempts"
    __table_args__ = (
        Index(
            "ix_auth_rate_limit_attempts_key_requested",
            "key_hash",
            "requested_at",
        ),
        Index("ix_auth_rate_limit_attempts_requested_at", "requested_at"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
