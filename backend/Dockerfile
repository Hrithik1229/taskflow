# ============================================================
# Stage 1: builder — install only production dependencies
# ============================================================
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build tools needed by some wheels (e.g. cffi for argon2-cffi-bindings)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy only the requirements file first so Docker can cache this layer
COPY requirements.txt ./

# Install into an isolated prefix so we can copy cleanly to the runtime stage
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ============================================================
# Stage 2: runtime — minimal, non-root, no dev tooling
# ============================================================
FROM python:3.12-slim AS runtime

# Keep image small and predictable
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Tell Python where the packages live
    PYTHONPATH=/app

# Runtime system libraries only (libpq for asyncpg C-extension)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    # Create a non-root user; UID/GID 1001 avoids collision with common host UIDs
    && groupadd -r -g 1001 appgroup \
    && useradd -r -u 1001 -g appgroup -d /app -s /sbin/nologin appuser

# Copy installed packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app

# Copy application source (Dockerfile/.dockerignore explicitly excludes .env, secrets, dev files)
COPY --chown=appuser:appgroup app/ ./app/
COPY --chown=appuser:appgroup alembic/ ./alembic/
COPY --chown=appuser:appgroup alembic.ini ./alembic.ini
COPY --chown=appuser:appgroup entrypoint.sh ./entrypoint.sh
COPY --chown=appuser:appgroup migrate.sh ./migrate.sh

# Drop privileges
USER appuser

# ============================================================
# Production start command
# ============================================================
# Single worker: rationale — the Socket.IO server uses an in-memory client
# manager (AsyncServer with async_mode="asgi") and an in-memory rate-limiter.
# Multiple workers would each maintain independent state; rooms/sessions
# created in one worker would be invisible to others, breaking real-time
# events.  Scaling beyond one instance requires a Redis-backed Socket.IO
# client manager and an external rate-limit store — not implemented here.
#
# --proxy-headers: required when running behind a reverse proxy (Render,
#   Railway, Fly.io all terminate TLS and forward the original client IP/proto
#   in X-Forwarded-For / X-Forwarded-Proto).  Without this, request.client
#   would always show the proxy's internal address.
#
# --forwarded-allow-ips="*": acceptable ONLY because these hosts guarantee
#   the proxy is the only inbound path; the listening port is not exposed
#   directly.  On platforms where the socket is reachable from arbitrary
#   internet traffic, pin this to the known proxy CIDR instead.
CMD ["sh", "-c", \
     "uvicorn app.main:asgi_app \
      --host 0.0.0.0 \
      --port ${PORT:-8000} \
      --workers 1 \
      --proxy-headers \
      --forwarded-allow-ips='*' \
      --log-level warning"]
