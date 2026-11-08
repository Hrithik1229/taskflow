# TaskFlow — Real-Time Collaborative Task Manager

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org)
[![React](https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=black)](https://react.dev)
[![Vite](https://img.shields.io/badge/Vite-8-646CFF?style=flat-square&logo=vite&logoColor=white)](https://vitejs.dev)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16+-4169E1?style=flat-square&logo=postgresql&logoColor=white)](https://www.postgresql.org)
[![Socket.IO](https://img.shields.io/badge/Socket.IO-4+-010101?style=flat-square&logo=socketdotio&logoColor=white)](https://socket.io)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0_Async-D71F00?style=flat-square&logo=sqlalchemy&logoColor=white)](https://www.sqlalchemy.org)
[![Tests](https://img.shields.io/badge/Tests-pytest_%7C_vitest-brightgreen?style=flat-square)](https://docs.pytest.org)

**TaskFlow** is a modern, real-time collaborative task management platform engineered for teams. It combines an asynchronous Python/FastAPI backend, an interactive React Kanban board, and PostgreSQL persistence with live Socket.IO synchronisation.

## Current Status

TaskFlow is a working MVP for local development and demonstration. The repository includes a FastAPI backend, React frontend, PostgreSQL persistence, project-scoped realtime collaboration, and automated backend/frontend test suites.

The project currently covers the core team workflow end-to-end:
- **Backend**: FastAPI, SQLAlchemy async models, Alembic migrations, JWT auth, RBAC checks, rate limiting, and project/task APIs.
- **Frontend**: React + Vite Kanban board, project navigation, task management, filtering, and realtime updates.
- **Realtime**: project-scoped Socket.IO rooms, live sync, and client-side echo suppression.
- **Hardening**: PostgreSQL-shared authentication rate limits, a 1 MiB HTTP/Socket.IO payload cap, and security headers for the API and Vercel frontend hosting.
- **Validation**: The latest local run passed 268 backend tests (91% statement coverage), 86 frontend tests (69.76% statement coverage), lint/format checks, and the frontend production build. Concurrency/realtime tests passed 10 repeated runs; dependency audits reported no known vulnerabilities.
- **CI**: A GitHub Actions workflow is configured for backend Ruff + pytest and frontend ESLint + Vitest + production build checks. It has not yet been run on GitHub.

This repository is intended for local development, portfolio/demo use, and further iteration; it does not include a hosted production deployment. Before deploying, narrow `frontend/vercel.json`'s CSP `connect-src` to the final API hostname. Browser-based multi-user realtime and keyboard-accessibility checks remain manual; see the [manual QA procedure](docs/testing.md).

The guiding architectural principle is **Trustworthy Collaboration**:
- **PostgreSQL is the single source of truth.** Realtime is a delivery mechanism, not the source of truth.
- Every state change validates caller permissions against live database membership and commits to PostgreSQL in an atomic transaction before any event is broadcasted.
- Writes are guarded by **optimistic concurrency control** (`version` tracking) and advisory locking to eliminate lost updates, race conditions, and out-of-order mutations.
- Real-time updates update the DOM cleanly without page reloads, visual jumps, or layout flickering.

---

## Key Features

### 📋 Interactive Kanban Board & Tasks
- **4-Column Workflow**: `To do`, `In progress`, `Review`, and `Completed`.
- **Drag-and-Drop**: Fluid, accessible card reordering and cross-column transitions powered by `@dnd-kit`.
- **Priority Indicator Strips**: Color-coded visual accents for `Urgent` (crimson), `High` (amber), `Medium` (blue), and `Low` (slate).
- **Quick Creation**: Column-specific `+` buttons to immediately open task creation pre-set to that status.
- **Due Date & Overdue Tracking**: Formatted timestamps with highlighted overdue pills.
- **Detailed Task Modal**: Edit titles, rich descriptions, assignees, priorities, and statuses, or delete with confirmation.

### 🔍 Search, Filtering & Instant Metrics
- **Live Search**: Debounced, SQL-injection-safe search across task titles and descriptions.
- **Multi-criteria Filtering**: Filter by priority, assignee, status, or overdue status.
- **1-Click "👤 My tasks"**: Instantly isolates tasks assigned to the signed-in user.
- **Filter Reset**: One-click reset pill showing active filter count.
- **Board Metrics Bar**: Live header stats displaying Total Tasks, Completed count with completion percentage, and Urgent count.

### 🔄 Review & Approval Workflow
- **Assigned Reviewer**: Submitting a task to `Review` requires selecting an assigned reviewer.
- **Separation of Duties**: Submitters cannot approve or review their own tasks.
- **Controlled Transitions**: Only the assigned reviewer, project owner, or admin can move a task out of `Review` to `In progress` or `Completed`.
- **Completion Attribution**: Automatic tracking of who completed each task and who reviewed it, persisted in task records and activity logs.

### ⚡ Real-Time Collaboration & Synchronization
- **Live Room Sockets**: Connected users join project rooms authenticated with JWT tokens.
- **Visual Connection Indicators**: Pulsating green dot for **Live**, amber for **Reconnecting**, and neutral for **Offline**.
- **Background Sync Pill**: Animated `Syncing…` badge when updates are synchronizing in the background without layout shifts.
- **Zero-Flicker Architecture**: Background refreshes and room recoveries keep existing cards mounted and preserved without flash-of-skeleton flickering.
- **Echo Suppression**: Client mutation IDs (`X-Client-Mutation-Id`) prevent echoing an author's own actions back to them.

### 🌓 Theme System (Light / Dark Mode)
- **Seamless Theme Toggle**: Accessible sun/moon switch in the navigation bar.
- **Persistent Preference**: Remembers the selected theme in `localStorage` (`taskflow_theme`).
- **System Sync**: Automatically detects and adapts to OS `prefers-color-scheme` preferences.

### 🛡️ Authentication & Role-Based Access Control (RBAC)
- **Argon2id Password Hashing**: State-of-the-art password security with `pwdlib`.
- **JWT Authentication**: Short-lived access tokens with automatic 401 recovery and memory/session storage.
- **Rate Limiting**: PostgreSQL-backed sliding-window limiter on `/api/auth/login` and `/api/auth/register` (10 req/min by IP + email, shared across application workers).
- **Enumeration-resistant registration**: New and existing email addresses receive the same generic registration confirmation; users sign in separately.
- **Role Hierarchy**: Project permissions scoped to `owner`, `admin`, and `member`.

---

## Role & Permission Matrix

Permissions are validated dynamically against PostgreSQL on every single request:

| Capability | Owner | Admin | Member |
| :--- | :---: | :---: | :---: |
| Edit project settings & delete project | ✅ | ❌ | ❌ |
| Invite & add members | ✅ (as Member or Admin) | ✅ (as Member only) | ❌ |
| Change member roles | ✅ (Promote/Demote) | ❌ | ❌ |
| Remove member | ✅ (Any non-owner) | ✅ (Members only) | ✅ (Self-removal only) |
| Create tasks | ✅ | ✅ | ✅ |
| Edit task details / delete task | ✅ (Any task) | ✅ (Any task) | ✅ (Created by or assigned to self) |
| Assign / change reviewer in `Review` | ✅ | ✅ | ✅ (Submitter or assigned reviewer) |
| Move tasks into `Review` | ✅ | ✅ | ✅ |
| Approve / reject task out of `Review` | ✅ | ✅ | ✅ (Assigned reviewer only) |
| View project board & activity | ✅ | ✅ | ✅ |

> **Note:** Removing a project member automatically unassigns their tasks in the same transaction, clears reviewer references, increments task versions, and records activity.

---

## Tech Stack

### Backend
- **Framework**: [FastAPI](https://fastapi.tiangolo.com/) (Python 3.12+)
- **ASGI Server**: [Uvicorn](https://www.uvicorn.org/) wrapped with [python-socketio](https://python-socketio.readthedocs.io/) `ASGIApp`
- **ORM & Database**: [SQLAlchemy 2.0](https://www.sqlalchemy.org/) (AsyncSession, async engine) with [asyncpg](https://github.com/MagicStack/asyncpg) & [PostgreSQL](https://www.postgresql.org/)
- **Migrations**: [Alembic](https://alembic.sqlalchemy.org/)
- **Data Validation & Settings**: [Pydantic v2](https://docs.pydantic.dev/) & [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- **Security**: [pwdlib](https://github.com/frankie567/pwdlib) with Argon2id & [PyJWT](https://pyjwt.readthedocs.io/)
- **Code Quality & Testing**: [Ruff](https://astral.sh/ruff), [pytest](https://docs.pytest.org/), [pytest-asyncio](https://github.com/pytest-dev/pytest-asyncio), [HTTPX](https://www.python-httpx.org/)

### Frontend
- **Runtime & Bundler**: [React 19](https://react.dev/) + [Vite](https://vitejs.dev/) (pure JavaScript)
- **Routing**: [React Router v7](https://reactrouter.com/)
- **Drag and Drop**: [@dnd-kit/core](https://dndkit.com/) & [@dnd-kit/sortable](https://dndkit.com/)
- **Realtime Client**: [socket.io-client](https://socket.io/docs/v4/client-api/)
- **HTTP Client**: [Axios](https://axios-http.com/) with interceptors & mutation IDs
- **Styling**: Pure CSS with design tokens (`tokens.css`), responsive layouts, and light/dark theme variables
- **Testing & Tooling**: [Vitest](https://vitest.dev/), [React Testing Library](https://testing-library.com/), [ESLint](https://eslint.org/)

---

## Project Structure

```
Real-Time Collaborative Task Manager/
├── backend/
│   ├── alembic/              # Database migration versions and env.py
│   ├── app/
│   │   ├── common/           # Error classes, rate limiting, logging
│   │   ├── models/           # SQLAlchemy 2.0 async models (Base, User, Project, Task, etc.)
│   │   ├── routers/          # FastAPI routers (auth, projects, tasks, dashboard)
│   │   ├── schemas/          # Pydantic v2 request and response schemas
│   │   ├── security/         # JWT utilities, passwords (Argon2id), permissions
│   │   ├── services/         # Business logic (transactions, task moves, audit logs)
│   │   ├── sockets/          # Socket.IO AsyncServer, handlers, rooms, auth
│   │   ├── config.py         # pydantic-settings Settings with env validation
│   │   ├── database.py       # Async engine, sessionmaker, and get_session dependency
│   │   └── main.py           # FastAPI initialization, middlewares, ASGI socketio app
│   ├── scripts/              # Database seed script for local demo data
│   ├── tests/                # Database integration and unit test suite
│   ├── requirements.txt      # Production Python dependencies
│   ├── requirements-dev.txt  # Development & test dependencies
│   └── pyproject.toml        # Ruff and pytest configuration
│
├── frontend/
│   ├── src/
│   │   ├── api/              # Axios client, auth API, health check
│   │   ├── components/       # Reusable UI (Avatar, Badge, Modal, ConfirmDialog, ThemeToggle)
│   │   ├── context/          # AuthContext, ThemeContext, ToastContext
│   │   ├── features/         # Domain modules (projects, tasks, real-time event reducer)
│   │   ├── hooks/            # useProjectRealtime and custom React hooks
│   │   ├── layouts/          # AppShell layout with sidebar, topbar, user menu
│   │   ├── pages/            # Views (DashboardPage, ProjectPage, BoardPage, MembersPage, Auth)
│   │   ├── realtime/         # Socket client management and client mutation tracker
│   │   ├── styles/           # tokens.css design system tokens and theme variables
│   │   ├── App.css           # Core SaaS styling, Kanban layout, responsive rules
│   │   └── main.jsx          # Application entrypoint
│   ├── package.json          # Frontend dependencies and npm scripts
│   ├── vite.config.js        # Vite build and Vitest configuration
│   └── eslint.config.js      # ESLint configuration
│
├── docs/
│   └── database.md           # Database schema, delete constraints, and migration details
├── docker-compose.yml        # Local PostgreSQL container service
└── README.md
```

---

## Getting Started

### Prerequisites
- **Python 3.12+**
- **Node.js 20+** and **npm**
- **Docker Compose** (recommended for local PostgreSQL) or a local PostgreSQL 15+ installation

---

### Step 1: Clone and Configure Environment

1. Set up the backend environment:
   ```bash
   cp backend/.env.example backend/.env
   ```
   *Edit `backend/.env` and supply secure random values for `APP_SECRET_KEY` and `JWT_SECRET_KEY`.*

2. Set up the frontend environment:
   ```bash
   cp frontend/.env.example frontend/.env
   ```

---

### Step 2: Start PostgreSQL Database

Using Docker Compose:
```bash
docker compose up -d db
```
This maps PostgreSQL to port `5433` on your host (container port `5432`) with development and test databases (`taskflow_dev` and `taskflow_test`). The alternate host port avoids conflicts with a locally installed PostgreSQL service.

*(Alternatively, ensure your local PostgreSQL service is running and update `DATABASE_URL` in `backend/.env` accordingly).*

---

### Step 3: Setup and Run the Backend

**PowerShell (Windows):**
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
alembic upgrade head
python -m uvicorn app.main:asgi_app --reload --port 8000
```

**Bash (Linux / macOS):**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
python -m uvicorn app.main:asgi_app --reload --port 8000
```

The API and Socket.IO server are now running on **`http://localhost:8000`**.  
Health check endpoint: **`http://localhost:8000/api/health`**.

---

### Step 4: Seed Demo Data (Optional)

In another terminal with the virtual environment activated, run:
```bash
python scripts/seed_dev.py
```
This provisions sample projects, members, and Kanban tasks with two demo accounts:
- **Owner**: `demo.owner@example.com` / `TaskFlowDemoOwner1!`
- **Member**: `demo.member@example.com` / `TaskFlowDemoMember1!`

*(These credentials are for local development fixtures only).*

---

### Step 5: Setup and Run the Frontend

Open a new terminal:
```bash
cd frontend
npm install
npm run dev
```

The frontend application will be live at **`http://localhost:5173`**.

---

## Running Tests & Quality Checks

### Backend Checks
From the `backend` directory:
```bash
# Run Ruff lint check
python -m ruff check .

# Run Ruff formatting check
python -m ruff format --check .

# Run pytest with coverage (requires PostgreSQL running for integration tests)
python -m pytest -q --cov=app --cov-report=term-missing
```

### Frontend Checks
From the `frontend` directory:
```bash
# Run ESLint
npm run lint

# Run Vitest unit & component test suite with coverage
npm run test -- --run --coverage

# Run production bundle build
npm run build
```

Latest local validation: backend 268 tests passed with 91% statement coverage;
frontend 86 tests passed with 69.76% statement coverage, and the production
build succeeded. The concurrency/realtime tests passed 10 repeated runs, and
the full npm audit reports zero vulnerabilities. See the
[test traceability and manual QA procedure](docs/testing.md) and
[security review](docs/security-review.md) for details.

---

## API Overview

### Authentication (`/api/auth`)
- `POST /api/auth/register` — Submit a registration request (`202`, generic response); sign in separately to continue.
- `POST /api/auth/login` — Sign in and receive a JWT access token (`TokenResponse`).
- `GET /api/auth/me` — Retrieve the authenticated profile (`UserRead`).

### Projects & Memberships (`/api/projects`)
- `POST /api/projects` — Create a project (caller becomes sole `owner`).
- `GET /api/projects` — List projects where caller has an active membership.
- `GET /api/projects/{project_id}` — Get project metadata, member counts, caller role.
- `PATCH /api/projects/{project_id}` — Update project name or description (Owner only).
- `DELETE /api/projects/{project_id}` — Permanently delete project and all associated tasks (Owner only).
- `GET /api/projects/{project_id}/members` — List all project collaborators.
- `POST /api/projects/{project_id}/members` — Invite/add a member by email.
- `PATCH /api/projects/{project_id}/members/{user_id}` — Change member role (Owner only).
- `DELETE /api/projects/{project_id}/members/{user_id}` — Remove member or leave project.

### Tasks & Kanban Board (`/api/tasks`)
- `GET /api/projects/{project_id}/tasks` — Query tasks with filters (`q`, `status`, `priority`, `assigned_to`, `overdue`, pagination).
- `POST /api/projects/{project_id}/tasks` — Create a task in a project.
- `GET /api/tasks/{task_id}` — Retrieve task details and review attribution.
- `PATCH /api/tasks/{task_id}` — Update task fields with optimistic `expected_version`.
- `PATCH /api/tasks/{task_id}/move` — Reorder or move task across columns with advisory locking.
- `DELETE /api/tasks/{task_id}` — Delete a task.

### Dashboard (`/api/dashboard`)
- `GET /api/dashboard/summary` — Aggregate task totals across all caller's projects (`total`, `assigned_to_me`, `overdue`, `completed`).
- `GET /api/dashboard/summary/breakdown?metric={metric}` — Group tasks by project for a specific metric.

---

## Real-Time Socket.IO Protocol

The FastAPI application and Python-SocketIO server run together as a unified ASGI app. Clients authenticate with their JWT token in the handshake auth object and join rooms scoped to their projects (`project:{project_id}`).

| Event Name | Room Scope | Payload Details |
| :--- | :--- | :--- |
| `task_created` | `project:{project_id}` | Full created task payload + actor summary |
| `task_updated` | `project:{project_id}` | Updated task payload with incremented `version` |
| `task_moved` | `project:{project_id}` | Moved task, updated positions, and affected sibling patches |
| `task_deleted` | `project:{project_id}` | Tombstone payload with deleted task ID |
| `member_changed` | `project:{project_id}` | Action (`added`, `role_changed`, `removed`) and member summary |
| `removed_from_project` | `user:{user_id}` | Direct revocation alert instructing client to leave room |
| `project_updated` | `project:{project_id}` | Updated project title and description |
| `project_deleted` | `project:{project_id}` | Project deletion alert navigating members to dashboard |

---

## Database Architecture

For complete database documentation including constraints, foreign keys, cascade rules, advisory locks, and migration histories, refer to:
📖 **[docs/database.md](./docs/database.md)**

---

## Licensing

This repository does not currently include a `LICENSE` file, so there is no formal public license assigned yet. Treat the code as a private portfolio/demo project unless a license is added later.
