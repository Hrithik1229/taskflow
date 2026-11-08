import logging

import socketio
from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.common.errors import TaskVersionConflict
from app.common.request_body_limit import RequestBodySizeLimitMiddleware
from app.config import settings
from app.routers.activity import router as activity_router
from app.routers.auth import router as auth_router
from app.routers.comments import router as comments_router
from app.routers.notifications import router as notifications_router
from app.routers.projects import router as projects_router
from app.routers.tasks import dashboard_router
from app.routers.tasks import router as tasks_router
from app.sockets import auth as _socket_auth  # noqa: F401
from app.sockets import events as _socket_events  # noqa: F401
from app.sockets.server import sio

logger = logging.getLogger(__name__)


def api_docs_urls(is_production: bool) -> dict[str, str | None]:
    if is_production:
        return {"docs_url": None, "redoc_url": None, "openapi_url": None}
    return {
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "openapi_url": "/openapi.json",
    }


def security_headers(is_production: bool) -> dict[str, str]:
    headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    }
    if is_production:
        headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        )
        headers["Strict-Transport-Security"] = "max-age=31536000"
    return headers


fastapi_app = FastAPI(
    title="TaskFlow API",
    **api_docs_urls(settings.is_production),
)
fastapi_app.add_middleware(
    RequestBodySizeLimitMiddleware,
    max_body_bytes=settings.MAX_REQUEST_BODY_BYTES,
)
fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@fastapi_app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    try:
        response = await call_next(request)
    except Exception as exc:
        response = await unhandled_exception_handler(request, exc)
    for name, value in security_headers(settings.is_production).items():
        response.headers[name] = value
    return response


fastapi_app.include_router(auth_router)
fastapi_app.include_router(projects_router)
fastapi_app.include_router(tasks_router)
fastapi_app.include_router(dashboard_router)
fastapi_app.include_router(comments_router)
fastapi_app.include_router(notifications_router)
fastapi_app.include_router(activity_router)


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
