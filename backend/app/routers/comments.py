from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import User
from app.schemas.comment import CommentCreate, CommentListResponse, CommentRead
from app.security.dependencies import get_current_user
from app.services.comments import create_comment, list_comments
from app.sockets.emitters import publish_outbox_after_commit

router = APIRouter(tags=["comments"])
SessionDependency = Annotated[AsyncSession, Depends(get_session)]
UserDependency = Annotated[User, Depends(get_current_user)]
MutationId = Annotated[
    str | None,
    Header(alias="X-Client-Mutation-Id", max_length=128),
]


@router.get(
    "/api/tasks/{task_id}/comments",
    response_model=CommentListResponse,
)
async def list_task_comments(
    task_id: UUID,
    session: SessionDependency,
    user: UserDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CommentListResponse:
    return await list_comments(
        session,
        task_id=task_id,
        user_id=user.id,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/api/tasks/{task_id}/comments",
    response_model=CommentRead,
    status_code=201,
)
async def create_task_comment(
    task_id: UUID,
    payload: CommentCreate,
    session: SessionDependency,
    user: UserDependency,
    mutation_id: MutationId = None,
) -> CommentRead:
    comment, outbox = await create_comment(
        session,
        task_id=task_id,
        actor_id=user.id,
        request=payload,
        client_mutation_id=mutation_id,
    )
    await publish_outbox_after_commit(outbox, actor=user)
    return comment
