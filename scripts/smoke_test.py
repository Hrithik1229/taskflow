#!/usr/bin/env python3
"""
scripts/smoke_test.py
─────────────────────────────────────────────────────────────────────────────
Reusable smoke test against any deployed or local production-like URL.

USAGE
  # Against local prod-like compose stack:
  python scripts/smoke_test.py --base-url http://localhost:8000

  # Against deployed backend:
  python scripts/smoke_test.py --base-url https://taskflow-api.onrender.com

REQUIREMENTS
  pip install httpx python-socketio websockets

EXIT CODE
  0 — all checks passed
  1 — one or more checks failed
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
import socketio  # python-socketio[asyncio_client]

# ─── Helpers ─────────────────────────────────────────────────────────────────

PASS = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"
SKIP = "\033[33m~\033[0m"


@dataclass
class Results:
    passed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    def ok(self, name: str) -> None:
        print(f"  {PASS}  {name}")
        self.passed.append(name)

    def fail(self, name: str, detail: str = "") -> None:
        msg = f"  {FAIL}  {name}"
        if detail:
            msg += f"\n       → {detail}"
        print(msg)
        self.failed.append(name)

    def summary(self) -> int:
        total = len(self.passed) + len(self.failed)
        print(
            f"\n{'─'*60}\n"
            f"  Smoke test: {len(self.passed)}/{total} passed"
            f"{'  ← ALL GOOD ✓' if not self.failed else ''}\n"
            f"{'─'*60}"
        )
        if self.failed:
            print("  FAILED checks:")
            for f in self.failed:
                print(f"    • {f}")
        return 1 if self.failed else 0


# ─── Individual checks ───────────────────────────────────────────────────────


async def check_health(client: httpx.AsyncClient, results: Results) -> None:
    print("\n[1] Health endpoints")
    try:
        r = await client.get("/api/health")
        if r.status_code == 200 and r.json().get("status") == "ok":
            results.ok("/api/health → 200 ok")
        else:
            results.fail("/api/health", f"status={r.status_code} body={r.text[:200]}")
    except Exception as exc:
        results.fail("/api/health", str(exc))

    try:
        r = await client.get("/api/health/ready")
        if r.status_code == 200 and r.json().get("status") == "ready":
            results.ok("/api/health/ready → 200 ready")
        else:
            results.fail("/api/health/ready", f"status={r.status_code} body={r.text[:200]}")
    except Exception as exc:
        results.fail("/api/health/ready", str(exc))


async def register_user(
    client: httpx.AsyncClient, suffix: str
) -> dict[str, Any] | None:
    """Register a unique user and return {username, email, password}."""
    uid = uuid.uuid4().hex[:8]
    data = {
        "username": f"user_{uid}_{suffix.lower()}",
        "email": f"smoketest_{uid}_{suffix.lower()}@example.com",
        "password": "SmokeTest@12345",
    }
    r = await client.post("/api/auth/register", json=data)
    if r.status_code not in (200, 201, 202):
        print(f"       [register error {r.status_code}]: {r.text[:200]}")
        return None
    return data


async def login_user(
    client: httpx.AsyncClient, email: str, password: str
) -> str | None:
    """Log in and return the access token, or None."""
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    if r.status_code == 200:
        return r.json().get("access_token")
    return None


async def check_auth(
    client: httpx.AsyncClient, results: Results
) -> tuple[dict[str, Any] | None, str | None, dict[str, Any] | None, str | None]:
    """Register two users and return (user_a, token_a, user_b, token_b)."""
    print("\n[2] Auth: register + login two users")
    user_a = await register_user(client, "A")
    user_b = await register_user(client, "B")

    if user_a:
        results.ok(f"Register user A ({user_a['email']})")
    else:
        results.fail("Register user A")
        return None, None, None, None

    if user_b:
        results.ok(f"Register user B ({user_b['email']})")
    else:
        results.fail("Register user B")
        return None, None, None, None

    token_a = await login_user(client, user_a["email"], user_a["password"])
    token_b = await login_user(client, user_b["email"], user_b["password"])

    if token_a:
        results.ok("Login user A → got token")
    else:
        results.fail("Login user A")

    if token_b:
        results.ok("Login user B → got token")
    else:
        results.fail("Login user B")

    return user_a, token_a, user_b, token_b


async def check_project_and_membership(
    client: httpx.AsyncClient,
    token_a: str,
    user_b: dict[str, Any],
    results: Results,
) -> str | None:
    """Create a project as A, add B as member. Return project_id."""
    print("\n[3] Project + membership")

    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Create project
    r = await client.post(
        "/api/projects",
        json={"name": "Smoke Test Project"},
        headers=headers_a,
    )
    if r.status_code not in (200, 201):
        results.fail("Create project as A", f"status={r.status_code}")
        return None
    project_id = r.json()["id"]
    results.ok(f"Create project → {project_id}")

    # Add B to project using email
    r = await client.post(
        f"/api/projects/{project_id}/members",
        json={"email": user_b["email"], "role": "member"},
        headers=headers_a,
    )
    if r.status_code in (200, 201, 204):
        results.ok("Add user B to project")
    else:
        results.fail("Add user B to project", f"status={r.status_code} body={r.text[:200]}")

    return project_id


# ─── Socket.IO real-time checks ──────────────────────────────────────────────


class SocketClient:
    """Thin wrapper around python-socketio AsyncClient for smoke testing."""

    def __init__(self, base_url: str, token: str, label: str):
        self.base_url = base_url
        self.token = token
        self.label = label
        self.sio = socketio.AsyncClient(
            reconnection=False,
            logger=False,
            engineio_logger=False,
        )
        self.received: list[dict] = []
        self._event = asyncio.Event()

        @self.sio.on("task_created")
        async def on_task_created(data):
            self.received.append({"event": "task_created", "data": data})
            self._event.set()

        @self.sio.on("task_updated")
        async def on_task_updated(data):
            self.received.append({"event": "task_updated", "data": data})
            self._event.set()

    async def connect(self) -> bool:
        try:
            await self.sio.connect(
                self.base_url,
                auth={"token": self.token},
                transports=["websocket"],  # force WS; no polling fallback for test
                wait_timeout=10,
            )
            return True
        except Exception as exc:
            print(f"       [{self.label}] connect error: {exc}")
            return False

    async def wait_for_event(self, timeout: float = 5.0) -> bool:
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
            self._event.clear()
            return True
        except asyncio.TimeoutError:
            return False

    async def disconnect(self) -> None:
        try:
            await self.sio.disconnect()
        except Exception:
            pass


async def check_realtime(
    base_url: str,
    client: httpx.AsyncClient,
    token_a: str,
    token_b: str,
    project_id: str,
    results: Results,
) -> None:
    print("\n[4] Real-time WebSocket (Socket.IO)")

    # Outsider: register a third user who is NOT in the project
    outsider_creds = await register_user(client, "OUTSIDER")
    outsider_token = None
    if outsider_creds:
        outsider_token = await login_user(
            client, outsider_creds["email"], outsider_creds["password"]
        )

    sio_a = SocketClient(base_url, token_a, "UserA")
    sio_b = SocketClient(base_url, token_b, "UserB")
    sio_out = SocketClient(base_url, outsider_token or token_a, "Outsider")

    ok_a = await sio_a.connect()
    ok_b = await sio_b.connect()
    ok_out = await sio_out.connect() if outsider_token else False

    if ok_a:
        results.ok("UserA WebSocket connected")
    else:
        results.fail("UserA WebSocket connect")

    if ok_b:
        results.ok("UserB WebSocket connected")
    else:
        results.fail("UserB WebSocket connect")

    if ok_out:
        results.ok("Outsider WebSocket connected")

    if not (ok_a and ok_b):
        print("       Skipping real-time event checks (connections failed)")
        await sio_a.disconnect()
        await sio_b.disconnect()
        await sio_out.disconnect()
        return

    # Subscribe both to the project room
    await sio_a.sio.emit("join_project", {"project_id": project_id})
    await sio_b.sio.emit("join_project", {"project_id": project_id})
    await asyncio.sleep(0.5)  # give server time to process joins

    # Create a task via REST as user A
    headers_a = {"Authorization": f"Bearer {token_a}"}
    r = await client.post(
        f"/api/projects/{project_id}/tasks",
        json={"title": "Smoke Test Task", "status": "todo"},
        headers=headers_a,
    )
    if r.status_code not in (200, 201):
        results.fail("Create task via REST", f"status={r.status_code} body={r.text[:200]}")
        task_id = None
    else:
        task_id = r.json()["id"]
        results.ok(f"Create task via REST → {task_id}")

    # UserB should receive task_created
    b_got = await sio_b.wait_for_event(timeout=5.0)
    if b_got and any(e["event"] == "task_created" for e in sio_b.received):
        results.ok("UserB received task_created event")
    else:
        results.fail("UserB did NOT receive task_created within 5s")

    # Outsider should NOT receive it
    if ok_out:
        await asyncio.sleep(1.0)
        if not sio_out.received:
            results.ok("Outsider did NOT receive task_created (correct isolation)")
        else:
            results.fail(
                "Outsider received an event it should not have",
                str(sio_out.received),
            )

    # Stale-version conflict: update with wrong version → expect 409
    if task_id:
        current_version = r.json().get("version", 1)
        r_conflict = await client.patch(
            f"/api/tasks/{task_id}",
            json={"title": "Conflict Update", "expected_version": current_version + 999},
            headers=headers_a,
        )
        if r_conflict.status_code == 409:
            results.ok("Stale-version PATCH → 409 conflict (correct)")
        else:
            results.fail(
                "Expected 409 on stale version",
                f"got {r_conflict.status_code}: {r_conflict.text[:200]}",
            )

    await sio_a.disconnect()
    await sio_b.disconnect()
    await sio_out.disconnect()


# ─── Entry point ─────────────────────────────────────────────────────────────


async def run(base_url: str) -> int:
    base_url = base_url.rstrip("/")
    print(f"\n{'═'*60}")
    print(f"  TaskFlow Smoke Test")
    print(f"  Target: {base_url}")
    print(f"{'═'*60}")

    results = Results()

    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        await check_health(client, results)

        user_a, token_a, user_b, token_b = await check_auth(client, results)
        if not token_a or not token_b or not user_b:
            print("\n  Cannot continue: auth checks failed.")
            return results.summary()

        project_id = await check_project_and_membership(
            client, token_a, user_b, results
        )
        if not project_id:
            print("\n  Cannot continue: project/membership checks failed.")
            return results.summary()

        await check_realtime(base_url, client, token_a, token_b, project_id, results)

    return results.summary()


def main() -> None:
    parser = argparse.ArgumentParser(description="TaskFlow smoke test")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL of the backend (default: http://localhost:8000)",
    )
    args = parser.parse_args()

    try:
        exit_code = asyncio.run(run(args.base_url))
    except KeyboardInterrupt:
        print("\n  Interrupted.")
        exit_code = 1
    except Exception:
        traceback.print_exc()
        exit_code = 1

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
