from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserRead
from app.security.jwt import create_access_token
from app.security.passwords import hash_password, verify_password_and_update

DUMMY_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$6yRBR5P5Mbz0x68/o6dR6A$"
    "XCIvvRN25mu+f9U7HPZE/8tVGpH3D6Y5PkIxfwqBuJ0"
)
INVALID_CREDENTIALS = "Invalid email or password."


async def register_user(session: AsyncSession, request: RegisterRequest) -> User:
    normalized_email = str(request.email).strip().lower()
    existing = await session.scalar(
        select(User.id).where(User.email == normalized_email)
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = User(
        username=request.username,
        email=normalized_email,
        password_hash=hash_password(request.password),
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        ) from None
    await session.refresh(user)
    return user


async def authenticate_user(
    session: AsyncSession,
    request: LoginRequest,
) -> tuple[User, TokenResponse]:
    normalized_email = str(request.email).strip().lower()
    user = await session.scalar(select(User).where(User.email == normalized_email))
    stored_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
    verified, replacement_hash = verify_password_and_update(
        request.password,
        stored_hash,
    )
    if user is None or not verified:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_CREDENTIALS,
            headers={"WWW-Authenticate": "Bearer"},
        )

    if replacement_hash is not None:
        user.password_hash = replacement_hash
        await session.commit()
        await session.refresh(user)

    return user, TokenResponse(
        access_token=create_access_token(user.id),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def to_user_read(user: User) -> UserRead:
    return UserRead(
        id=user.id,
        username=user.username,
        email=user.email,
        created_at=user.created_at,
    )
