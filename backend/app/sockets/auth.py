import logging
from datetime import UTC
from typing import Any

import socketio
from sqlalchemy import select

from app.database import SessionFactory
from app.models import User
from app.security.jwt import AccessTokenError, decode_access_token_with_expiry
from app.sockets.server import sio

logger = logging.getLogger(__name__)


@sio.event
async def connect(
    sid: str,
    environ: dict[str, Any],
    auth: dict[str, Any] | None = None,
) -> None:
    del environ
    raw_token = auth.get("token") if isinstance(auth, dict) else None
    if not isinstance(raw_token, str) or not raw_token:
        raise socketio.exceptions.ConnectionRefusedError("unauthorized")
    try:
        user_id, token_exp = decode_access_token_with_expiry(raw_token)
    except AccessTokenError:
        raise socketio.exceptions.ConnectionRefusedError("unauthorized") from None

    async with SessionFactory() as session:
        user = await session.scalar(select(User).where(User.id == user_id))
        if user is None:
            raise socketio.exceptions.ConnectionRefusedError("unauthorized")
        # Keep the handshake identity server-side; never trust a client user id.
        await sio.save_session(
            sid,
            {
                "user_id": str(user_id),
                "token_exp": token_exp.astimezone(UTC).isoformat(),
            },
        )
    await sio.enter_room(sid, f"user:{user_id}")
    logger.info("Socket.IO client connected")


@sio.event
async def disconnect(sid: str, reason: str | None = None) -> None:
    del sid, reason
    logger.info("Socket.IO client disconnected")
