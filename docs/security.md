# TaskFlow — Security Architecture & Controls

This document summarizes the primary security controls, validation mechanisms, fail-fast production invariants, and accepted risk trade-offs implemented in TaskFlow.

For the exhaustive vulnerability assessment and automated evidence audit, refer to:  
📖 **[docs/security-review.md](./security-review.md)**

---

## 1. Core Security Controls

### A. Authentication & Credential Protection
- **Argon2id Hashing:** Password hashing uses `argon2-cffi` via `pwdlib` with memory-hard parameters resistant to GPU/ASIC cracking. Plaintext passwords are never persisted.
- **Enumeration-Resistant Registration:** `POST /api/auth/register` returns an identical `202 Accepted` response whether an email is brand new or already registered.
- **Uniform Login Failure:** `POST /api/auth/login` returns an identical generic error message for unknown emails and incorrect passwords.
- **Credential Redaction in Logs:** Custom logging handlers ensure passwords and authorization tokens are never logged.
- **Fail-Fast Secrets:** When running in `APP_ENV=production`, `Settings` strictly validates that `APP_SECRET_KEY` and `JWT_SECRET_KEY` are at least 32 characters long and rejects placeholder strings (e.g. `replace-with`).

### B. Authorization & Scoping
- **Zero Client Trust:** Identity is derived solely from server-decoded JWT claims, never from client-submitted payload user IDs.
- **Dynamic RBAC Validation:** Project permissions (`owner`, `admin`, `member`) are re-validated in PostgreSQL on every request.
- **Strict Tenant Isolation:** Cross-project queries (IDOR attempts) for tasks, comments, and members fail with `404 Not Found` or `403 Forbidden`.
- **Automated Matrix Verification:** A dedicated test suite (`test_authorization_matrix.py`) enforces that every registered protected route has an explicit role permission test.

### C. Rate Limiting & Denial of Service (DoS) Defense
- **PostgreSQL-Shared Rate Limiter:** `POST /api/auth/login` and `/api/auth/register` enforce a sliding-window rate limit (10 req/min per IP + email). Rate-limit attempts are recorded in PostgreSQL (`auth_rate_limit_attempts`) with serialized transaction advisory locks, ensuring counters are shared across all backend workers.
- **Payload Size Caps:** An ASGI middleware intercepts all incoming HTTP requests before body parsing and rejects payloads larger than 1 MiB (`MAX_REQUEST_BODY_BYTES`), including chunked streams.
- **Socket.IO Buffer Limits:** The Socket.IO server configures `max_http_buffer_size = 1_048_576` bytes, mirroring the HTTP limit.

### D. Real-Time WebSocket Security
- **Handshake Authentication:** Socket connections require a valid JWT token in the handshake auth object.
- **Room Authorization:** Emitting `join_project` re-verifies the user's active membership in PostgreSQL before entering the room.
- **Immediate Revocation:** Removing a member from a project automatically evicts all their active sockets from the room and emits a direct revocation event.
- **Strict Outbox Boundary:** WebSocket events are only broadcast *after* the underlying database transaction has successfully committed (`publish_outbox_after_commit`).

### E. HTTP & Transport Security
- **Strict CORS:** Wildcard origins (`*`) are disallowed by settings validation. In `production`, origins must explicitly start with `https://`.
- **Security Headers:** Every response from FastAPI and Nginx/Vercel includes:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `Permissions-Policy: geolocation=(), microphone=(), camera=()`
  - `Strict-Transport-Security: max-age=31536000` (in production)
- **Docs Disabled in Production:** Interactive API documentation (`/docs`, `/redoc`, `/openapi.json`) is disabled in production mode.

---

## 2. Accepted Risks & Architectural Boundaries

| Area | Accepted Risk | Rationale / Mitigation |
| :--- | :--- | :--- |
| **Token Architecture** | Access tokens are short-lived (30 min) without refresh tokens. | Chosen to eliminate complex refresh-token rotation and revocation storage for the MVP. Expired tokens require re-login. |
| **Single-Worker Realtime** | In-memory Socket.IO client manager runs on a single ASGI worker. | Acceptable for MVP. Scaling horizontally requires adding a Redis broker (`socketio.AsyncRedisManager`). |
| **Board Task Cap** | Single project boards return up to 500 tasks without infinite scroll. | Protects the client DOM from unbounded re-rendering overhead and keeps Kanban drag-and-drop performant. |
| **Database Scale-to-Zero** | Neon serverless database suspends after 5 min idle. | Connections recycle every 300s with `pool_pre_ping=True` to seamlessly wake the database on demand. |
