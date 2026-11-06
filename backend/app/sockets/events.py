import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

from app.database import SessionFactory
from app.models import ProjectMember
from app.security.permissions import get_membership
from app.sockets.server import sio

logger = logging.getLogger(__name__)
NAMESPACE = "/"


class _ExpiredSocketToken(Exception):
    pass


def _parse_project_id(data: object) -> UUID | None:
    if not isinstance(data, dict) or set(data) != {"project_id"}:
        return None
    try:
        return UUID(str(data["project_id"]))
    except (ValueError, TypeError, AttributeError):
        return None


async def _authenticated_session(sid: str) -> tuple[UUID, datetime] | None:
    try:
        state = await sio.get_session(sid, namespace=NAMESPACE)
        user_id = UUID(state["user_id"])
        token_exp = datetime.fromisoformat(state["token_exp"])
    except (KeyError, TypeError, ValueError):
        return None
    if token_exp <= datetime.now(UTC):
        raise _ExpiredSocketToken
    return user_id, token_exp


async def _disconnect_after_ack(sid: str) -> None:
    await asyncio.sleep(0.05)
    await sio.disconnect(sid, namespace=NAMESPACE)


@sio.on("join_project", namespace=NAMESPACE)
async def join_project(sid: str, data: object) -> dict[str, object]:
    try:
        project_id = _parse_project_id(data)
        if project_id is None:
            return {"ok": False, "error": "invalid_payload"}
        identity = await _authenticated_session(sid)
        if identity is None:
            return {"ok": False, "error": "unauthenticated"}
        user_id, _ = identity
        async with SessionFactory() as session:
            membership: ProjectMember | None = await get_membership(
                session, project_id, user_id
            )
        if membership is None:
            return {"ok": False, "error": "forbidden"}
        await sio.enter_room(sid, f"project:{project_id}", namespace=NAMESPACE)
        return {"ok": True, "project_id": str(project_id)}
    except _ExpiredSocketToken:
        asyncio.create_task(_disconnect_after_ack(sid))
        return {"ok": False, "error": "unauthenticated"}
    except Exception:
        logger.exception("Socket.IO project join failed")
        return {"ok": False, "error": "forbidden"}


@sio.on("leave_project", namespace=NAMESPACE)
async def leave_project(sid: str, data: object) -> dict[str, object]:
    try:
        project_id = _parse_project_id(data)
        if project_id is None:
            return {"ok": False, "error": "invalid_payload"}
        identity = await _authenticated_session(sid)
        if identity is None:
            return {"ok": False, "error": "unauthenticated"}
        await sio.leave_room(sid, f"project:{project_id}", namespace=NAMESPACE)
        return {"ok": True, "project_id": str(project_id)}
    except _ExpiredSocketToken:
        asyncio.create_task(_disconnect_after_ack(sid))
        return {"ok": False, "error": "unauthenticated"}
    except Exception:
        logger.exception("Socket.IO project leave failed")
        return {"ok": False, "error": "unauthenticated"}
