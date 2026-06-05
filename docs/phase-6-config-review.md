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
| 1 | Secrets from env only | Config uses pydantic-settings + `.env`; secrets only from env (`analysis/analysis/config.py:1,17-20`). `.env`/`.env.*` gitignored, only `*.env.example` tracked. **No hardcoded secrets found in tracked source** (only fake test tokens in `analysis/tests/test_trinity.py:55,60`). | Keep. Real secrets only in `/etc/cucumber/*.env` (mode 600). | P0 (confirm) |
| 2 | `SESSION_SECRET` default | Dev default `"dev-insecure-change-me"` (`analysis/analysis/config.py:64`). | Set a fresh random `SESSION_SECRET` in prod env. | P0 |
| 3 | Cookie `Secure` flag | `cookie_secure: bool = False` for localhost (`config.py:63-67`). | `SESSION_COOKIE_SECURE=true` in prod. | P0 |
| 4 | Cookie HttpOnly/SameSite | Opaque server session token exists (`auth/sessions.py:28`); cookie-set code is in-flight (auth router not yet wired in `main.py:7-17`). | When wired: `HttpOnly=true`, `SameSite=Lax`, `Path=/`, domain-scoped. | P0 |
| 5 | Auth gating on endpoints | **No auth dependency on any route** — all endpoints are open (see §A below). | State-changing POSTs require admin login; reads require login. | P0 |
| 6 | CORS | **No CORS middleware** in either app (`analysis/analysis/main.py:10-18`; `search engine/find_engine/main.py:37-41`). | Same-origin `/api` (no CORS) OR strict allowlist + `allow_credentials=true` for the UI origin. Never `"*"` with credentials. | P0 |
| 7 | DB credentials | Defaults `analysis:analysis` (`config.py:14`) and compose `findengine:findengine` (`search engine/docker-compose.yml:5-7`). | Strong generated passwords; rotate defaults. | P0 |
| 8 | DB network exposure | Compose publishes `5432:5432` to all interfaces (`docker-compose.yml:8-9`). | Bind `127.0.0.1:5432` (or `listen_addresses=localhost`); ufw blocks 5432. | P0 |
| 9 | Least-privilege DB role | App already supports split read/analysis DSNs (`config.py:22-25,69-72`; `storage/db.py:1-8`) but defaults to same role. | Create `analysis_ro` (SELECT-only) for the read DSN. | P1 |
| 10 | App server bind | uvicorn/gunicorn should bind loopback; nginx fronts TLS. (No prod server config in repo yet.) | systemd units bind `127.0.0.1`; nginx terminates TLS (see runbook). | P0 |
| 11 | Error verbosity | `FastAPI(title=..., version=...)` — no `debug=True` (`main.py:12`); proper `HTTPException` 404s (e.g. `categories.py:99`). Default prod behavior returns generic 500, no stack trace to client. | Keep `debug` off in prod; never enable `--reload`/debug behind nginx. | P1 (confirm) |
| 12 | Collector worker count | Scheduler started in FastAPI `lifespan` (`search engine/find_engine/main.py:20-34`). | Run collector with **1 uvicorn worker** to avoid duplicate cron runs. | P1 |
| 13 | Request size / input validation | Query params bounded (`scores.py:86` `ge=1`); search POST takes a JSON body (`search.py:61-63`, `SearchQueryIn`) — no explicit `max_length` on query string. | nginx `client_max_body_size 1m`; add `max_length` to `SearchQueryIn.query` and `le=` cap on `limit`. | P1 |
| 14 | Dependency hygiene | Pinned floors in `pyproject.toml` (fastapi, uvicorn, sqlalchemy, argon2-cffi, fastembed). `requires-python>=3.11` though target is 3.13. | Periodically `pip list --outdated` / `pip-audit`; pin a lockfile for the deploy venv. | P2 |
| 15 | Password hashing | argon2 via argon2-cffi (`auth/hashing.py:8-24`) — strong, verify errors → False. | Keep. | OK |
| 16 | Logging hygiene | Collector uses `logging.basicConfig(level=INFO)` (`find_engine/main.py:17`); analysis relies on gunicorn/uvicorn access logs. | Ensure login handler never logs request bodies/passwords; keep access logs free of query strings with secrets. | P1 |
| 17 | Server response header leak | uvicorn emits a `server` header. | Optional: strip/standardize `Server` header at nginx (`server_tokens off;`). | P2 |

---

## A. Endpoint inventory & auth recommendation

No router currently declares an auth dependency — every endpoint below is open to
anyone who can reach the API. The auth agent should gate them once login lands.

| Method + path | Router (`file:line`) | Type | Recommended gate |
|---|---|---|---|
| `GET /health` | `health.py:25` | read (liveness) | public OK |
| `GET /categories` | `categories.py:70` | read | login |
| `GET /categories/pending` | `categories.py:79` | read | login |
| `POST /categories/{id}/approve` | `categories.py:88` | **state-change** | **admin** |
| `POST /categories/{id}/reject` | `categories.py:101` | **state-change (delete)** | **admin** |
| `POST /classify` | `categories.py:114` | **state-change (LLM run)** | **admin** |
| `GET /tierlist` | `scores.py:19` | read | login |
| `GET /items/{id}/score` | `scores.py:56` | read | login |
| `POST /score` | `scores.py:84` | **state-change (LLM run)** | **admin** |
| `GET /items/{id}/research` | `research.py:54` | read | login |
| `GET /research` | `research.py:73` | read | login |
| `POST /research` | `research.py:101` | **state-change (web+LLM run, $$)** | **admin** |
| `POST /search` | `search.py:61` | read (semantic query) | login |
| `GET /items/{id}/competitors` | `search.py:74` | read | login |
| `POST /embed` | `search.py:87` | **state-change (embedding run)** | **admin** |

Notes:
- The four "LLM/web run" POSTs (`/classify`, `/score`, `/research`, `/embed`) trigger
  paid Trinity calls and heavy work — these are the highest-value to gate as **admin**
  (abuse = cost + load). `/research` in particular spends on web search.
- Reads expose your scored idea pipeline; for a friends-only deployment, require
  **login** for all reads except `/health`.

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

---

## C. Prioritized remediation

### P0 — must do before exposing to friends
1. **Gate state-changing endpoints behind admin login** and reads behind login
   (§A). Today every route is open. *(auth agent)*
2. **Set production cookie flags**: `SESSION_COOKIE_SECURE=true`, `HttpOnly`,
   `SameSite=Lax`, domain-scoped, when the auth router sets the cookie. *(auth agent)*
3. **Set a real `SESSION_SECRET`** in prod env (replace `dev-insecure-change-me`).
4. **Change default DB passwords** (`findengine/findengine`, `analysis/analysis`)
   and **do not expose 5432** — bind Postgres to localhost, block 5432 in ufw.
5. **CORS**: serve UI same-origin under `/api` (no CORS), or add a strict
   allowlist with `allow_credentials=true` for the exact UI origin. *(auth agent)*
6. **Front with nginx + TLS**, app bound to loopback (no plaintext / no direct
   public uvicorn).

### P1 — soon after
7. Add a **read-only `analysis_ro` DB role** for the read DSN (code already supports it).
8. Add **login rate limiting** (nginx `limit_req` on `/auth/login`) + fail2ban. *(auth agent: nginx route is `/api/auth/login`)*
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

## D. For the in-flight auth agent (hand-off)

These items belong to the auth/login work, not deployment config:

- **Cookie flags** (P0 #2): `HttpOnly=true`, `Secure` from `cookie_secure`/env,
  `SameSite=Lax`, `Path=/`, domain-scoped, `max_age = session_ttl_hours*3600`.
- **CORS** (P0 #5): add `CORSMiddleware` only if UI is cross-origin; allowlist the
  UI origin, `allow_credentials=true`, never `"*"` with credentials.
- **Endpoint gating** (P0 #1): apply an auth dependency; mark the four `*run*` POSTs
  and the approve/reject routes **admin-only**; reads require login except `/health`.
- **Login rate limiting** (P1 #8): expects nginx to proxy `/api/auth/login` →
  `/auth/login`; optionally add per-account throttle on failed `verify_password`.
- **Logging** (P1 #11): do not log the login request body or password.
```
