import logging

import socketio
from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.common.errors import TaskVersionConflict
from app.config import settings
from app.routers.auth import router as auth_router
from app.routers.projects import router as projects_router
from app.routers.tasks import dashboard_router
from app.routers.tasks import router as tasks_router
from app.sockets import auth as _socket_auth  # noqa: F401
from app.sockets import events as _socket_events  # noqa: F401
from app.sockets.server import sio

logger = logging.getLogger(__name__)

fastapi_app = FastAPI(title="TaskFlow API")
fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
fastapi_app.include_router(auth_router)
fastapi_app.include_router(projects_router)
fastapi_app.include_router(tasks_router)
fastapi_app.include_router(dashboard_router)


@fastapi_app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@fastapi_app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    del request
    detail = (
        exc.detail if isinstance(exc.detail, (str, list, dict)) else "Request failed"
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": jsonable_encoder(detail),
            "code": f"http_{exc.status_code}",
        },
        headers=exc.headers,
    )


@fastapi_app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    del request
    return JSONResponse(
        status_code=422,
        content={
            "detail": jsonable_encoder(exc.errors()),
            "code": "validation_error",
        },
    )


@fastapi_app.exception_handler(TaskVersionConflict)
async def task_version_conflict_handler(
    request: Request, exc: TaskVersionConflict
) -> JSONResponse:
    del request
    return JSONResponse(
        status_code=409,
        content={
            "detail": str(exc),
            "code": "version_conflict",
            "current": jsonable_encoder(exc.current),
        },
    )


@fastapi_app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled request error", exc_info=exc)
    del request
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "code": "internal_error"},
    )


asgi_app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app)
