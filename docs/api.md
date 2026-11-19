# TaskFlow — API & WebSocket Reference

This document provides the complete HTTP REST API and Socket.IO real-time protocol specification for TaskFlow.

The REST endpoints documented here are cross-referenced directly against the exported OpenAPI 3.1 specification at [`docs/openapi.json`](./openapi.json).

To regenerate `docs/openapi.json` at any time from code:
```bash
python backend/scripts/export_openapi.py
```

---

## 1. Conventions

### Authentication Scheme
All protected endpoints require an HTTP `Authorization` header containing a valid Bearer JWT:
```http
Authorization: Bearer <jwt_access_token>
```
Tokens are acquired via `POST /api/auth/login`. Unauthenticated requests to protected endpoints return `401 Unauthorized`.

### Standard Error Response Format
All errors adhere to a uniform JSON envelope:
```json
{
  "detail": "Descriptive message or array of validation errors",
  "code": "http_404"
}
```

Common status codes:
- `200 OK` — Successful query or update.
- `201 Created` — Resource successfully created.
- `202 Accepted` — Asynchronous or enumeration-safe request accepted (e.g., registration).
- `204 No Content` — Resource deleted.
- `401 Unauthorized` — Missing, expired, or invalid JWT token.
- `403 Forbidden` — Insufficient role permissions for the targeted project or resource.
- `404 Not Found` — Resource does not exist (or non-members querying project resources).
- `409 Conflict` — Optimistic concurrency version conflict (`code: "version_conflict"`).
- `422 Unprocessable Entity` — Request schema validation failure (`code: "validation_error"`).
- `429 Too Many Requests` — Rate limit exceeded (`Retry-After` header included).
- `500 Internal Server Error` — Masked server exception (stack trace never leaked).

### Concurrency & Mutation Headers
- `X-Client-Mutation-Id: <uuid>` — Optional client-generated UUID sent with mutations. Returned in WebSocket broadcasts so the authoring client can suppress self-echoes.
- `expected_version: <int>` — Mandatory integer in task updates (`PATCH /api/tasks/{id}` and `/move`). If `expected_version` does not match the database version, the server returns `409 Conflict`.

### Pagination Convention
List endpoints accept:
- `limit` (int, default 50, max 50)
- `offset` (int, default 0)

Responses include `total`, `limit`, `offset`, and the array payload.

---

## 2. Authentication Endpoints

### Register Account
```http
POST /api/auth/register
```
- **Auth:** Anonymous (Public)
- **Rate Limit:** 10 requests / 60 seconds (IP + email)
- **Body:**
  ```json
  {
    "username": "alice",
    "email": "alice@example.com",
    "password": "StrongPassword123!"
  }
  ```
- **Response (`202 Accepted`):**
  ```json
  {
    "message": "If the account can be created, the request has been accepted."
  }
  ```
- **Curl Example:**
  ```bash
  curl -X POST http://localhost:8000/api/auth/register \
    -H "Content-Type: application/json" \
    -d '{"username":"alice","email":"alice@example.com","password":"StrongPassword123!"}'
  ```

### Login
```http
POST /api/auth/login
```
- **Auth:** Anonymous (Public)
- **Rate Limit:** 10 requests / 60 seconds (IP + email)
- **Body:**
  ```json
  {
    "email": "alice@example.com",
    "password": "StrongPassword123!"
  }
  ```
- **Response (`200 OK`):**
  ```json
  {
    "access_token": "eyJhbGciOi...",
    "token_type": "bearer",
    "expires_in": 1800
  }
  ```
- **Curl Example:**
  ```bash
  curl -X POST http://localhost:8000/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"alice@example.com","password":"StrongPassword123!"}'
  ```

### Current User Profile
```http
GET /api/auth/me
```
- **Auth:** Bearer Token
- **Response (`200 OK`):**
  ```json
  {
    "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "username": "alice",
    "email": "alice@example.com",
    "created_at": "2026-11-18T10:00:00Z"
  }
  ```
- **Curl Example:**
  ```bash
  curl -X GET http://localhost:8000/api/auth/me \
    -H "Authorization: Bearer <TOKEN>"
  ```

---

## 3. Project Endpoints

### List My Projects
```http
GET /api/projects
```
- **Auth:** Bearer Token
- **Response (`200 OK`):**
  ```json
  {
    "projects": [
      {
        "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
        "name": "Sprint Alpha",
        "description": "Core product development",
        "owner_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "role": "owner",
        "member_count": 3,
        "created_at": "2026-11-18T10:00:00Z",
        "updated_at": "2026-11-18T10:00:00Z"
      }
    ]
  }
  ```

### Create Project
```http
POST /api/projects
```
- **Auth:** Bearer Token (Creator becomes `owner`)
- **Body:**
  ```json
  {
    "name": "Mobile Redesign",
    "description": "Flutter app rewrite"
  }
  ```
- **Response (`201 Created`):** `ProjectRead` object.

### Get Project Details
```http
GET /api/projects/{project_id}
```
- **Auth:** Bearer Token (Requires project membership)
- **Response (`200 OK`):** `ProjectRead` object with caller's role.

### Update Project
```http
PATCH /api/projects/{project_id}
```
- **Auth:** Bearer Token (Requires `owner` role)
- **Body:**
  ```json
  {
    "name": "Mobile Redesign 2.0",
    "description": "Updated scope"
  }
  ```
- **Response (`200 OK`):** Updated `ProjectRead`.

### Delete Project
```http
DELETE /api/projects/{project_id}
```
- **Auth:** Bearer Token (Requires `owner` role)
- **Response (`204 No Content`):** Empty. Deletes all tasks, members, and activity in cascade.

---

## 4. Member Management Endpoints

### List Project Members
```http
GET /api/projects/{project_id}/members
```
- **Auth:** Bearer Token (Project member)
- **Response (`200 OK`):**
  ```json
  {
    "members": [
      {
        "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "username": "alice",
        "email": "alice@example.com",
        "role": "owner",
        "joined_at": "2026-11-18T10:00:00Z"
      }
    ]
  }
  ```

### Add / Invite Member
```http
POST /api/projects/{project_id}/members
```
- **Auth:** Bearer Token (`owner` can add as admin or member; `admin` can add as member)
- **Body:**
  ```json
  {
    "email": "bob@example.com",
    "role": "member"
  }
  ```
- **Response (`201 Created`):** `MemberRead` object.

### Change Member Role
```http
PATCH /api/projects/{project_id}/members/{user_id}
```
- **Auth:** Bearer Token (Requires `owner` role)
- **Body:** `{"role": "admin"}`
- **Response (`200 OK`):** Updated `MemberRead`.

### Remove Member / Leave Project
```http
DELETE /api/projects/{project_id}/members/{user_id}
```
- **Auth:** Bearer Token (`owner` can remove anyone; `admin` can remove members; members can remove self)
- **Response (`204 No Content`):** Unassigns tasks and revokes socket rooms.

---

## 5. Task & Kanban Endpoints

### List Tasks
```http
GET /api/projects/{project_id}/tasks
```
- **Auth:** Bearer Token (Project member)
- **Query Filters:**
  - `status`: `todo`, `in_progress`, `review`, `completed`
  - `priority`: `low`, `medium`, `high`, `urgent`
  - `assigned_to`: UUID
  - `overdue`: bool (`true` or `false`)
  - `due_before`: ISO datetime with timezone
  - `due_after`: ISO datetime with timezone
  - `q`: Search query string (titles and descriptions)
  - `sort`: `status`, `position`, `created_at`, `updated_at`, `due_at`, `title`
  - `direction`: `asc` or `desc`
  - `limit`: int (1–50, default 50)
  - `offset`: int (default 0)
- **Response (`200 OK`):**
  ```json
  {
    "tasks": [...],
    "total": 12,
    "limit": 50,
    "offset": 0
  }
  ```

### Create Task
```http
POST /api/projects/{project_id}/tasks
```
- **Auth:** Bearer Token (Project member)
- **Headers:** `X-Client-Mutation-Id: <uuid>` (optional)
- **Body:**
  ```json
  {
    "title": "Design authentication modal",
    "description": "Support email and password fields",
    "status": "todo",
    "priority": "high",
    "assigned_to": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "due_at": "2026-11-25T18:00:00Z"
  }
  ```
- **Response (`201 Created`):** `TaskRead` object with `version: 1`.

### Get Task Details
```http
GET /api/tasks/{task_id}
```
- **Auth:** Bearer Token (Project member)
- **Response (`200 OK`):** `TaskRead` object including attribution fields (`completed_by`, `reviewer_id`, etc.).

### Update Task (with Optimistic Concurrency)
```http
PATCH /api/tasks/{task_id}
```
- **Auth:** Bearer Token (Owner/Admin or task creator/assignee)
- **Headers:** `X-Client-Mutation-Id: <uuid>` (optional)
- **Body:**
  ```json
  {
    "title": "Refined modal design",
    "priority": "urgent",
    "expected_version": 1
  }
  ```
- **Response (`200 OK`):** Updated `TaskRead` with `version: 2`.
- **Conflict Response (`409 Conflict`):** If version has evolved:
  ```json
  {
    "detail": "Task was modified by another user.",
    "code": "version_conflict",
    "current": {
      "id": "task-uuid",
      "version": 2,
      "title": "Another title",
      "updated_at": "2026-11-18T17:00:00Z"
    }
  }
  ```

### Move Task Across Columns / Reorder
```http
PATCH /api/tasks/{task_id}/move
```
- **Auth:** Bearer Token (Project member; moving out of Review requires assigned reviewer or owner/admin)
- **Body:**
  ```json
  {
    "destination_status": "in_progress",
    "destination_position": 0,
    "expected_version": 1
  }
  ```
- **Response (`200 OK`):**
  ```json
  {
    "task": { ... },
    "affected_siblings": [
      { "id": "...", "position": 1, "status": "in_progress", "version": 3 }
    ]
  }
  ```

### Delete Task
```http
DELETE /api/tasks/{task_id}
```
- **Auth:** Bearer Token (Owner/Admin or task creator)
- **Response (`204 No Content`):** Empty.

---

## 6. Comments, Notifications & Activity Endpoints

### List Comments
```http
GET /api/tasks/{task_id}/comments
```
- **Auth:** Bearer Token (Project member)
- **Response (`200 OK`):** Array of comment objects with user summaries.

### Add Comment
```http
POST /api/tasks/{task_id}/comments
```
- **Auth:** Bearer Token (Project member)
- **Body:** `{"content": "PR is ready for review."}`
- **Response (`201 Created`):** `CommentRead` object. Automatically triggers notification to task assignee.

### List Notifications
```http
GET /api/notifications
```
- **Auth:** Bearer Token
- **Query:** `unread_only=true` (optional)
- **Response (`200 OK`):** Array of user notifications with `read_at` timestamps.

### Mark Notification Read
```http
PATCH /api/notifications/{notification_id}/read
```
- **Auth:** Bearer Token (Notification recipient)
- **Response (`200 OK`):** Updated notification.

### Mark All Notifications Read
```http
PATCH /api/notifications/read-all
```
- **Auth:** Bearer Token
- **Response (`200 OK`):** `{"updated_count": 5}`.

### Project Activity Feed
```http
GET /api/projects/{project_id}/activity
```
- **Auth:** Bearer Token (Project member)
- **Query:** `limit=50`, `offset=0`
- **Response (`200 OK`):** Chronological audit records of project events.

### Recent Activity Across Projects
```http
GET /api/activity/recent
```
- **Auth:** Bearer Token
- **Query:** `limit=10`
- **Response (`200 OK`):** Recent audit records for dashboard view.

---

## 7. Health Endpoints

### Liveness Probe
```http
GET /api/health
```
- **Auth:** Public
- **Response (`200 OK`):** `{"status": "ok"}`
- Checks process liveness; does not touch the database.

### Readiness Probe
```http
GET /api/health/ready
```
- **Auth:** Public
- **Response (`200 OK`):** `{"status": "ready"}`
- **Failure (`503 Service Unavailable`):** `{"status": "unavailable"}`
- Executes a trivial database query (`SELECT 1`) to verify datastore connectivity. Leaks zero internal connection details or stack traces.

---

## 8. Real-Time Socket.IO Protocol Contract

### Connection & Handshake
- **URL Path:** `/socket.io`
- **Transports:** `["websocket", "polling"]`
- **Auth Handshake:**
  ```javascript
  const socket = io("http://localhost:8000", {
    auth: { token: "<jwt_access_token>" }
  });
  ```
- **Rejection:** Invalid or expired JWT tokens immediately raise `ConnectionRefusedError("unauthorized")`.
- **Private Room:** Every connected user automatically joins private channel `user:{user_id}` for direct notifications and eviction events.

### Client-to-Server Events

| Event | Payload | Acknowledgement Callback | Description |
| :--- | :--- | :--- | :--- |
| `join_project` | `{"project_id": "<uuid>"}` | `{"ok": true, "project_id": "..."}` or `{"ok": false, "error": "forbidden"}` | Validates active project membership and adds socket to room `project:{project_id}`. |
| `leave_project` | `{"project_id": "<uuid>"}` | `{"ok": true, "project_id": "..."}` | Removes socket from room `project:{project_id}`. |

### Server-to-Client Broadcast Events

| Event Name | Room Scope | Example Payload Envelope | Purpose |
| :--- | :--- | :--- | :--- |
| `task_created` | `project:{project_id}` | `{ "event_id": "uuid", "type": "task_created", "project_id": "...", "actor": {"id": "...", "username": "alice"}, "task": { ... }, "client_mutation_id": "opt-uuid" }` | Broadcast new task to project board |
| `task_updated` | `project:{project_id}` | `{ "event_id": "uuid", "type": "task_updated", "task": { "id": "...", "version": 2, ... }, "client_mutation_id": "..." }` | Update task details across clients |
| `task_moved` | `project:{project_id}` | `{ "event_id": "uuid", "type": "task_moved", "task": { ... }, "affected_siblings": [ ... ], "client_mutation_id": "..." }` | Reposition card on Kanban columns |
| `task_deleted` | `project:{project_id}` | `{ "event_id": "uuid", "type": "task_deleted", "task_id": "...", "client_mutation_id": "..." }` | Remove card from Kanban board |
| `comment_added` | `project:{project_id}` | `{ "event_id": "uuid", "type": "comment_added", "task_id": "...", "comment": { ... } }` | Append comment to modal thread |
| `member_changed`| `project:{project_id}` | `{ "event_id": "uuid", "type": "member_changed", "action": "added" \| "role_changed" \| "removed", "member": { ... } }` | Update member roster list |
| `notification_created` | `user:{recipient_id}` | `{ "event_id": "uuid", "type": "notification_created", "notification": { ... } }` | Trigger toast & increment badge counter |
| `removed_from_project` | `user:{user_id}` | `{ "event_id": "uuid", "type": "removed_from_project", "project_id": "..." }` | Instruct client to vacate project board |
| `project_updated` | `project:{project_id}` | `{ "event_id": "uuid", "type": "project_updated", "project": { "name": "...", "description": "..." } }` | Update project header title/desc |
| `project_deleted` | `project:{project_id}` | `{ "event_id": "uuid", "type": "project_deleted", "project_id": "..." }` | Redirect users back to dashboard |
