# TaskFlow Security Review

**Review date:** 2026-11-17
**Scope:** Repository configuration, backend authentication/authorization, HTTP and
Socket.IO surfaces, dependency audit, frontend output, and automated security
tests.

## Summary

No high-severity exploitable vulnerability was identified in this review. The
backend tests cover the principal authentication, route-authorization, cross-
project resource access, error-shaping, CORS, and Socket.IO controls. This is a
bounded repository review, not a penetration test or a certification.

The referenced acceptance sections 10.1–10.3 were not present in the
repository. Test coverage and residual validation gaps are listed in
[testing.md](./testing.md), against the acceptance bullets supplied for this
phase.

## Evidence and controls

### Secrets and configuration

- `APP_SECRET_KEY` and `JWT_SECRET_KEY` are required outside `APP_ENV=test`;
  missing secrets fail settings validation (`backend/app/config.py`).
- `.env` files are ignored, while `.env.example` templates are not ignored.
  The local `.env` files were not tracked.
- A Git-history credential-pattern scan produced six strong-pattern hits.
  Review classified them as test/CI placeholders; a broader changed-line scan
  found code references and development seed credentials, but no
  high-entropy production credential. The development seed values in
  `backend/scripts/seed_dev.py` are explicitly gated to `APP_ENV=development`.
- `gitleaks` and `trufflehog` were not available, so the custom pattern scan is
  not a substitute for a dedicated secret scanner. No credential values are
  reproduced here.
- The production frontend bundle was checked for the configured backend secret
  values; none were found.

### Dependencies

| Audit | Result |
|---|---|
| `pip-audit -r requirements-dev.txt` | No known vulnerabilities |
| `npm audit --omit=dev` | 0 vulnerabilities |
| Full `npm audit` | 0 vulnerabilities after applying the audited ESLint 9.39.5 fix |

The npm install reported that ESLint 9.39.5 is deprecated. It is the audit
remediation selected by the user; move to an audited supported ESLint release
when the dependency graph has a compatible fix path.

### Authentication and authorization

- JWTs are signed with the configured, pinned `HS256` algorithm, and expiration
  is enforced. Tests reject `alg=none`, another signing algorithm, expired
  tokens, and tampered signatures.
- Access-token lifetime defaults to 30 minutes (`ACCESS_TOKEN_EXPIRE_MINUTES`).
- Passwords use Argon2 hashing. Registration enforces username length
  3–50 characters, password length 8–128, and a maximum email length of 254.
- Login uses the same error for an unknown email and a wrong password.
  Registration returns the same generic 202 response for new and existing
  emails. The frontend shows the same confirmation and requires a separate
  sign-in; it does not automatically attempt login after registration.
- Auth rate limiting defaults to 10 attempts per 60 seconds, keyed by IP and
  email. PostgreSQL stores hashed keys and serializes updates with transaction
  advisory locks, so counters are shared across application workers/replicas.
- The OpenAPI route guard sends anonymous requests to every included API route
  and expects 401, except the explicit public-route allow-list. Project role
  checks are tested for owner/admin/member/non-member across every protected
  OpenAPI route. A separate coverage assertion fails if a protected route is
  added without a matrix entry.
- HTTP IDOR tests cover tasks, comments, project activity, and notifications
  across project boundaries. Resource scoping is enforced by project
  membership or notification ownership checks.

### Input, database, and output handling

- Pydantic schemas validate UUIDs, enums, lengths, and pagination bounds.
  Task/project/comment fields have explicit limits.
- Database access uses SQLAlchemy query construction; the source scan did not
  find string-built SQL or raw `text()` SQL execution.
- React renders content through normal JSX escaping; no
  `dangerouslySetInnerHTML` use was found.
- The ASGI request middleware rejects HTTP bodies larger than 1 MiB before
  application parsing, including requests without `Content-Length`. Socket.IO
  also uses the same 1 MiB maximum payload size.

### HTTP, CORS, Socket.IO, and errors

- CORS origins are explicit and wildcard origins are rejected by settings
  validation. Tests verify allowed and disallowed origins and allowed/denied
  preflight requests.
- Socket.IO authenticates the handshake, validates project membership before
  room joins, limits delivery to authorized project rooms, and revokes removed
  members. Tests cover unauthorized connect/join, multiple authorized
  recipients, outsider exclusion, and transactional event delivery.
- Tests verify generic 500 responses without stack traces or injected
  exception content, validation-error shape, and that login/socket logs do not
  contain passwords or access tokens.
- In production, Swagger, ReDoc, and the OpenAPI schema URLs are disabled.
- Backend responses set `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, `Referrer-Policy:
  strict-origin-when-cross-origin`, and a restrictive `Permissions-Policy`.
  Production API responses additionally set CSP and HSTS.
- [`frontend/vercel.json`](../frontend/vercel.json) configures CSP, HSTS, and
  defensive headers for a Vercel deployment. The app is not currently deployed;
  its host-agnostic `connect-src` permits HTTPS/WSS origins until the production
  API origin is known. Narrow this directive to the exact API origin at deploy
  time. The backend should receive HTTPS traffic through a trusted
  TLS-terminating ingress.

## Findings and accepted residual risks

| Severity | Finding | Status |
|---|---|---|
| Medium | Registration email enumeration via distinct duplicate response | Fixed with a generic 202 response and a non-auto-login frontend flow |
| Medium | No maximum raw JSON request-body size | Fixed with a 1 MiB HTTP and Socket.IO limit; fixed/chunked body tests added |
| Low | Auth rate limiter was process-local | Fixed with PostgreSQL-backed, transaction-serialized counters |
| Low | CSP/HSTS and frontend-host headers were not configured | Added production API headers and Vercel headers; narrow frontend `connect-src` to the final API origin before deployment |
| Low | Four moderate development npm advisories | Fixed; both production-only and full npm audits now report 0. ESLint 9.39.5 emitted a deprecation warning; see dependency note above. |
| Low | Full endpoint-by-role matrix was not automated | Fixed with a role × protected-route suite and an OpenAPI coverage guard |

No known high-severity findings remain. The only deployment-specific follow-up
is restricting the frontend CSP to the final API hostname.

## Reproduction commands

From `backend/`:

```powershell
python -m ruff check .
python -m ruff format --check .
python -m pytest -q --cov=app --cov-report=term-missing
python -m pip_audit -r requirements-dev.txt
```

From `frontend/`:

```powershell
npm audit --omit=dev
npm audit
npm run lint
npm run test -- --run --coverage
npm run build
```
