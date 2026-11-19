#!/usr/bin/env sh
# migrate.sh — standalone migration script
# Use as a Render/Railway "release command": sh migrate.sh
# It runs ONCE before the new instance starts serving traffic.
# Exit code propagates: non-zero aborts the deploy.
set -e
echo "[migrate] Running alembic upgrade head..."
alembic upgrade head
echo "[migrate] Done."
