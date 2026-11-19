# TaskFlow — Real-Time Collaborative Task Manager

[![Status](https://img.shields.io/badge/Status-Production%20Ready%20(v1.0.0)-success?style=flat-square)](./docs/deployment.md)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org)
[![React](https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=black)](https://react.dev)
[![Vite](https://img.shields.io/badge/Vite-8-646CFF?style=flat-square&logo=vite&logoColor=white)](https://vitejs.dev)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-4169E1?style=flat-square&logo=postgresql&logoColor=white)](https://www.postgresql.org)
[![Socket.IO](https://img.shields.io/badge/Socket.IO-4+-010101?style=flat-square&logo=socketdotio&logoColor=white)](https://socket.io)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0_Async-D71F00?style=flat-square&logo=sqlalchemy&logoColor=white)](https://www.sqlalchemy.org)
[![Tests](https://img.shields.io/badge/Tests-pytest_%7C_vitest-brightgreen?style=flat-square)](https://docs.pytest.org)
[![OpenAPI](https://img.shields.io/badge/OpenAPI-3.1.0-blue?style=flat-square&logo=openapiinitiative&logoColor=white)](./docs/openapi.json)

**TaskFlow** is a production-grade, full-stack, real-time collaborative Kanban task management platform engineered for modern teams. It pairs an asynchronous Python/FastAPI backend with an interactive React 19 Kanban board, leveraging PostgreSQL 17 as the single source of truth, transactional outbox WebSocket synchronization via Socket.IO, and optimistic concurrency control (OCC).

---

## Project Status & Implementation Roadmap

All 9 development phases are **100% complete and verified**:

- [x] **Phase 1: Architecture & Schema Foundation** — PostgreSQL schema, async SQLAlchemy 2.0, Alembic migrations, Docker database container.
- [x] **Phase 2: Authentication & Multi-Tenancy** — Argon2id password hashing, JWT bearer auth, user registration/login, uniform error handling.
- [x] **Phase 3: Projects, RBAC & Core Kanban** — Project workspaces, 3-tier RBAC (`owner`, `admin`, `member`), task CRUD, `@dnd-kit` Kanban board.
- [x] **Phase 4: Real-Time Synchronization** — Socket.IO rooms, transactional outbox (emit-after-commit), echo suppression, auto-reconnect resync.
- [x] **Phase 5: Concurrency & Review Workflow** — Optimistic Concurrency Control (OCC `409 Conflict`), PostgreSQL advisory locking, separation-of-duties review gates.
- [x] **Phase 6: Collaboration & Audit Trail** — Real-time task discussion comments, unread notifications badge, project-wide activity log.
- [x] **Phase 7: UX Polish, Theming & Accessibility** — Light/Dark theme system with token variables, keyboard accessible dialogs, empty states, responsive layouts.
- [x] **Phase 8: Production Deployment Readiness** — Multi-stage non-root backend Dockerfile, Nginx SPA frontend container, production Docker Compose stack, fail-fast configuration validators, liveness/readiness health probes.
- [x] **Phase 9: Documentation & Portfolio Packaging** — OpenAPI 3.1.0 schema export, complete API/ER/Architecture/Security/Testing specs, clean-clone onboarding verification.

---

## Architecture Overview & Core Principle

The guiding principle of TaskFlow is **Trustworthy Collaboration**:
- **PostgreSQL is the single source of truth:** Real-time WebSockets are a low-latency delivery mechanism, never the persistence authority.
- **Transactional Outbox (Emit-After-Commit):** State mutations (task updates, column reordering, activity logs, notifications) occur within atomic database transactions. WebSockets broadcast strictly *after* successful transaction commit. If a transaction rolls back, zero events are emitted, preventing phantom state across clients.
- **Optimistic Concurrency Control (OCC):** Every task carries an incrementing `version` integer. Concurrent updates submitting a stale `expected_version` receive an `HTTP 409 Conflict` containing the latest entity state, preventing silent overwrites.
- **PostgreSQL Advisory Locking:** Cross-column drag-and-drop reordering acquires transaction-scoped advisory locks (`pg_advisory_xact_lock`), guaranteeing continuous sequence numbers without race conditions.
- **Echo Suppression:** Client-generated mutation identifiers (`X-Client-Mutation-Id`) are returned with socket envelopes, enabling authoring clients to ignore their own echoes and eliminate layout flickering.

For comprehensive architectural diagrams and sequence flows, see [docs/architecture.md](./docs/architecture.md).

---

## Implemented Features

### 📋 Interactive Kanban Workflow
- **4-Column Board:** `To do`, `In progress`, `Review`, and `Completed`.
- **Drag-and-Drop:** Fluid, accessible drag-and-drop reordering within and across columns powered by `@dnd-kit`.
- **Priority Bands:** Distinct visual indicators for `Urgent` (crimson), `High` (amber), `Medium` (blue), and `Low` (slate).
- **Task Management:** Create, edit title/description, update priority, assign collaborators, set due dates, and delete tasks.

### 🔄 Review & Approval Controls
- **Review Submission:** Moving a task to `Review` requires selecting an assigned reviewer.
- **Separation of Duties:** Task authors cannot approve their own tasks.
- **Gated Approval:** Only the assigned reviewer, project owner, or admin can approve or reject a task out of `Review`.
- **Attribution Auditing:** Automatically logs who submitted, reviewed, or completed each task.

### ⚡ Real-Time Multi-User Collaboration
- **Project-Scoped Rooms:** Clients join authenticated Socket.IO rooms (`project:{project_id}`) using their JWT tokens.
- **Instant Synchronization:** Card creation, moves, edits, and deletions sync across all active project members in real-time.
- **Strict Tenant Isolation:** Non-members cannot join project rooms or receive project events.
- **Live Connection State:** Visual indicator shows **Live** (green), **Reconnecting** (amber), or **Offline** (gray).
- **Automatic Resync:** Reconnection automatically triggers a background task fetch to catch up on missed events.

### 💬 Discussion Comments, Activity & Notifications
- **Task Comments:** Real-time discussion thread inside task detail modals with author avatars and timestamps.
- **In-App Notifications:** Instant bell alerts and badge counter for task assignments, review requests, and mentions.
- **Project Activity Feed:** Chronological audit trail of all project and task modifications.

### 🛡️ Authentication & Role-Based Access Control (RBAC)
- **Argon2id Hashing:** Password hashing using memory-hard Argon2id via `pwdlib`.
- **JWT Authentication:** Short-lived access tokens with automatic 401 redirect handling.
- **Enumeration-Resistant:** Registration and login endpoints return uniform responses to prevent user enumeration.
- **PostgreSQL-Shared Rate Limiting:** Sliding-window rate limiting on login/register (10 req/min per IP + email) synchronized in PostgreSQL across workers.
- **Project Roles:** Three-tier hierarchy (`owner`, `admin`, `member`) enforced dynamically in database transactions on every request.

### 🌓 Theme System & Accessibility
- **Light & Dark Mode:** Accessible sun/moon switch with persistent preference in `localStorage`.
- **System Theme Detection:** Seamlessly adapts to OS `prefers-color-scheme`.
- **Keyboard Accessible:** Tested keyboard navigation, visible focus rings, and focus trapping in dialogs.

---

## User Interface Screenshots

> *Screenshots are marked as placeholders until captured on your target display environment. Step-by-step instructions to capture reviewer-ready screenshots are provided in [docs/screenshots/README.md](./docs/screenshots/README.md).*

| Dashboard Overview | Kanban Board |
| :---: | :---: |
| *(See [docs/screenshots/README.md](./docs/screenshots/README.md))* | *(See [docs/screenshots/README.md](./docs/screenshots/README.md))* |

| Task Modal & Comments | Member Management |
| :---: | :---: |
| *(See [docs/screenshots/README.md](./docs/screenshots/README.md))* | *(See [docs/screenshots/README.md](./docs/screenshots/README.md))* |

---

## Technology Stack

| Layer | Technologies |
| :--- | :--- |
| **Backend** | Python 3.12+, FastAPI, Uvicorn, python-socketio (ASGI), SQLAlchemy 2.0 (asyncio), asyncpg, Alembic, Pydantic v2, pwdlib (Argon2id), PyJWT |
| **Frontend** | React 19, Vite 8, React Router v7, @dnd-kit (core & sortable), socket.io-client, Axios, pure CSS with design tokens (`tokens.css`) |
| **Database** | PostgreSQL 17 (relational schema, foreign key cascades, partial unique indexes, session advisory locks) |
| **Testing** | pytest, pytest-asyncio, pytest-cov, HTTPX, Vitest, React Testing Library, ESLint, Ruff |
| **Deployment** | Docker (multi-stage non-root runtime), Docker Compose, Nginx, Vercel SPA configuration |

---

## Project Structure

```
Real-Time Collaborative Task Manager/
├── backend/
│   ├── alembic/              # Database migration scripts and environment config
│   │   └── versions/         # Incremental schema migrations (0001 through 0006)
│   ├── app/
│   │   ├── common/           # Error classes, rate limiting, body size limits, advisory locks
│   │   ├── models/           # SQLAlchemy 2.0 async models (User, Project, Task, Comment, etc.)
│   │   ├── routers/          # FastAPI routers (auth, projects, tasks, dashboard, comments, notifications, activity)
│   │   ├── schemas/          # Pydantic v2 request, response, and query schemas
│   │   ├── security/         # JWT encoding/decoding, Argon2 password hashing, RBAC permissions
│   │   ├── services/         # Business logic (tasks, outbox, projects, members, activity)
│   │   ├── sockets/          # Socket.IO AsyncServer, handlers, rooms, auth, outbox emitters
│   │   ├── config.py         # pydantic-settings Settings with fail-fast production validators
│   │   ├── database.py       # Async engine, connection pooling, and get_session dependency
│   │   └── main.py           # FastAPI initialization, security headers, liveness/readiness probes
│   ├── docker/               # Initialization SQL scripts for container setups
│   ├── scripts/              # Seed script (`seed_dev.py`) and OpenAPI exporter (`export_openapi.py`)
│   ├── tests/                # Automated pytest suites (auth, tasks, realtime, security, config)
│   ├── Dockerfile            # Multi-stage production container definition (non-root appuser)
│   ├── entrypoint.sh         # Container startup script (runs alembic upgrade head, then uvicorn)
│   ├── migrate.sh            # Standalone migration script for release commands
│   ├── requirements.txt      # Production Python dependencies
│   └── requirements-dev.txt  # Development and test dependencies
│
├── frontend/
│   ├── src/
│   │   ├── api/              # Axios client, auth API, health check
│   │   ├── components/       # Reusable UI (Avatar, Badge, Modal, ConfirmDialog, ThemeToggle)
│   │   ├── context/          # AuthContext, ThemeContext, ToastContext
│   │   ├── features/         # Domain modules (tasks, projects, activity, Kanban drag-and-drop)
│   │   ├── hooks/            # useProjectRealtime and custom React hooks
│   │   ├── layouts/          # AppShell layout with sidebar, header, user menu
│   │   ├── pages/            # Views (Dashboard, ProjectPage, BoardPage, MembersPage, Auth)
│   │   ├── realtime/         # Socket.IO client manager and client mutation tracker
│   │   └── styles/           # Design tokens (`tokens.css`) and light/dark theme variables
│   ├── Dockerfile.prod       # Multi-stage Node build + Nginx static asset server
│   ├── nginx.prod.conf       # Nginx production configuration with SPA rewrites and security headers
│   ├── vercel.json           # Vercel deployment configuration (SPA rewrites and security headers)
│   └── package.json          # Frontend scripts and dependencies
│
├── docs/
│   ├── api.md                # Comprehensive REST API and Socket.IO protocol specification
│   ├── architecture.md       # Architecture diagrams, outbox sequence flows, concurrency model
│   ├── database.md           # Database schema, foreign keys, delete rules, and migration notes
│   ├── deployment.md         # Production deployment guide (Render, Neon, Vercel, Docker)
│   ├── er-diagram.md         # Entity-Relationship diagram and database constraints matrix
│   ├── openapi.json          # Exported OpenAPI 3.1 JSON schema
│   ├── resume.md             # Verifiable resume bullet points and project summary
│   ├── screenshots/          # UI screenshot guide and required asset inventory
│   ├── security.md           # Security controls summary and accepted risks
│   ├── security-review.md    # Detailed security audit report and test evidence
│   └── testing.md            # Test strategy, requirement traceability, and manual QA scripts
│
├── scripts/
│   └── smoke_test.py         # Automated end-to-end WebSocket smoke test runner
├── docker-compose.yml        # Development PostgreSQL 17 container
├── docker-compose.prod-like.yml # Full production-like stack (db + backend + frontend)
└── README.md
```

---

## Prerequisites

- **Python 3.12+**
- **Node.js 22+** and **npm**
- **Docker Compose** (recommended for local PostgreSQL) or a local PostgreSQL 16/17 server

---

## Local Setup Walkthrough (Step-by-Step)

### 1. Configure Environment Files

1. Backend environment:
   ```bash
   cp backend/.env.example backend/.env
   ```
   *(For development, the defaults in `backend/.env.example` point to local Docker PostgreSQL on port `5433`).*

2. Frontend environment:
   ```bash
   cp frontend/.env.example frontend/.env
   ```

### 2. Start PostgreSQL Database

Using the provided Docker Compose service:
```bash
docker compose up -d db
```
*Note: This starts PostgreSQL 17 mapped to port `5433` (to prevent conflicts with any local PostgreSQL service on `5432`).*

### 3. Setup and Start the Backend

**On Windows (PowerShell):**
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
alembic upgrade head
python -m uvicorn app.main:asgi_app --reload --port 8000
```

**On Linux / macOS (Bash):**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
python -m uvicorn app.main:asgi_app --reload --port 8000
```

Verify backend health:
- Liveness: `http://localhost:8000/api/health` $\rightarrow$ `{"status":"ok"}`
- Readiness: `http://localhost:8000/api/health/ready` $\rightarrow$ `{"status":"ready"}`

### 4. Seed Demo Data (Optional)

In a new terminal with the backend virtual environment activated:
```bash
python backend/scripts/seed_dev.py
```
This populates sample projects and tasks with two demo accounts:
- **Owner:** `demo.owner@example.com` / `TaskFlowDemoOwner1!`
- **Member:** `demo.member@example.com` / `TaskFlowDemoMember1!`
*(Demo fixtures for local development only).*

### 5. Setup and Start the Frontend

Open a new terminal:
```bash
cd frontend
npm install
npm run dev
```
Open **`http://localhost:5173`** in your browser.

---

## Environment Variables Reference

### Backend (`backend/.env`)

| Variable | Default (Development) | Purpose |
| :--- | :--- | :--- |
| `APP_ENV` | `development` | Environment mode (`development`, `test`, `staging`, `production`). |
| `APP_SECRET_KEY` | `replace-with-...` | General application secret key ($\ge 32$ characters in production). |
| `JWT_SECRET_KEY` | `replace-with-...` | Secret key used to sign and verify JWT access tokens. |
| `JWT_ALGORITHM` | `HS256` | Pinned JWT signing algorithm. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access token lifespan before expiration. |
| `DATABASE_URL` | `postgresql+asyncpg://...` | Asynchronous PostgreSQL connection string. |
| `TEST_DATABASE_URL` | `postgresql+asyncpg://...` | Dedicated PostgreSQL database URL for test suite. |
| `CORS_ORIGINS` | `http://localhost:5173,...` | Comma-separated allowed HTTP/HTTPS origins (no wildcards). |
| `AUTH_RATE_LIMIT_ENABLED` | `true` | Enables PostgreSQL sliding-window authentication rate limiter. |
| `AUTH_RATE_LIMIT_MAX_REQUESTS` | `10` | Maximum login/registration attempts per window. |
| `AUTH_RATE_LIMIT_WINDOW_SECONDS`| `60` | Duration of rate-limiting window in seconds. |
| `MAX_REQUEST_BODY_BYTES` | `1048576` | Maximum incoming payload size in bytes (1 MiB cap). |
| `DB_POOL_SIZE` | `3` | Number of persistent connections kept in the connection pool. |
| `DB_MAX_OVERFLOW` | `2` | Extra burst connections allowed under load. |
| `DB_POOL_RECYCLE` | `300` | Connection recycling interval in seconds (5 min). |

### Frontend (`frontend/.env`)

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `VITE_API_BASE_URL` | `http://localhost:8000/api` | Base HTTP endpoint for REST API requests. |
| `VITE_SOCKET_URL` | `http://localhost:8000` | Base origin for Socket.IO WebSocket connections. |

---

## Verification & Testing Commands

### Real Test Execution Summary (Verified 2026-11-18)
- **Backend Tests:** `python -m pytest` $\rightarrow$ **115 passed**, 177 skipped (database-integration tests require running DB), **0 failures**.
- **Production Config Tests:** `pytest tests/test_config_production.py` $\rightarrow$ **27/27 passed** (fail-fast settings, SSL, pool limits, CORS, health endpoints).
- **Frontend Tests:** `npm run test -- --run` $\rightarrow$ **86/86 passed** across 17 test suites (100% pass rate).
- **Frontend Production Build:** `npm run build` $\rightarrow$ Built production bundle in 337ms with zero errors.
- **Code Quality & Linting:** `ruff check .` (0 errors), `ruff format --check .` (77 files formatted), `npm run lint` (0 errors).
- **Production Smoke Test:** `python scripts/smoke_test.py` $\rightarrow$ **15/15 checks passed** against container stack.

```bash
# Run backend test suite
cd backend
python -m pytest -q --tb=short

# Run production configuration test suite
python -m pytest tests/test_config_production.py -q

# Run frontend test suite
cd ../frontend
npm run test -- --run

# Run frontend production build
npm run build

# Run automated end-to-end smoke test
cd ..
python scripts/smoke_test.py --base-url http://localhost:8000
```

### Interactive API Documentation & OpenAPI Schema
When the backend is running locally, access the interactive documentation:
- **Interactive Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc Alternate UI:** [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Static OpenAPI 3.1.0 Specification:** [docs/openapi.json](./docs/openapi.json) (covering all 20 REST endpoints)
- **Complete REST & Socket.IO Specification:** [docs/api.md](./docs/api.md)

---

## Two-Browser Real-Time Collaboration Walkthrough

1. Open **`http://localhost:5173`** in Chrome (User A) and in Firefox or an Incognito window (User B).
2. **User A:** Register with `alice@example.com`, log in, and create a project named `"Phoenix"`.
3. **User B:** Register with `bob@example.com` and log in.
4. **User A:** Go to Project Settings $\rightarrow$ Members, add `bob@example.com` as a `Member`.
5. **User B:** Select `"Phoenix"` from the Dashboard project list.
6. **Live Create:** User A clicks `+ Add Task` under `To do` and saves `"Design Landing Page"`.
   - *Result:* User B's board updates instantly in real-time.
7. **Live Move:** User B drags `"Design Landing Page"` to `In progress`.
   - *Result:* User A's card transitions smoothly across columns without page reloads.
8. **Concurrency Conflict:** Both users open the task modal simultaneously. User A saves an update; User B attempts to save a conflicting update.
   - *Result:* User B receives a `409 Version Conflict` toast notification preserving User A's changes.

---

## Production Deployment Summary

TaskFlow is configured for containerized deployment or cloud hosting:
- **Backend:** Ready for Render, Railway, or Fly.io as a Docker Web Service with single-worker ASGI.
- **Database:** Ready for Neon or any managed PostgreSQL 16/17 database with SSL enforcement.
- **Frontend:** Ready for Vercel edge deployment with preconfigured SPA rewrites and security headers (`frontend/vercel.json`).
- **Local Production Simulation:** A production-like stack (PostgreSQL + production backend container + Nginx frontend static build) is runnable locally via:
  ```bash
  docker compose -f docker-compose.prod-like.yml --env-file .env.prod-like up -d
  ```

For complete step-by-step production deployment instructions, backup policies, rollback plans, and cold-start caveats, see:  
📖 **[docs/deployment.md](./docs/deployment.md)**

---

## Known Limitations & Design Decisions

1. **No Refresh Tokens (MVP Design):**  
   Access tokens have a 30-minute lifespan without refresh token rotation. When an access token expires, the user must re-authenticate. This eliminates database token revocation table overhead for the MVP.
2. **Single-Worker Socket.IO Server:**  
   The Socket.IO server uses an in-memory client manager. Scaling horizontally across multiple worker processes or server instances requires adding a Redis broker (`socketio.AsyncRedisManager`), which is not in scope for this release.
3. **Board Task Limit:**  
   Individual project boards query up to 500 tasks (`BOARD_TASK_LIMIT = 500`). Boards do not implement infinite scrolling to ensure smooth `@dnd-kit` drag-and-drop performance without DOM thrashing.
4. **In-Memory Rate Limiter on Non-Auth Endpoints:**  
   Authentication endpoints (`/login`, `/register`) use PostgreSQL-shared rate limiting. General API rate limiting relies on standard proxy or gateway rate limiting.
5. **Neon Serverless Database Sleep:**  
   Neon's free tier scales to zero compute after 5 minutes of inactivity. The application handles this transparently via `pool_pre_ping=True` and `pool_recycle=300`, incurring a ~300ms wake latency on the first subsequent query.

---

## License

This repository does not currently include an open-source license. All rights are reserved by the author. Treat this project as a private portfolio demonstration.
