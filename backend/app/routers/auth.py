from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.rate_limit import enforce_auth_rate_limit
from app.database import get_session
from app.models import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserRead
from app.security.dependencies import get_current_user
from app.services.auth import authenticate_user, register_user, to_user_read

router = APIRouter(prefix="/api/auth", tags=["authentication"])
SessionDependency = Annotated[AsyncSession, Depends(get_session)]


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: RegisterRequest,
    request: Request,
    session: SessionDependency,
) -> UserRead:
    enforce_auth_rate_limit(request, "register", str(payload.email))
    user = await register_user(session, payload)
    return to_user_read(user)


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    session: SessionDependency,
) -> TokenResponse:
    enforce_auth_rate_limit(request, "login", str(payload.email))
    _, token = await authenticate_user(session, payload)
    return token


@router.get("/me", response_model=UserRead)
async def current_profile(
    user: Annotated[User, Depends(get_current_user)],
) -> UserRead:
    return to_user_read(user)
