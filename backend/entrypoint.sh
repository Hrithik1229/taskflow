#!/usr/bin/env sh
# entrypoint.sh — production container entry point
#
# Migration strategy: "release command" pattern
# ─────────────────────────────────────────────────────────────────────────────
# We run `alembic upgrade head` before starting the application server.
# On Render.com and Railway this can be replaced by a "release command"
# configured in the dashboard (run before the new instance starts serving
# traffic), which is safer because migrations run once, not once-per-replica.
#
# When running as an entrypoint script (as here, for the prod-like compose
# stack), `set -e` ensures that if the migration step exits non-zero the
# container exits immediately — Docker Compose will mark the service as
# failed and not start the app.  This prevents a broken schema from serving
# live traffic.
#
# Never use SQLAlchemy's create_all() in production — it has no concept of
# incremental schema evolution or rollback.
# ─────────────────────────────────────────────────────────────────────────────
set -e

echo "[entrypoint] Running Alembic migrations..."
alembic upgrade head
echo "[entrypoint] Migrations complete. Starting server..."

exec uvicorn app.main:asgi_app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers 1 \
    --proxy-headers \
    --forwarded-allow-ips='*' \
    --log-level warning
