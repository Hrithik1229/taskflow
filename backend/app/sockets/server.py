import logging

import socketio

from app.config import settings

logging.getLogger("socketio").setLevel(logging.WARNING)
logging.getLogger("engineio").setLevel(logging.WARNING)

# The in-memory room manager is single-worker only; multi-worker deployments
# require a shared Socket.IO client manager such as Redis.
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=settings.cors_origins_list,
)
