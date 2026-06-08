# Phase 6 — Secure-Configuration Review (current repo state)

A focused review of **Project cucumber** as it stands today, before sharing on a
small VPS with friends. This is a defensive configuration checklist — for each area:
**current state** (with `file:line`), **recommended state**, and **priority**:

- **P0** — do before exposing to friends
- **P1** — do soon after
- **P2** — nice-to-have / hardening

The deployment runbook with copy-pasteable config is in
[`phase-6-deploy-hardening.md`](./phase-6-deploy-hardening.md).

---

## Summary table

| # | Area | Current state | Recommended state | Priority |
|---|------|---------------|-------------------|----------|
| 1 | Secrets from env only | Config uses pydantic-settings + `.env`; secrets only from env (`analysis/analysis/config.py:1,17-29`). `.env`/`.env.*` gitignored, only `*.env.example` tracked. **No hardcoded secrets found in tracked source** (only fake test tokens in `analysis/tests/test_trinity.py`). | Keep. Real secrets only in `/etc/cucumber/*.env` (mode 600). | P0 (confirm) |
| 2 | `SESSION_SECRET` default | Dev default `"dev-insecure-change-me"` (`analysis/analysis/config.py:64`). | Set a fresh random `SESSION_SECRET` in prod env. | P0 |
| 3 | Cookie `Secure` flag | `cookie_secure: bool = False` for localhost (`analysis/analysis/config.py:62-67`). | `SESSION_COOKIE_SECURE=true` in prod. | P0 |
| 4 | Cookie HttpOnly/SameSite | Implemented in `set_session_cookie`: `HttpOnly=true`, `SameSite=Lax`, `Path=/`, `Secure` from config (`analysis/analysis/auth/dependencies.py:30-41`). | Keep; set `SESSION_COOKIE_SECURE=true` in prod. Add `Domain` only if deployment needs a constrained subdomain scope. | OK / P0 prod config |
| 5 | Auth gating on endpoints | Implemented: reads use `get_current_user`; state-changing routes use `require_role("admin")`; `/health` and login/logout are public (see §A). | Keep. Re-check gates when adding new routes. | OK |
| 6 | CORS | Analysis app conditionally installs `CORSMiddleware` only when `CORS_ORIGINS` is non-empty, with `allow_credentials=True` (`analysis/analysis/main.py:16-26`). Collector app still has no CORS, which is fine for internal/admin-only use. | Prefer same-origin `/api` in prod (no CORS). For cross-origin local/dev, use an exact allowlist; never `"*"` with credentials. | OK / P0 prod config |
| 7 | DB credentials | Defaults `analysis:analysis` (`config.py:14`) and compose `findengine:findengine` (`search engine/docker-compose.yml:5-7`). | Strong generated passwords; rotate defaults. | P0 |
| 8 | DB network exposure | Compose publishes `5432:5432` to all interfaces (`docker-compose.yml:8-9`). | Bind `127.0.0.1:5432` (or `listen_addresses=localhost`); ufw blocks 5432. | P0 |
| 9 | Least-privilege DB role | App already supports split read/analysis DSNs (`config.py:22-25,69-72`; `storage/db.py:1-8`) but defaults to same role. | Create `analysis_ro` (SELECT-only) for the read DSN. | P1 |
| 10 | App server bind | uvicorn/gunicorn should bind loopback; nginx fronts TLS. Copy-paste systemd/nginx config exists in the runbook. | systemd units bind `127.0.0.1`; nginx terminates TLS (see runbook). | P0 |
| 11 | Error verbosity | `FastAPI(title=..., version=...)` — no `debug=True` (`main.py:12`); proper `HTTPException` 404s (e.g. `categories.py:99`). Default prod behavior returns generic 500, no stack trace to client. | Keep `debug` off in prod; never enable `--reload`/debug behind nginx. | P1 (confirm) |
| 12 | Collector worker count | Scheduler started in FastAPI `lifespan` (`search engine/find_engine/main.py:20-34`). | Run collector with **1 uvicorn worker** to avoid duplicate cron runs. | P1 |
| 13 | Request size / input validation | Many query params have lower bounds (`ge=1`; see `scores.py`, `research.py`, `search.py`), and `min_coefficient` has `0..1`; search POST still has no explicit `max_length` on query string. | nginx `client_max_body_size 1m`; add `max_length` to `SearchQueryIn.query` and `le=` caps on list/search limits. | P1 |
| 14 | Dependency hygiene | Pinned floors in `pyproject.toml` (fastapi, uvicorn, sqlalchemy, argon2-cffi, fastembed). `requires-python>=3.11` though target is 3.13. | Periodically `pip list --outdated` / `pip-audit`; pin a lockfile for the deploy venv. | P2 |
| 15 | Password hashing | argon2 via argon2-cffi (`auth/hashing.py:8-24`) — strong, verify errors → False. | Keep. | OK |
| 16 | Logging hygiene | Collector uses `logging.basicConfig(level=INFO)` (`find_engine/main.py:17`); analysis relies on gunicorn/uvicorn access logs. | Ensure login handler never logs request bodies/passwords; keep access logs free of query strings with secrets. | P1 |
| 17 | Server response header leak | uvicorn emits a `server` header. | Optional: strip/standardize `Server` header at nginx (`server_tokens off;`). | P2 |

---

## A. Endpoint inventory & auth gates

Current analysis API gates are implemented in the routers. Public endpoints are
limited to liveness and session creation/destruction; reads require any active
user; state-changing moderation/analysis runs require `admin`.

| Method + path | Router (`file:line`) | Type | Current gate |
|---|---|---|---|
| `GET /health` | `health.py:25` | read (liveness) | public OK |
| `POST /auth/login` | `auth.py:27` | session create | public |
| `POST /auth/logout` | `auth.py:52` | session revoke | public, revokes if cookie exists |
| `GET /auth/me` | `auth.py:70` | read current user | `viewer+` (`get_current_user`) |
| `GET /categories` | `categories.py:71` | read | `viewer+` |
| `GET /categories/pending` | `categories.py:81` | read | `viewer+` |
| `POST /categories/{id}/approve` | `categories.py:91` | **state-change** | **admin** |
| `POST /categories/{id}/reject` | `categories.py:105` | **state-change (delete)** | **admin** |
| `POST /classify` | `categories.py:119` | **state-change (LLM run)** | **admin** |
| `GET /tierlist` | `scores.py:20` | read | `viewer+` |
| `GET /items/{id}/score` | `scores.py:58` | read | `viewer+` |
| `POST /score` | `scores.py:87` | **state-change (LLM run)** | **admin** |
| `GET /items/{id}/research` | `research.py:55` | read | `viewer+` |
| `GET /research` | `research.py:75` | read | `viewer+` |
| `POST /research` | `research.py:104` | **state-change (web+LLM run, $$)** | **admin** |
| `POST /search` | `search.py:62` | read (semantic query) | `viewer+` |
| `GET /items/{id}/competitors` | `search.py:76` | read | `viewer+` |
| `POST /embed` | `search.py:90` | **state-change (embedding run)** | **admin** |

Notes:
- The four "LLM/web run" POSTs (`/classify`, `/score`, `/research`, `/embed`) trigger
  paid Trinity calls and heavy work — these are the highest-value to gate as **admin**
  (abuse = cost + load). `/research` in particular spends on web search.
- Reads expose your scored idea pipeline; current code requires login for all reads
  except `/health`.

---

## B. Notes on items that are already healthy

- **No secrets in tracked code.** A scan of tracked `.py/.toml/.ini` found no
  hardcoded credentials/tokens — only fixture strings in `tests/test_trinity.py`.
  The `dev-insecure-change-me` and `analysis:analysis` values are overridable
  env **defaults**, not committed live secrets.
- **Env-only secret pattern** is correctly implemented (pydantic-settings,
  `extra="ignore"`, `.env` gitignored).
- **Passwords** are argon2-hashed; never stored plaintext (`auth/hashing.py`).
- **Sessions** are opaque DB tokens with TTL + `is_active` checks
  (`auth/sessions.py:35-61`), revocable on logout — good design, not JWT.
- **Auth/RBAC gates** are now wired on analysis routes; UI also hides admin-only
  actions from non-admin users, while the API remains the source of truth.
- **Credentialed CORS** is available for local/cross-origin UI via explicit
  `CORS_ORIGINS`; default empty config keeps production same-origin deployments simple.

---

## C. Prioritized remediation

### P0 — must do before exposing to friends
1. **Set production cookie flags**: `SESSION_COOKIE_SECURE=true`; `HttpOnly`,
   `SameSite=Lax` and `Path=/` are already set by code (§A/B).
2. **Set a real `SESSION_SECRET`** in prod env (replace `dev-insecure-change-me`).
3. **Change default DB passwords** (`findengine/findengine`, `analysis/analysis`)
   and **do not expose 5432** — bind Postgres to localhost, block 5432 in ufw.
4. **CORS**: serve UI same-origin under `/api` (no CORS), or set a strict
   `CORS_ORIGINS` allowlist with `allow_credentials=true` for the exact UI origin.
5. **Front with nginx + TLS**, app bound to loopback (no plaintext / no direct
   public uvicorn).
6. **Re-check endpoint gates** after every new route; use §A as the expected model.

### P1 — soon after
7. Add a **read-only `analysis_ro` DB role** for the read DSN (code already supports it).
8. Add **login rate limiting** (nginx `limit_req` on `/api/auth/login`) + fail2ban.
9. Add **input bounds**: `max_length` on `SearchQueryIn.query`, `le=` cap on `limit`
   params; nginx `client_max_body_size 1m`.
10. Run the **collector with a single worker**; confirm no debug mode in prod.
11. **Logging hygiene**: ensure the login handler never logs request bodies/passwords.

### P2 — nice-to-have
12. Lockfile + periodic `pip-audit` / `pip list --outdated`; align `requires-python`
    to 3.13.
13. `server_tokens off;` in nginx; strip server version headers.
14. Off-box backup copies; periodic restore drills.

---

## D. Auth/RBAC implementation notes

- Cookie flags are centralized in `analysis/analysis/auth/dependencies.py`, not
  duplicated in the router.
- CORS is configured in `analysis/analysis/main.py` from `CORS_ORIGINS`; wildcard
  origins are not appropriate with cookie credentials.
- Endpoint gates are per-route dependencies in `analysis/analysis/api/routers/*`.
  Keep this explicit style when adding endpoints.
- Login rate limiting is still deployment-level: nginx should proxy
  `/api/auth/login` → `/auth/login` and apply `limit_req` before the request reaches
  FastAPI. Optional app-level throttling can be added around failed password checks.
- Logging rule remains: do not log the login request body or password.
