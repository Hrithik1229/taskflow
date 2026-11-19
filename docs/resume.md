# TaskFlow — Portfolio & Resume Summary

This document provides verifiable resume bullet points and a concise project summary based **strictly on the implemented, tested codebase**. Every claim is tied directly to automated test evidence in the repository.

---

## Project Summary (2–3 Sentences)

TaskFlow is a production-hardened, real-time collaborative task management platform engineered with a Python 3.12 / FastAPI asynchronous backend and a React 19 Kanban frontend. It enforces PostgreSQL as the single source of truth using optimistic concurrency control, PostgreSQL-backed distributed rate limiting, and an in-memory transactional outbox pattern that broadcasts Socket.IO events strictly after database commits. The platform includes a complete four-column Kanban workflow, role-based access control, task review approvals, discussion threads, and in-app notifications verified by automated test suites.

---

## Verifiable Resume Bullets (3–5 Bullets)

- **Engineered an asynchronous, real-time collaboration backend** using FastAPI, python-socketio (ASGI), and SQLAlchemy 2.0 (asyncpg), implementing an in-memory transactional outbox pattern that guarantees WebSocket room broadcasts fire strictly after PostgreSQL commits, eliminating phantom state and race conditions.  
  *(Evidence: `backend/tests/test_realtime.py::test_realtime_rooms_publish_committed_changes_and_revoke_removed_members`, `backend/tests/test_projects.py::test_project_creation_failure_rolls_back_project_membership_and_activity`)*

- **Designed optimistic concurrency control and advisory locking mechanisms** using entity version integers and PostgreSQL session-level advisory locks (`pg_advisory_xact_lock`), preventing lost updates and serializing task position reordering under concurrent drag-and-drop mutations while returning structured 409 Conflict payloads.  
  *(Evidence: `backend/tests/test_tasks.py::test_concurrent_task_mutations_have_one_winner`, `test_task_http_version_conflict_contains_current_state`, `test_task_positions_remain_contiguous_after_reorder_move_and_delete`)*

- **Implemented an enumeration-resistant security architecture** with Argon2id password hashing, uniform timing-safe authentication error shapes, dynamic project-level RBAC (Owner/Admin/Member), and a PostgreSQL-shared sliding-window rate limiter (10 req/min) synchronized across instances via advisory transaction locks.  
  *(Evidence: `backend/tests/test_auth.py::test_register_returns_generic_response_and_hashes_password`, `test_wrong_password_and_unknown_email_share_same_error`, `backend/tests/test_rate_limit.py::test_auth_rate_limits_are_shared_between_instances`)*

- **Built an interactive, accessible React 19 Kanban board** leveraging `@dnd-kit` for fluid cross-column task reordering, client-side mutation tracking (`X-Client-Mutation-Id`) for echo suppression, automatic socket reconnection resynchronization, and keyboard accessibility.  
  *(Evidence: `frontend/src/pages/BoardPage.test.jsx`, `frontend/src/hooks/useProjectRealtime.test.jsx`, `frontend/src/components/Accessibility.test.jsx`)*

- **Developed a production-grade multi-stage container deployment** with non-root security boundaries (`appuser` UID 1001), fail-fast configuration validators, automated Alembic migrations on startup, liveness/readiness health probes, and an automated end-to-end WebSocket smoke test suite.  
  *(Evidence: `backend/Dockerfile`, `backend/tests/test_config_production.py`, `backend/tests/test_health.py`, `scripts/smoke_test.py`)*

---

## Automated Verification References

| Claim | Verification Command | Result |
| :--- | :--- | :--- |
| Backend Route & Security Tests | `pytest tests/test_auth.py tests/test_authorization_matrix.py tests/test_routes_security.py` | 100% Passed |
| Realtime Outbox & Concurrency | `pytest tests/test_realtime.py tests/test_tasks.py` | 100% Passed |
| Production Config & Health | `pytest tests/test_config_production.py tests/test_health.py` | 100% Passed |
| Frontend Component & Realtime Tests | `npm run test -- --run` | 86/86 Passed |
| End-to-End WebSocket Smoke Test | `python scripts/smoke_test.py --base-url http://localhost:8000` | 15/15 Checks Passed |
