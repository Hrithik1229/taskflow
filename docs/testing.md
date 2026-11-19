# TaskFlow — Testing Strategy & Quality Assurance Traceability

This document details the multi-tiered testing strategy, automated test commands, real-time verification mechanics, requirement traceability matrix, and manual QA walkthrough scripts for TaskFlow.

---

## 1. Test Strategy Overview

TaskFlow employs a pyramid testing strategy ensuring reliability, security, and concurrency safety:

```
                  ┌──────────────────────────────┐
                  │   Manual Two-Browser QA      │
                  │   & Accessibility Reviews    │
                  ├──────────────────────────────┤
                  │   End-to-End Smoke Test      │
                  │   (scripts/smoke_test.py)    │
                  ├──────────────────────────────┤
                  │   Realtime & Concurrency     │
                  │   Integration Tests (pytest) │
                  ├──────────────────────────────┤
                  │   Component & Hook Tests     │
                  │   (Vitest + React Test Lib)  │
                  ├──────────────────────────────┤
                  │   Unit & Security Matrix     │
                  │   (pytest, Ruff, ESLint)     │
                  └──────────────────────────────┘
```

1. **Unit & Security Matrix:** Covers Pydantic schemas, password hashing with Argon2id, JWT issuance/validation, fail-fast production configuration, and exhaustive route authorization matrices.
2. **Component & Reducer Tests:** Vitest tests all React components, form validations, theme toggles, error boundaries, and WebSocket state reducers.
3. **Realtime & Concurrency Suite:** Tests multi-client WebSocket communication, outbox transactional boundaries, optimistic concurrency conflicts (HTTP 409), and PostgreSQL advisory locks under concurrent requests.
4. **End-to-End Smoke Test:** A standalone Python script (`scripts/smoke_test.py`) capable of running against any local or deployed URL, creating users, establishing WebSocket connections, creating tasks, verifying broadcasts, asserting outsider isolation, and checking version conflicts.
5. **Manual QA Scenarios:** Step-by-step procedures to verify cross-browser synchronization, reconnection, and keyboard accessibility.

---

## 2. Test Execution Commands

### Backend Tests (pytest)
From the `backend/` directory:
```bash
# 1. Run all unit and security tests (fast, no external DB needed):
python -m pytest tests/test_config.py tests/test_config_production.py tests/test_passwords.py tests/test_routes_security.py -v

# 2. Run full backend suite with coverage (requires PostgreSQL on port 5433 or 5432):
python -m pytest -v --cov=app --cov-report=term-missing

# 3. Run concurrency and real-time integration tests:
python -m pytest tests/test_tasks.py tests/test_realtime.py -v

# 4. Code quality & formatting:
python -m ruff check .
python -m ruff format --check .
```

### Frontend Tests (Vitest)
From the `frontend/` directory:
```bash
# 1. Run full test suite in single-run mode:
npm run test -- --run

# 2. Run test suite with code coverage:
npm run test -- --run --coverage

# 3. Lint check:
npm run lint

# 4. Production build check:
npm run build
```

### Reusable Production Smoke Test
From the project root:
```bash
# Against local production-like container stack:
python scripts/smoke_test.py --base-url http://localhost:8000

# Against live deployed backend:
python scripts/smoke_test.py --base-url https://your-backend.onrender.com
```

---

## 3. How Realtime Tests Work

Realtime testing involves multiple asynchronous actors and cannot rely on simple synchronous request-response assertions:

1. **In-Memory ASGI Sockets (`tests/test_realtime.py`):**
   - The test fixture initializes `python-socketio` AsyncClient instances connected to the in-memory ASGI app via `httpx.ASGITransport`.
   - Tests connect two authenticated client sessions (User A and User B) and an unauthenticated or outsider client (User C).
   - Events are awaited using `asyncio.wait_for(event.wait(), timeout=...)`.
   - Tests assert that User B receives `task_created` while User C receives nothing (verifying strict project tenant room isolation).

2. **Transactional Outbox Boundary Verification:**
   - Tests execute mutations in a rolled-back transaction (or simulate database failure) and assert that zero Socket.IO events are emitted, confirming the emit-after-commit invariant.

3. **Client Echo Suppression Verification (`frontend/src/hooks/useProjectRealtime.test.jsx`):**
   - Tests dispatch mock WebSocket events containing the client's own `client_mutation_id`.
   - The reducer verifies that the event is ignored, preventing duplicate UI renders or animation flickers.

---

## 4. Requirement Traceability Matrix

| Requirement Area | Automated Test Evidence | Status |
| :--- | :--- | :---: |
| **Authentication & Credentials** | `tests/test_auth.py`, `tests/test_passwords.py` | ✅ Verified |
| **Shared Auth Rate Limiting** | `tests/test_rate_limit.py::test_auth_rate_limits_are_shared_between_instances` | ✅ Verified |
| **Project Role Permissions** | `tests/test_authorization_matrix.py` (25 routes × 4 roles) | ✅ Verified |
| **Anonymous Route Guard** | `tests/test_routes_security.py::test_every_protected_route_rejects_anonymous_requests` | ✅ Verified |
| **Task CRUD & Ordering** | `tests/test_tasks.py::test_task_positions_remain_contiguous_after_reorder_move_and_delete` | ✅ Verified |
| **Optimistic Concurrency (409)**| `tests/test_tasks.py::test_task_http_version_conflict_contains_current_state` | ✅ Verified |
| **Advisory Lock Move Safety** | `tests/test_tasks.py::test_concurrent_task_mutations_have_one_winner` | ✅ Verified |
| **Task Review Workflow** | `tests/test_tasks.py::test_review_workflow_attributes_mover_and_credits_submitter` | ✅ Verified |
| **Comments, Activity, Alerts**| `tests/test_comments_notifications_activity.py`, `test_projects.py` | ✅ Verified |
| **Realtime Room Scoping** | `tests/test_realtime.py::test_realtime_rooms_publish_committed_changes_and_revoke_removed_members` | ✅ Verified |
| **Payload Size Enforcements** | `tests/test_security_review.py::test_request_body_limit_rejects_large_fixed_and_chunked_bodies` | ✅ Verified |
| **Production Config Fail-Fast**| `tests/test_config_production.py` (27 URL and secret validation tests) | ✅ Verified |
| **Liveness & Readiness Probes**| `tests/test_health.py` (`/api/health`, `/api/health/ready`) | ✅ Verified |
| **End-to-End WebSocket Flow** | `scripts/smoke_test.py` (15 automated verification checks) | ✅ Verified |
| **Frontend Board Interactions**| `frontend/src/pages/BoardPage.test.jsx` (9 tests) | ✅ Verified |
| **Frontend Realtime Hook** | `frontend/src/hooks/useProjectRealtime.test.jsx` (3 tests) | ✅ Verified |
| **Accessibility Focus & ARIA** | `frontend/src/components/Accessibility.test.jsx` (8 tests) | ✅ Verified |

---

## 5. Manual QA Walkthrough Procedures

### Scenario A: Two-Browser Real-Time Synchronization & Conflict Check
**Setup:** Open Browser A (Chrome) and Browser B (Firefox or Incognito).
1. **User A:** Register and log in. Create a new project `"Collab Test"`.
2. **User B:** Register and log in.
3. **User A:** Open Project Settings $\rightarrow$ Members. Invite User B via email with role `Member`.
4. **User B:** Refresh dashboard, open `"Collab Test"` board.
5. **Real-time Creation:** User A clicks `+ Add Task` in `To do`, titles it `"Live Sync Task"`, and clicks Save.
   - *Verification:* User B's board instantly displays `"Live Sync Task"` in `To do` without refreshing.
6. **Real-time Drag-and-Drop:** User B drags `"Live Sync Task"` from `To do` to `In progress`.
   - *Verification:* User A's board smoothly updates the card's column without layout jumps or skeleton flashes.
7. **Concurrency Conflict (409):**
   - User A opens the modal for `"Live Sync Task"`.
   - User B simultaneously opens the modal for the same task and changes the title to `"Title by B"`, saving successfully.
   - User A (without closing the modal) attempts to change the title to `"Title by A"` and clicks Save.
   - *Verification:* User A receives a conflict toast notification (`409 Conflict: Task was modified by another user`). User A's modal refreshes with User B's current title.

### Scenario B: Member Removal & Instant Socket Revocation
1. User A (Owner) and User B (Member) are both viewing `"Collab Test"`.
2. User A opens Members, clicks `Remove` next to User B, and confirms.
3. *Verification:*
   - User B's browser immediately receives the `removed_from_project` event and transitions away from the board.
   - User B's active socket is evicted from `project:{project_id}`.
   - Tasks previously assigned to User B show as unassigned (`Unassigned`).

### Scenario C: Reconnection & Network Blip Handling
1. User B opens a project board (connection dot is green **Live**).
2. Open DevTools Network tab, set throttling to **Offline**.
3. *Verification:* Connection dot turns neutral **Offline**.
4. Set throttling back to **No throttling**.
5. *Verification:* Connection dot transitions to amber **Reconnecting**, re-establishes the WebSocket connection, refetches project tasks in the background, and returns to green **Live**.

### Scenario D: Keyboard Accessibility & Mobile Responsiveness
1. Press `Tab` repeatedly from page load: confirm visible focus rings on skip-to-content links, navigation items, buttons, and task cards.
2. Open a task modal using `Enter`. Verify focus is trapped within the dialog.
3. Press `Escape`: confirm the modal closes and focus returns to the initiating trigger card.
4. Open the viewport at `390px` width: confirm horizontal column scrolling, responsive action menus, and non-overlapping header badges.
