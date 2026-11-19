#!/usr/bin/env python3
# ruff: noqa: E402, I001
"""
backend/scripts/export_openapi.py

Exports the current FastAPI OpenAPI JSON specification to docs/openapi.json.
Usage:
    python backend/scripts/export_openapi.py
"""

import json
import os
import sys
from pathlib import Path

# Ensure development/test mode so OpenAPI docs URLs and schema generation are enabled
os.environ["APP_ENV"] = "development"
os.environ.setdefault("APP_SECRET_KEY", "temporary-secret-for-openapi-export-32c")
os.environ.setdefault("JWT_SECRET_KEY", "temporary-jwt-secret-for-openapi-export")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://dummy:dummy@localhost:5432/dummy"
)

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend_dir))

from app.main import fastapi_app  # noqa: E402


def export_openapi() -> None:
    schema = fastapi_app.openapi()
    output_path = backend_dir.parent / "docs" / "openapi.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2)
    print(f"OpenAPI schema successfully exported to: {output_path}")


if __name__ == "__main__":
    export_openapi()
