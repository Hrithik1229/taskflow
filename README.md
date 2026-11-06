# TaskFlow

TaskFlow is a real-time collaborative task manager for teams. Its foundation is
built around a FastAPI backend, a React frontend, PostgreSQL, and Socket.IO.

## Features

- Create projects, manage memberships and roles, and enforce project-scoped
  permissions.
- Organize assigned work on a Kanban board with priorities, due dates, filters,
  and optimistic concurrency protection.
- Submit tasks for review, assign reviewers, and track completion attribution.
- See dashboard totals and open per-project task breakdowns.
- Receive live project updates and personal notifications over Socket.IO.
- Sign in with JWT authentication and manage a light/dark theme.

## Stack

- Backend: Python, FastAPI, SQLAlchemy async, PostgreSQL, Socket.IO
- Frontend: React, Vite, JavaScript, React Router
- Tests and tooling: pytest, Ruff, Vitest, React Testing Library, ESLint

## Prerequisites

- Python 3.12 or newer
- Node.js 20 or newer and npm
- Docker Compose (optional, for local PostgreSQL)

## Local setup

1. Copy `backend/.env.example` to `backend/.env` and replace both development
   secret placeholders with long, unique random values. These files are local
   configuration and must never be committed.
2. Copy `frontend/.env.example` to `frontend/.env`.
3. Start PostgreSQL with `docker compose up -d db`. The Compose
   defaults (`taskflow_dev` / `taskflow_dev_only`) are for local development
   only. On first initialization, Compose also creates the `taskflow_test`
   database used by integration tests.
4. In a PowerShell terminal:

   ```powershell
   cd backend
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements-dev.txt
   alembic upgrade head
   ```

   If PowerShell blocks activation, use
   `.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt` and
   `.\.venv\Scripts\python.exe -m alembic upgrade head`.
5. In another terminal, install and start the frontend:

   ```powershell
   cd frontend
   npm install
   npm run dev
   ```
6. Start the API from `backend` in a separate terminal:

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn app.main:asgi_app --reload --port 8000
   ```
7. Open the Vite URL printed in the terminal (normally
   `http://localhost:5173`). The backend health endpoint is
   `http://localhost:8000/api/health`.

The frontend uses the health endpoint to display the real API connection
state. The API and Socket.IO share port 8000. `backend/.env.example` contains
the local database URLs and allowed CORS origins; do not use the development
defaults or example secrets outside a local environment.

## Tests and checks

Run backend checks from `backend` (PostgreSQL must be running for the full
database-backed suite):

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pytest -q
```

Run frontend checks from `frontend`:

```powershell
npm run lint
npm run test -- --run
npm run build
```

## Authentication

Registration is available at `POST /api/auth/register` and creates a user
without returning a token; the frontend signs in immediately afterward.
`POST /api/auth/login` issues a single short-lived access JWT (30 minutes by
default), and `GET /api/auth/me` validates it and loads the current user from
PostgreSQL. There is intentionally no refresh-token endpoint. The browser
keeps the access token in memory and `sessionStorage`, clears it on a protected
401, and returns the user to sign-in. Passwords must be 8–128 characters; no
additional character-composition rule is imposed.

Login and registration have an in-memory sliding-window limit (10 requests per
minute by IP and by normalized email by default). This is process-local and
intended for the single-worker MVP; distributed deployments need a shared
rate-limit store.

For development only, run `python scripts/seed_dev.py` from `backend` after
migrations. It creates demo users and a demo project with hashed passwords:

- `demo.owner@example.com` / `TaskFlowDemoOwner1!`
- `demo.member@example.com` / `TaskFlowDemoMember1!`

These credentials are public development fixtures and must never be reused
outside a local development database.

## Projects and membership

Authenticated project endpoints are available under `/api/projects`:

- `POST /api/projects` creates a project and makes its creator the sole owner.
- `GET /api/projects?offset=0&limit=20` lists only the caller's memberships.
- `GET`, `PATCH`, and `DELETE /api/projects/{project_id}` read, update, or
  delete a project.
- `GET` and `POST /api/projects/{project_id}/members` list or add members.
- `PATCH` and `DELETE /api/projects/{project_id}/members/{user_id}` change a
  role or remove a member. Non-owner members may remove themselves to leave.

Authorization is checked against a live database membership on each request.
Non-members receive `404` for project and member resources; members who lack a
permission receive `403`.

| Action | Owner | Admin | Member |
| --- | --- | --- | --- |
| Edit project settings / delete project | Yes | No | No |
| Add member | Member or admin | Member only | No |
| Change roles | Promote member or demote admin | No | No |
| Remove member | Any non-owner | Members only | Self only |
| Create task | Yes | Yes | Yes |
| Edit task fields / delete task | Any task | Any task | Created by or assigned to caller |
| Change reviewer while in Review | Any task | Any task | Submitter or current reviewer |
| Move tasks other than out of Review | Any task | Any task | Any task |
| Move from Review to In progress / Completed | Any task | Any task | Assigned reviewer only |
| View activity | Yes | Yes | Yes |

Project/member writes and their activity records commit together. Removing a
member also unassigns their project tasks in the same transaction, increments
each affected task version, clears that person's reviewer and completion-credit
references, and records activity for those changes. Project deletion does not
create an activity row because the project and its activity are deleted together.

## Tasks and board

Tasks are available through `POST` and `GET /api/projects/{project_id}/tasks`,
`GET`, `PATCH`, and `DELETE /api/tasks/{task_id}`, and
`PATCH /api/tasks/{task_id}/move`. Project task listing supports status,
assignee, priority, due-date bounds, overdue-only, literal text search (`q`),
pagination, and stable sorting. Search treats `%`, `_`, and `\` as literal
characters. Board requests can return up to 500 tasks; the frontend uses that
cap and groups tasks by status and persisted position.

Due dates must be timezone-aware; aware values are normalized to UTC. Task
updates and moves require `expected_version`. A stale write returns HTTP 409
with `code: "version_conflict"` and the current task representation. Ordering
changes use a PostgreSQL transaction advisory lock scoped to the project,
followed by deterministic task-row locks for moves. Changed sibling positions
also increment their versions. Task changes, activity rows, notifications for
assignment/reassignment and review decisions, and pending realtime event
descriptors are handled together. Task mutations accept
`X-Client-Mutation-Id`; the frontend generates one per request and suppresses
its matching socket echo.

`GET /api/dashboard/summary` returns real totals for the caller's projects:
total tasks, tasks assigned to the caller, overdue unfinished tasks, and
completed tasks. The assigned-to-me total includes completed tasks, matching
the existing summary definition. `GET /api/dashboard/summary/breakdown?metric=total`
accepts `total`, `overdue`, `completed`, or `assigned_to_me` and groups the
same metric by projects where the caller is currently a member. For example:

```http
GET /api/dashboard/summary/breakdown?metric=completed
Authorization: Bearer <access-token>
```

```json
{
  "metric": "completed",
  "total_count": 1,
  "projects": [
    {
      "project_id": "project-uuid",
      "project_name": "Launch plan",
      "count": 1,
      "has_more": false,
      "tasks": [
        {
          "id": "task-uuid",
          "title": "Review approved",
          "status": "completed",
          "priority": "high",
          "due_at": null,
          "assignee": null,
          "completed_by": { "id": "user-uuid", "username": "Taylor" }
        }
      ]
    }
  ]
}
```

Counts are exact; at most 20 task rows are returned for each project, with
`has_more` indicating truncation. Invalid metrics return 422 and non-members'
projects are omitted. `total` includes every task in current member projects;
`overdue` uses `due_at < current UTC time` and excludes completed tasks;
`completed` selects completed tasks; `assigned_to_me` includes all statuses.

Tasks cannot be created directly in Review. Move a task into Review through
`PATCH /api/tasks/{task_id}/move` and include the current member who will
review it:

```json
{
  "status": "review",
  "position": 0,
  "expected_version": 4,
  "reviewer_id": "reviewer-uuid"
}
```

The submitter cannot review their own task. While a task is in Review,
`PATCH /api/tasks/{task_id}` may include `reviewer_id` and `expected_version`;
only the submitter, current reviewer, owner, or admin may change it. Only the
assigned reviewer, owner, or admin may move a task from Review to In progress
or Completed. A Review task cannot move directly back to To do.

Task responses include small `{id, username}` summaries for the reviewer,
review submitter, last status mover, and credited completer, plus UTC status
and completion timestamps. Direct completion credits the person who moved it
to Completed. Completion from Review credits the submitter; the reviewer's
decision actor remains in the activity log. Reopening clears completion credit
and timestamp. Legacy tasks with unknown attribution remain uncredited; a
removed member's completion credit displays as “Former member”.

## Realtime events

The API and Socket.IO share the same ASGI server and port. Clients connect with
the JWT in the Socket.IO handshake `auth` payload, then join a project room.
Project membership is rechecked against PostgreSQL on every join and broadcasts
are sent only after the corresponding service transaction commits. A commit
failure emits nothing; emission failures are logged and clients recover by
refetching REST data on reconnect.

Each event includes `event_id`, `type`, `project_id`, an `{id, username}` actor
summary, UTC `occurred_at`, and nullable `client_mutation_id`. Event-specific
data contains the committed task, membership, project, or notification
representation.

| Event | Room | Data |
| --- | --- | --- |
| `task_created`, `task_updated` | `project:{id}` | `task` with its version |
| `task_moved`, `task_deleted` | `project:{id}` | `task` tombstone/representation and changed `affected` sibling patches |
| `member_changed` | `project:{id}` | Membership change action and member summary |
| `removed_from_project` | `user:{id}` | Final access-revocation notice |
| `notification_created` | `user:{recipient_id}` | Recipient's notification |
| `comment_added` | `project:{id}` | Reserved for the comments phase |
| `project_created`, `project_updated`, `project_deleted` | `project:{id}` | Project summary; project events are contract extensions |

When a member is removed, their connected sockets leave the project room before
the final user-room notice is sent. The frontend rejoins after reconnect,
replaces board data from REST, and bounds its processed-event ID set to
deduplicate deliveries. The current in-memory Socket.IO room manager is
single-worker only; multi-worker deployments require a shared client manager
(for example, Redis) and coordinated deployment configuration.

## Project documentation

- Database model, delete behavior, migrations, and test DB isolation:
  [docs/database.md](./docs/database.md)

## Development status

The project, membership, authorization, task, Kanban board, and authenticated
Socket.IO flows are implemented in the backend and frontend. Comments and
production multi-worker Socket.IO deployment are not implemented.

## Push to GitHub

Before publishing, check that the environment files contain only placeholders
and that no real secrets or private data have been added to the project. The
root `.gitignore` excludes local environment files, virtual environments,
installed dependencies, and generated build/test output while keeping the
`.env.example` templates and `frontend/package-lock.json`. No project license
is included; add a license if you intend to grant others permission to use,
modify, or distribute the project.

Create an empty GitHub repository (do not initialize it with a README or
license), then run these commands from the project root. Replace the remote
URL with your repository URL:

```powershell
git init
git add .
git status
# Confirm local .env files and generated directories are not staged.
git commit -m "Initial TaskFlow project"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repository>.git
git push -u origin main
```

If a real environment file was previously added to Git, remove it from the
index before pushing (this keeps the local file). Repeat for any other
environment file that was previously tracked:

```powershell
git rm --cached backend/.env frontend/.env
```

Review the GitHub repository's visibility and access settings before pushing.
