from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.enums import ProjectRole


class MemberAdd(BaseModel):
    email: EmailStr
    role: ProjectRole = ProjectRole.MEMBER

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("role")
    @classmethod
    def reject_owner_role(cls, value: ProjectRole) -> ProjectRole:
        if value == ProjectRole.OWNER:
            raise ValueError("A project cannot have another owner.")
        return value


class MemberRoleUpdate(BaseModel):
    role: ProjectRole

    @field_validator("role")
    @classmethod
    def reject_owner_role(cls, value: ProjectRole) -> ProjectRole:
        if value == ProjectRole.OWNER:
            raise ValueError("The project owner role cannot be assigned.")
        return value


class MemberRead(BaseModel):
    id: UUID
    username: str
    email: EmailStr
    role: ProjectRole
    joined_at: datetime


class MemberList(BaseModel):
    members: list[MemberRead]


class ProjectNameQuery(BaseModel):
    email: EmailStr = Field(description="Email address of the registered user to add.")
