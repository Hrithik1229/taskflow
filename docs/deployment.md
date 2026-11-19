# Deployment Guide — TaskFlow

> **Date verified:** 2026-11-18  
> **Backend host evaluated:** Render.com (Free/Starter Web Service)  
> **Database:** Neon (managed PostgreSQL — free tier)  
> **Frontend host:** Vercel (Vite SPA)

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Environment Variables Reference](#2-environment-variables-reference)
3. [Step 1 — Create the Managed Database and Run Migrations](#3-step-1--create-the-managed-database-and-run-migrations)
4. [Step 2 — Deploy the Backend](#4-step-2--deploy-the-backend)
5. [Step 3 — Deploy the Frontend](#5-step-3--deploy-the-frontend)
6. [Step 4 — CORS and Origin Configuration](#6-step-4--cors-and-origin-configuration)
7. [Step 5 — Verification Checklist](#7-step-5--verification-checklist)
8. [Step 6 — Backups and Recovery](#8-step-6--backups-and-recovery)
9. [Step 7 — Rollback Approach](#9-step-7--rollback-approach)
10. [Step 8 — Cold-Start and Sleep Behaviour Caveats](#10-step-8--cold-start-and-sleep-behaviour-caveats)
11. [Provider Facts and What You Must Re-verify](#11-provider-facts-and-what-you-must-re-verify)
12. [Known Risks](#12-known-risks)

---

## 1. Architecture Overview

```
Browser (Vercel CDN)
  │
  │  HTTPS + WSS
  ▼
Render Web Service   ←──── single Uvicorn worker (ASGI)
  │   FastAPI + Socket.IO (python-socketio, async_mode=asgi)
  │
  │  postgresql+asyncpg (SSL)
  ▼
Neon Managed PostgreSQL
```

**Why single worker?**  
The Socket.IO server uses an **in-memory client manager**; multiple workers maintain separate session stores and room maps. Broadcasting to `project:<id>` from worker 1 would not reach clients connected to worker 2. Scaling beyond one instance requires a Redis-backed Socket.IO manager (`socketio.AsyncRedisManager`), which is not in scope here.

**Why Render + Neon + Vercel?**

| Provider | Reason chosen |
|---|---|
| **Render** | Native ASGI/WebSocket support; persistent process (not serverless); `$PORT` env var; free tier has 750 h/month; zero config TLS |
| **Neon** | Managed PostgreSQL; free tier (1 GB, 100 CU-h/month); `sslmode=require` by default; connection pooling via PgBouncer (Neon serverless driver) |
| **Vercel** | Zero-config Vite SPA deployment; global CDN; free tier for static assets; `vercel.json` SPA rewrites supported |

---

## 2. Environment Variables Reference

### Backend (Render Web Service)

| Variable | Required | Example | Notes |
|---|---|---|---|
| `APP_ENV` | ✅ | `production` | Enables production guards, disables docs |
| `APP_SECRET_KEY` | ✅ | (32+ char hex) | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `JWT_SECRET_KEY` | ✅ | (32+ char hex) | Different from APP_SECRET_KEY |
| `DATABASE_URL` | ✅ | `postgresql://user:pass@ep-xxx.neon.tech/db?sslmode=require` | **Provider format** — the app normalises `postgres://` → `postgresql+asyncpg://` and strips/maps SSL params |
| `CORS_ORIGINS` | ✅ | `https://taskflow.vercel.app` | Comma-separated; must be `https://`; no trailing slash; no wildcard |
| `JWT_ALGORITHM` | ➖ | `HS256` | Default |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | ➖ | `30` | Default |
| `DB_POOL_SIZE` | ➖ | `3` | Base connections held open |
| `DB_MAX_OVERFLOW` | ➖ | `2` | Extra burst connections |
| `DB_POOL_RECYCLE` | ➖ | `300` | Seconds before recycling a connection |

> [!IMPORTANT]
> `DATABASE_URL` is the **raw provider URL** (may contain `sslmode=require`, `channel_binding=require`).  
> The normalisation layer in `app/config.py` → `_normalize_postgres_url()` converts it to the asyncpg-compatible form automatically. Never put `postgresql+asyncpg://` in the cloud env var — keep the raw form so the normaliser can apply SSL mapping correctly.

> [!CAUTION]
> **Secrets are baked into the JWT tokens and sessions.** Rotating `JWT_SECRET_KEY` immediately invalidates all active sessions. Rotating `APP_SECRET_KEY` invalidates any data encrypted with it. Plan for a maintenance window or implement key-rotation logic before rotating in production.

### Frontend (Vercel Project Settings → Environment Variables)

| Variable | Required | Example | Notes |
|---|---|---|---|
| `VITE_API_BASE_URL` | ✅ | `https://taskflow-api.onrender.com` | Baked into JS bundle at build time — must be the **https** URL |
| `VITE_SOCKET_URL` | ✅ | `https://taskflow-api.onrender.com` | Same origin as API; Socket.IO path is `/socket.io` (default) |

> [!NOTE]
> Vite replaces `import.meta.env.VITE_*` at **build time**. These values are embedded in the compiled JS bundle — not read at runtime. Changing them on Vercel requires a new deployment (redeploy or push a new commit). Never set secrets as `VITE_*` variables.

---

## 3. Step 1 — Create the Managed Database and Run Migrations

### 3a. Create Neon Project

1. Go to [console.neon.tech](https://console.neon.tech) → **New Project**.
2. Choose region closest to your Render deployment region.
3. Copy the **Connection string** from the dashboard. It looks like:
   ```
   postgresql://neondb_owner:<password>@ep-cool-darkness-a1b2c3d4.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require
   ```
4. Keep this URL — set it as `DATABASE_URL` on Render.

### 3b. Run Migrations

**Option A — Render Release Command (recommended)**  
In Render dashboard → your service → **Settings** → **Build & Deploy** → **Pre-Deploy Command**:
```
sh migrate.sh
```
This runs `alembic upgrade head` before the new instance takes traffic. If migrations fail, the deploy aborts.

**Option B — Entrypoint script (this repo default)**  
The `backend/entrypoint.sh` script runs `alembic upgrade head` before starting Uvicorn. Set the **Start Command** in Render to:
```
sh entrypoint.sh
```

**Option C — Manual one-shot (initial setup)**  
```bash
# From your machine with DATABASE_URL in environment:
cd backend
DATABASE_URL="postgresql://..." alembic upgrade head
```

> [!WARNING]
> **Never use `SQLAlchemy.metadata.create_all()`** in production. It has no concept of incremental schema changes and cannot apply ALTER TABLE statements. Only Alembic manages the production schema.

**Verify migration ran:**
```sql
-- In Neon SQL Editor:
SELECT version_num FROM alembic_version;
-- Should show the latest revision (e.g. 0003_...)
```

---

## 4. Step 2 — Deploy the Backend

### On Render.com

1. **Connect** your GitHub repository.
2. Create a **Web Service** → select the repo.
3. **Settings:**

   | Setting | Value |
   |---|---|
   | **Root Directory** | `backend` |
   | **Runtime** | Docker |
   | **Dockerfile Path** | `Dockerfile` |
   | **Start Command** | (leave blank — CMD in Dockerfile / entrypoint.sh) |
   | **Plan** | Free or Starter |
   | **Region** | Same as Neon |

4. **Environment Variables** → add all variables from [Section 2](#2-environment-variables-reference).
5. **Pre-Deploy Command** (optional, Starter plan): `sh migrate.sh`

6. Click **Deploy**. First deploy takes ~3 min (Docker build).

**Post-deploy verification:**
```bash
curl https://taskflow-api.onrender.com/api/health
# → {"status":"ok"}

curl https://taskflow-api.onrender.com/api/health/ready
# → {"status":"ready"}
```

### Socket.IO and WebSocket proxy requirements

Render's TLS termination proxy:
- **Forwards** WebSocket upgrade headers — no extra config needed.
- **Timeout:** Render's proxy has a 55-second idle timeout for HTTP but WebSocket connections stay alive as long as frames are exchanged. The Socket.IO client sends periodic heartbeats (default `pingInterval=25s`, `pingTimeout=20s`) which keeps the connection alive.
- **Sticky sessions:** NOT needed for a single-worker deployment. With WebSocket transport, each client maintains a persistent TCP connection to the same process. If you scale to multiple workers in future, you need sticky sessions (load-balancer affinity) OR a Redis-backed Socket.IO manager.
- **Polling fallback:** If WebSocket upgrade fails (e.g., some corporate proxies strip Upgrade headers), Socket.IO falls back to HTTP long-polling. This works on Render but each poll request is a new HTTP round-trip and has much higher latency. On multi-instance deployments, polling requires sticky sessions; WebSocket transport does not.

---

## 5. Step 3 — Deploy the Frontend

### On Vercel

1. Import the repository at [vercel.com/new](https://vercel.com/new).
2. **Framework Preset:** Vite (auto-detected).
3. **Root Directory:** `frontend`
4. **Build Command:** `npm run build`
5. **Output Directory:** `dist`
6. **Environment Variables:**

   | Key | Value |
   |---|---|
   | `VITE_API_BASE_URL` | `https://taskflow-api.onrender.com` |
   | `VITE_SOCKET_URL` | `https://taskflow-api.onrender.com` |

7. Click **Deploy**.

The `frontend/vercel.json` already configures:
- SPA fallback rewrite (`/*` → `/index.html`)
- Security headers (CSP, HSTS, X-Frame-Options, etc.)
- Immutable cache on `/assets/*` (Vite adds content hashes)

---

## 6. Step 4 — CORS and Origin Configuration

After both services are deployed, update `CORS_ORIGINS` on Render:

```
CORS_ORIGINS=https://your-app.vercel.app
```

If you have a custom domain:
```
CORS_ORIGINS=https://app.taskflow.com,https://your-app.vercel.app
```

**Rules:**
- Always `https://` — no `http://`, no trailing slash, no wildcard
- Must match the exact `Origin` header the browser sends
- The Socket.IO server reads the same `cors_origins_list` from settings — no separate configuration needed

After changing `CORS_ORIGINS`, trigger a Render redeploy for the new value to take effect.

---

## 7. Step 5 — Verification Checklist

### Local production-like stack

```bash
# Generate secrets
python -c "import secrets; print(secrets.token_hex(32))"  # run twice

# Copy and edit env file
cp .env.prod-like.example .env.prod-like
# edit .env.prod-like: set APP_SECRET_KEY and JWT_SECRET_KEY

# Build and start
docker compose -f docker-compose.prod-like.yml --env-file .env.prod-like up --build

# In another terminal: run smoke test
python scripts/smoke_test.py --base-url http://localhost:8000
```

Expected smoke test output (all checks):
```
✓  /api/health → 200 ok
✓  /api/health/ready → 200 ready
✓  Register user A
✓  Register user B
✓  Login user A → got token
✓  Login user B → got token
✓  Create project
✓  Add user B to project
✓  UserA WebSocket connected
✓  UserB WebSocket connected
✓  Outsider WebSocket connected
✓  Create task via REST
✓  UserB received task_created event
✓  Outsider did NOT receive task_created (correct isolation)
✓  Stale-version PATCH → 409 conflict (correct)
```

### Against deployed URL

```bash
python scripts/smoke_test.py --base-url https://taskflow-api.onrender.com
```

### Manual two-browser test

1. Open `https://your-app.vercel.app` in Chrome (User A).
2. Open in Firefox or private mode (User B).
3. A registers, creates a project, invites B.
4. B accepts and opens the board.
5. A creates a task → verify B sees it appear in real-time without refresh.
6. B updates the same task concurrently with A → verify 409 conflict toast appears.
7. Check browser DevTools → Network → WS frames are present (not XHR polling).
8. Check `Origin` header on OPTIONS preflight → response has correct `Access-Control-Allow-Origin`.

### Security checks

```bash
# Docs should be hidden in production
curl -s https://taskflow-api.onrender.com/docs   # → 404
curl -s https://taskflow-api.onrender.com/openapi.json  # → 404

# No secrets in health response
curl -s https://taskflow-api.onrender.com/api/health/ready
# → {"status":"ready"}  — no DB URL, no internal identifiers

# HSTS header present
curl -I https://taskflow-api.onrender.com/api/health | grep -i strict
# → Strict-Transport-Security: max-age=31536000
```

---

## 8. Step 6 — Backups and Recovery

### What Neon provides (free tier — verify current state at console.neon.tech)

| Feature | Free Tier (as of 2026-11-18) |
|---|---|
| **Point-in-time restore** | Available on paid plans only |
| **Branch-based snapshots** | Yes — create a branch from any point in the last 7 days (Neon's history window; free tier may be shorter — verify) |
| **Automated backups** | Neon continuously archives WAL to S3 internally; restore is via branch creation or support request on free tier |

> [!IMPORTANT]
> **You must re-verify these limits** at [neon.com/docs/backup](https://neon.com/docs/backup) before relying on them. Free-tier backup policies can change without notice.

### What you must configure

- **Regular exports** (free-tier mitigation): schedule a cron job or Render cron service to run:
  ```bash
  pg_dump "$DATABASE_URL" --no-password | gzip > backup_$(date +%Y%m%d).sql.gz
  ```
  Upload to S3, Backblaze B2, or Google Cloud Storage.
- Neon's branch feature can be used as a manual snapshot before a migration:
  ```
  neon branch create --name pre-migration-$(date +%Y%m%d)
  ```

### Recovery procedure

1. Create a Neon branch from a known-good point: Neon Console → Branches → Create.
2. Set `DATABASE_URL` to the new branch's connection string.
3. Redeploy backend. Migrations will apply any new revisions.
4. Verify with `/api/health/ready`.

---

## 9. Step 7 — Rollback Approach

### Application rollback

1. In Render dashboard → **Deploys** → find the previous successful deploy → **Roll back to this deploy**.
2. Render re-deploys the old Docker image. If migrations ran on the failed deploy, the schema may be ahead of the code.

### Database migration rollback

```bash
# Roll back one revision
alembic downgrade -1

# Roll back to specific revision
alembic downgrade 0002

# Check current revision
alembic current
```

> [!WARNING]
> Alembic `downgrade` only works if the migration has a `downgrade()` function implemented. Check all migration files in `alembic/versions/` have correct downgrade paths before deploying to production.

### Safe deployment pattern

1. Run `alembic upgrade head` as a **pre-deploy step** (before traffic shifts).
2. Migrations must be **backward-compatible**: add columns as nullable, never drop columns in the same release that stops reading them.
3. If a migration must be destructive, deploy in two phases:
   - Phase 1: add new column, deploy code that reads both old and new.
   - Phase 2: drop old column after confirming Phase 1 is stable.

---

## 10. Step 8 — Cold-Start and Sleep Behaviour Caveats

### Render (backend)

| Plan | Sleep behaviour |
|---|---|
| **Free** | Spins down after **15 minutes** of no inbound traffic. Cold-start takes ~60 seconds. During cold-start, the browser sees a Render splash page; WebSocket handshakes will fail until the process is up. |
| **Starter ($7/mo)** | Always-on; no sleep. |

**Implications:**
- On the free plan, the first user after 15 minutes of inactivity waits ~60 seconds.
- WebSocket clients that were connected when the service slept will receive a disconnect event. The Socket.IO client (`socket.io-client`) will attempt reconnection. If the reconnection happens before the server is fully awake, it may fail and retry with exponential back-off.
- The `/api/health/ready` endpoint can be pinged by an external uptime monitor (e.g., UptimeRobot on a 10-minute interval) to keep the service warm — but this consumes the 750 free instance-hours/month.

### Neon (database)

| Feature | Free Tier |
|---|---|
| **Scale to zero** | After **5 minutes** of inactivity the compute (not the data) is suspended |
| **Cold-start latency** | ~300–500 ms on first query after suspend |
| **Data** | Persisted on S3-backed storage; never lost on scale-to-zero |

**Implications:**
- The first database query after a scale-to-zero event may take 300–500 ms. Combined with Render's cold-start, the first request of the day can be ~60 s (Render) + ~500 ms (Neon) slow.
- `pool_pre_ping=True` in SQLAlchemy will detect the stale connection and re-connect transparently, at the cost of one extra round-trip per request after a Neon resume.
- `pool_recycle=300` ensures connections idle longer than 5 minutes are discarded rather than reused after Neon has scaled to zero.

### Vercel (frontend)

Vercel CDN has no sleep behaviour — static assets are always served from edge nodes globally. The only "cold start" is the backend.

---

## 11. Provider Facts and What You Must Re-verify

The following facts were gathered from web search on **2026-11-18**. Provider policies change frequently; re-verify before deploying to production.

| Fact | Source (as searched) | Must re-verify |
|---|---|---|
| Render free tier sleeps after 15 min inactivity | render.com docs | ✅ Check current idle timeout |
| Render free tier: 750 instance-hours/month | render.com pricing | ✅ |
| Neon scale-to-zero: 5 min idle | neon.com docs | ✅ |
| Neon free tier: 1 GB storage, 100 CU-h/month | neon.com pricing | ✅ |
| Neon enforces SSL on all connections | neon.com docs | ✅ Verify `sslmode=require` in connection string |
| asyncpg does not accept `sslmode=` query param; use `ssl=` | asyncpg / SQLAlchemy docs | ✅ Test with actual Neon URL |
| `channel_binding=require` must be stripped from asyncpg URL | Neon / asyncpg | ✅ |
| Vercel: `vercel.json` `rewrites` supports SPA fallback | vercel.com/docs | ✅ |
| Render: native WebSocket support, no extra config | render.com docs | ✅ |
| Neon PITR available on paid plans only | neon.com/docs/backup | ✅ Verify current backup retention on free tier |

---

## 12. Known Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Render free tier cold-start (~60 s) degrades UX | Medium | Upgrade to Starter ($7/mo) or use an uptime monitor to keep warm |
| Neon free tier: 100 CU-h/month exhausted → compute paused for the month | High | Monitor usage in Neon Console; upgrade if near limit |
| Single worker: no horizontal scaling for backend | Medium | Acceptable for MVP; must add Redis-backed Socket.IO manager to scale out |
| In-memory rate limiter: resets on restart / deploy | Low | Rate limit state is lost on deploy. For strong protection, use Redis or DB-backed rate limiting |
| JWT secret rotation invalidates all sessions | Medium | Plan maintenance window; communicate to users |
| Alembic downgrade functions may be absent | Medium | Audit all migration files; add downgrade steps before first production deploy |
| No secrets in repo | ✅ Enforced | `.env` and `.env.prod-like` are git-ignored; production check rejects placeholders |
