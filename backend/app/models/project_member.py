from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import ProjectRole

project_role_type = Enum(
    ProjectRole,
    name="project_role",
    native_enum=False,
    create_constraint=True,
    values_callable=lambda enum_type: [role.value for role in enum_type],
)


class ProjectMember(Base):
    __tablename__ = "project_members"
    __table_args__ = (
        Index(
            "uq_project_members_one_owner_per_project",
            "project_id",
            unique=True,
            postgresql_where=text("role = 'owner'"),
        ),
        UniqueConstraint(
            "project_id", "user_id", name="uq_project_members_project_user"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    role: Mapped[ProjectRole] = mapped_column(project_role_type, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
