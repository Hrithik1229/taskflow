import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import SessionFactory
from app.models import Project, ProjectRole, User
from app.schemas.auth import RegisterRequest
from app.schemas.member import MemberAdd
from app.schemas.project import ProjectCreate
from app.security.permissions import get_membership
from app.services.auth import register_user
from app.services.members import add_member_by_email
from app.services.projects import create_project

DEMO_OWNER = {
    "username": "demo-owner",
    "email": "demo.owner@example.com",
    "password": "TaskFlowDemoOwner1!",
}
DEMO_MEMBER = {
    "username": "demo-member",
    "email": "demo.member@example.com",
    "password": "TaskFlowDemoMember1!",
}


async def ensure_user(session: AsyncSession, details: dict[str, str]) -> User:
    email = details["email"]
    user = await session.scalar(select(User).where(User.email == email))
    if user is not None:
        return user
    await register_user(
        session,
        RegisterRequest(
            username=details["username"],
            email=email,
            password=details["password"],
        ),
    )
    user = await session.scalar(select(User).where(User.email == email))
    if user is None:
        raise RuntimeError("The development user could not be created.")
    return user


async def seed() -> None:
    if settings.APP_ENV.lower() != "development":
        raise RuntimeError(
            "The development seed can only run with APP_ENV=development."
        )

    async with SessionFactory() as session:
        owner = await ensure_user(session, DEMO_OWNER)
        member = await ensure_user(session, DEMO_MEMBER)
        project = await session.scalar(
            select(Project).where(
                Project.owner_id == owner.id,
                Project.name == "TaskFlow Demo",
            )
        )
        if project is None:
            project_read, _outbox = await create_project(
                session,
                owner_id=owner.id,
                request=ProjectCreate(
                    name="TaskFlow Demo",
                    description="Development-only demo project.",
                ),
            )
            project = await session.get(Project, project_read.id)
            if project is None:
                raise RuntimeError("The development project could not be reloaded.")

        membership = await get_membership(session, project.id, member.id)
        if membership is None:
            owner_membership = await get_membership(session, project.id, owner.id)
            if owner_membership is None:
                raise RuntimeError("The development project has no owner membership.")
            await add_member_by_email(
                session,
                membership=owner_membership,
                actor_id=owner.id,
                request=MemberAdd(email=member.email, role=ProjectRole.MEMBER),
            )

    print("Development seed complete: two demo users and one demo project.")


if __name__ == "__main__":
    asyncio.run(seed())
