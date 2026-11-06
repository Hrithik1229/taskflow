# Database schema

The backend uses PostgreSQL with SQLAlchemy's async engine and Alembic. IDs are
created with Python `uuid4`; PostgreSQL does not need an extension. Timestamp
columns use `TIMESTAMP WITH TIME ZONE`, default to PostgreSQL `now()` where
appropriate, and Python-generated timestamps use UTC.

## Tables

| Table | Key columns | Constraints and indexes |
|---|---|---|
| `users` | `id`, normalized `email`, `username`, `password_hash` | Unique email; lowercase/trimmed email check; created/updated timestamps |
| `projects` | `id`, `name`, nullable `description`, `owner_id` | Owner FK; owner lookup index; created/updated timestamps |
| `project_members` | `project_id`, `user_id`, `role`, `joined_at` | Unique project/user pair; role check; partial unique owner index; project and user indexes |
| `tasks` | `project_id`, title, status, priority, assignee, reviewer, submitter, status mover/time, completer/time, creator, due date, position, version | Status/priority checks; nonnegative position; positive version; board, assignee, reviewer, completer, and due-date indexes; nullable user references use `ON DELETE SET NULL` |
| `comments` | `task_id`, `user_id`, content, timestamps | Task/created-time lookup index |
| `activity_logs` | `project_id`, actor, action, entity, JSONB details | Project/descending-created-time index |
| `notifications` | recipient, project, nullable actor, type, JSONB payload, read/created times | Recipient/read/descending-created-time index |

Task board positions intentionally do not have a unique constraint. A move
reorders several rows in one transaction; application-level row locking and
position shifting will preserve contiguous positions without relying on a
deferrable uniqueness constraint that complicates intermediate reorder states.

The partial unique index permits at most one `owner` membership per project.
`create_project_with_owner()` creates the project and its owner membership in
one session transaction; the caller commits explicitly. Future membership
operations must preserve that owner row. Project ownership is not transferred.

## Foreign-key delete behavior

- Deleting a user who owns a project is restricted. User references from
  membership, task creator, comment author, and activity actor are also
  restricted to preserve attribution and project integrity.
- Task reviewer, review submitter, status mover, and completion-credit
  references use `ON DELETE SET NULL`. Project-member removal also clears
  reviewer and completion-credit references for that project, increments the
  affected task version once, and records activity in the same transaction.
- Deleting a project cascades to its memberships, tasks, activity, and
  notifications. Deleting a task cascades to its comments.
- Deleting a task assignee sets `assigned_to` to null; deleting a notification
  actor sets `actor_id` to null, retaining the task or notification record.
- Deleting a notification recipient cascades their notifications.

## Transactions and migrations

`get_session()` yields one `AsyncSession` per request and rolls back if the
request raises. It does not commit implicitly: successful write services or
routers must explicitly commit before any realtime event is emitted.
`backend/alembic/env.py` takes its connection string from `DATABASE_URL` in
settings; `alembic.ini` intentionally contains no database URL.

Database tests require a dedicated PostgreSQL database configured by
`TEST_DATABASE_URL`. The session-scoped fixture runs `alembic upgrade head`.
Each test uses a connection-scoped outer transaction and a session configured
with `join_transaction_mode="create_savepoint"`; session commits stay inside
that outer transaction, which is rolled back after the test. The test
database must not contain data that needs to be preserved. Migration tests
explicitly downgrade to base, upgrade to head, and run Alembic's drift check.
When no test URL is configured or its PostgreSQL host is unreachable, these
integration tests are skipped with an explicit reason; database errors after
the host accepts connections remain test failures.

Migration `0002_task_review_attribution` adds reviewer and status/completion
attribution columns. It backfills the latest status mover and timestamp from
each task's most recent `task.moved` activity record when available. It does
not infer legacy completion credits.
