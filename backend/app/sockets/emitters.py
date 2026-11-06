import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.common.outbox import OutboxEvent
from app.models import User
from app.sockets.server import sio

logger = logging.getLogger(__name__)
NAMESPACE = "/"

TASK_EVENT_NAMES = {
    "task.created": "task_created",
    "task.updated": "task_updated",
    "task.moved": "task_moved",
    "task.deleted": "task_deleted",
}


def _envelope(
    event_type: str,
    project_id: UUID,
    actor: User,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "event_id": str(uuid4()),
        "type": event_type,
        "project_id": str(project_id),
        "actor": {"id": str(actor.id), "username": actor.username},
        "occurred_at": datetime.now(UTC).isoformat(),
        "client_mutation_id": payload.get("client_mutation_id"),
    }


async def _evict_member(project_id: UUID, user_id: UUID, actor: User) -> None:
    project_room = f"project:{project_id}"
    user_room = f"user:{user_id}"
    participants = list(sio.manager.get_participants(NAMESPACE, user_room))
    for participant in participants:
        sid = participant[0]
        if sio.manager.is_connected(sid, NAMESPACE):
            rooms = sio.rooms(sid, namespace=NAMESPACE)
            if project_room in rooms:
                await sio.leave_room(sid, project_room, namespace=NAMESPACE)
    await sio.emit(
        "removed_from_project",
        {
            "event_id": str(uuid4()),
            "type": "removed_from_project",
            "project_id": str(project_id),
            "actor": {"id": str(actor.id), "username": actor.username},
            "occurred_at": datetime.now(UTC).isoformat(),
            "client_mutation_id": None,
        },
        room=user_room,
        namespace=NAMESPACE,
    )


async def publish_outbox_after_commit(
    events: list[OutboxEvent],
    *,
    actor: User,
) -> None:
    """Best-effort publication for outbox descriptors returned after DB commit."""
    for event in events:
        try:
            await _publish_one(event, actor=actor)
        except Exception:
            logger.exception(
                "Socket.IO event publication failed",
                extra={
                    "event": event.event,
                    "project_id": str(event.project_id),
                },
            )


async def _publish_one(event: OutboxEvent, *, actor: User) -> None:
    payload = event.payload
    action = payload.get("action")
    event_name = TASK_EVENT_NAMES.get(action) if isinstance(action, str) else None
    if event_name is not None:
        envelope = _envelope(event_name, event.project_id, actor, payload)
        envelope.update(
            {
                key: value
                for key, value in payload.items()
                if key not in {"action", "client_mutation_id"}
            }
        )
        await sio.emit(
            event_name,
            envelope,
            room=f"project:{event.project_id}",
            namespace=NAMESPACE,
        )
        return

    if event.event == "member_changed":
        member_payload = {
            "event_id": str(uuid4()),
            "type": "member_changed",
            "project_id": str(event.project_id),
            "actor": {"id": str(actor.id), "username": actor.username},
            "occurred_at": datetime.now(UTC).isoformat(),
            "client_mutation_id": payload.get("client_mutation_id"),
            **payload,
        }
        member = member_payload.get("member")
        if isinstance(member, dict):
            member_payload["member"] = {
                key: value for key, value in member.items() if key != "email"
            }
        await sio.emit(
            "member_changed",
            member_payload,
            room=f"project:{event.project_id}",
            namespace=NAMESPACE,
        )
        if action == "member.removed" and payload.get("user_id"):
            await _evict_member(
                event.project_id,
                UUID(str(payload["user_id"])),
                actor,
            )
        return

    if event.event == "notification_created":
        recipient_id = UUID(str(payload["recipient_id"]))
        envelope = _envelope("notification_created", event.project_id, actor, payload)
        envelope["notification"] = payload["notification"]
        await sio.emit(
            "notification_created",
            envelope,
            room=f"user:{recipient_id}",
            namespace=NAMESPACE,
        )
        return

    project_event_names = {
        "project.created": "project_created",
        "project.updated": "project_updated",
        "project.deleted": "project_deleted",
    }
    if event.event == "project_deleted" or event.event == "project_changed":
        event_name = project_event_names.get(str(action))
        if event_name is None:
            return
        envelope = _envelope(event_name, event.project_id, actor, payload)
        project = payload.get("project")
        if isinstance(project, dict):
            envelope["project"] = {
                key: value
                for key, value in project.items()
                if key not in {"role", "assigned_to_me_count"}
            }
        else:
            envelope["project"] = project
        await sio.emit(
            event_name,
            envelope,
            room=f"project:{event.project_id}",
            namespace=NAMESPACE,
        )
        return

    logger.warning(
        "Unrecognized outbox event",
        extra={"event": event.event, "project_id": str(event.project_id)},
    )
