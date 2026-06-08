# Phase 6 — VPS Deployment & Hardening Runbook

Production deployment runbook for **Project cucumber** on a small single-VPS setup
(Ubuntu 22.04/24.04 LTS assumed). The system is two FastAPI apps plus a Postgres
database and a React UI:

| Component | Source | Process | Listens |
|-----------|--------|---------|---------|
| Analysis API | `analysis/` (`analysis.main:app`) | uvicorn workers | `127.0.0.1:8113` |
| Collector | `search engine/` (`find_engine.main:app`, internal APScheduler) | uvicorn (1 worker) | `127.0.0.1:8114` |
| Database | `pgvector/pgvector:pg16` | Docker / native | `127.0.0.1:5432` |
| UI | `ui/dist` (Vite static build) | served by nginx | n/a |

> The collector embeds an APScheduler in its FastAPI `lifespan`
> (`search engine/find_engine/main.py:20-34`), so run it as **exactly one** uvicorn
> worker — multiple workers would multiply every cron job.

Everything is fronted by **nginx** (TLS, headers, rate limiting, static UI). Only
nginx and SSH are exposed to the internet; the two app processes and Postgres bind
to loopback only.

---

## 0. Topology overview

```
                    Internet
                       │  443/80 (nginx), 22 (ssh)
                 ┌─────▼─────┐
                 │   nginx   │  TLS termination, security headers,
                 │  (root)   │  rate-limit /auth/login, serve ui/dist
                 └──┬─────┬──┘
       /api/  ──────┘     └────── /collector/ (optional, admin-only / internal)
          │                              │
   127.0.0.1:8113                 127.0.0.1:8114
   analysis API (uvicorn)         collector (uvicorn, 1 worker)
          │                              │
          └──────────┬───────────────────┘
                127.0.0.1:5432  Postgres (pgvector), loopback only
```

---

## 1. Dedicated non-root system user

Run both app processes as an unprivileged system user `cucumber`. Never run
uvicorn/gunicorn as root.

```bash
# Create a system account with no login shell and no home password
sudo useradd --system --create-home --home-dir /opt/cucumber \
     --shell /usr/sbin/nologin cucumber

# Application code lives here (read-only to the service user is ideal)
sudo mkdir -p /opt/cucumber/app
sudo git clone <your-repo-url> /opt/cucumber/app   # or rsync your build

# Runtime-writable areas (logs, virtualenvs, fastembed model cache)
sudo mkdir -p /opt/cucumber/run /opt/cucumber/logs /opt/cucumber/cache

sudo chown -R cucumber:cucumber /opt/cucumber
sudo chmod 750 /opt/cucumber /opt/cucumber/app
sudo chmod 700 /opt/cucumber/run /opt/cucumber/logs /opt/cucumber/cache
```

Permission summary:

| Path | Owner | Mode | Notes |
|------|-------|------|-------|
| `/opt/cucumber/app` | `cucumber:cucumber` | `750` | code; service user only needs read+exec |
| `/opt/cucumber/app/.venv` | `cucumber:cucumber` | `750` | per-app virtualenvs |
| `/opt/cucumber/logs` | `cucumber:cucumber` | `700` | |
| `/opt/cucumber/cache` | `cucumber:cucumber` | `700` | fastembed downloads `BAAI/bge-small-en-v1.5` here |
| `/etc/cucumber/*.env` | `cucumber:cucumber` | `600` | secrets (see §5) |

Create one virtualenv per app and install from each `pyproject.toml`
(`analysis/pyproject.toml` pins `uvicorn[standard]`, `fastapi`, `asyncpg`,
`argon2-cffi`, `fastembed`, etc.):

```bash
sudo -u cucumber python3.13 -m venv /opt/cucumber/app/analysis/.venv
sudo -u cucumber /opt/cucumber/app/analysis/.venv/bin/pip install \
     --no-cache-dir "/opt/cucumber/app/analysis" gunicorn

sudo -u cucumber python3.13 -m venv "/opt/cucumber/app/search engine/.venv"
sudo -u cucumber "/opt/cucumber/app/search engine/.venv/bin/pip" install \
     --no-cache-dir "/opt/cucumber/app/search engine"
```

---

## 2. systemd units

### 2.1 Analysis API — `gunicorn` + uvicorn workers

`/etc/systemd/system/cucumber-analysis.service`:

```ini
[Unit]
Description=Project cucumber — analysis API
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=exec
User=cucumber
Group=cucumber
WorkingDirectory=/opt/cucumber/app/analysis

# Secrets & config come ONLY from this file (mode 600, owned by cucumber)
EnvironmentFile=/etc/cucumber/analysis.env

# 2–4 uvicorn workers behind gunicorn; tune to CPU cores. Bind to loopback —
# nginx is the only thing that talks to it.
ExecStart=/opt/cucumber/app/analysis/.venv/bin/gunicorn analysis.main:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --workers 3 \
    --bind 127.0.0.1:8113 \
    --timeout 120 \
    --access-logfile - --error-logfile -

Restart=on-failure
RestartSec=3

# Cache dir for fastembed model download
Environment=FASTEMBED_CACHE_PATH=/opt/cucumber/cache
Environment=HF_HOME=/opt/cucumber/cache

# ---- Sandboxing ----
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictNamespaces=yes
RestrictRealtime=yes
RestrictSUIDSGID=yes
LockPersonality=yes
MemoryDenyWriteExecute=yes
# Only loopback + outbound to Trinity gateway are needed
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
# ProtectSystem=strict makes / read-only; whitelist the writable dirs
ReadWritePaths=/opt/cucumber/logs /opt/cucumber/cache
# App needs no elevated capabilities at all
CapabilityBoundingSet=
AmbientCapabilities=

[Install]
WantedBy=multi-user.target
```

> Note: `MemoryDenyWriteExecute=yes` is safe for pure-Python + asyncpg/argon2
> wheels. If fastembed's ONNX runtime fails to load under it, drop that one
> directive (keep all the others).

### 2.2 Collector — single worker (owns the scheduler)

`/etc/systemd/system/cucumber-collector.service`:

```ini
[Unit]
Description=Project cucumber — collector (find-engine) + scheduler
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=exec
User=cucumber
Group=cucumber
WorkingDirectory=/opt/cucumber/app/search engine
EnvironmentFile=/etc/cucumber/collector.env

# EXACTLY one worker: the FastAPI lifespan starts an APScheduler instance.
ExecStart=/opt/cucumber/app/search\x20engine/.venv/bin/uvicorn find_engine.main:app \
    --host 127.0.0.1 --port 8114 --workers 1

Restart=on-failure
RestartSec=5

NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictNamespaces=yes
RestrictRealtime=yes
RestrictSUIDSGID=yes
LockPersonality=yes
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
ReadWritePaths=/opt/cucumber/logs
CapabilityBoundingSet=
AmbientCapabilities=

[Install]
WantedBy=multi-user.target
```

> The `\x20` in the path escapes the space in `search engine`. Alternatively,
> deploy the collector to a space-free path (e.g. `/opt/cucumber/app/collector`)
> to avoid quoting pain entirely — recommended.

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now cucumber-analysis.service cucumber-collector.service
sudo systemctl status cucumber-analysis.service
journalctl -u cucumber-analysis.service -f
```

To verify the sandbox is being applied:

```bash
sudo systemd-analyze security cucumber-analysis.service   # aim for a low score
```

---

## 3. Postgres (production)

The dev compose file (`search engine/docker-compose.yml:1-19`) publishes
`5432:5432` to **all interfaces** with credentials `findengine/findengine`. That is
fine for laptop dev and **must not** ship to the VPS. Two acceptable options:

### 3.1 Option A — native Postgres (recommended for a single box)

Install Postgres 16 + the pgvector extension and bind to loopback:

```bash
# /etc/postgresql/16/main/postgresql.conf
listen_addresses = 'localhost'
```

```conf
# /etc/postgresql/16/main/pg_hba.conf  — local password auth only
host  findengine  findengine     127.0.0.1/32  scram-sha-256
host  findengine  analysis        127.0.0.1/32  scram-sha-256
host  findengine  analysis_ro     127.0.0.1/32  scram-sha-256
```

Install pgvector: `sudo apt install postgresql-16-pgvector` then
`CREATE EXTENSION vector;` in the `findengine` database.

### 3.2 Option B — keep the pgvector Docker image, bound to localhost

Keep the `pgvector/pgvector:pg16` image (it carries the extension the app needs)
but **bind the published port to 127.0.0.1 only** and inject the password from an
env file — never inline:

```yaml
# docker-compose.prod.yml
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: findengine
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}   # from .env, NOT in the file
      POSTGRES_DB: findengine
    ports:
      - "127.0.0.1:5432:5432"     # <-- loopback only, never 0.0.0.0:5432
    volumes:
      - pgdata:/var/lib/postgresql/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U findengine"]
      interval: 10s
      timeout: 5s
      retries: 5
volumes:
  pgdata:
```

### 3.3 Credentials & least-privilege roles

Change the default `findengine/findengine` and create a **read-only role** for the
analysis app's read DSN. The app already supports a separate read DSN
(`analysis/analysis/config.py:24-25`, `db_url_read` / `read_url_effective`) and a
full-rights analysis DSN, specifically so you can split privileges here without
touching code.

```sql
-- Strong, generated passwords (use `openssl rand -base64 24`)
ALTER USER findengine WITH PASSWORD '<generated>';

-- App role: full rights on the analysis-owned tables only
CREATE ROLE analysis LOGIN PASSWORD '<generated>';
GRANT CONNECT ON DATABASE findengine TO analysis;
GRANT USAGE, CREATE ON SCHEMA public TO analysis;   -- needs CREATE for Alembic
-- (or run migrations as findengine and grant only DML to analysis)

-- Read-only role: SELECT on engine tables, nothing else
CREATE ROLE analysis_ro LOGIN PASSWORD '<generated>';
GRANT CONNECT ON DATABASE findengine TO analysis_ro;
GRANT USAGE ON SCHEMA public TO analysis_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO analysis_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO analysis_ro;
```

Then in `/etc/cucumber/analysis.env`:

```
DB_URL_ANALYSIS=postgresql+asyncpg://analysis:<generated>@127.0.0.1:5432/findengine
DB_URL_READ=postgresql+asyncpg://analysis_ro:<generated>@127.0.0.1:5432/findengine
```

### 3.4 Automated backups (pg_dump cron)

`/etc/cron.d/cucumber-pgdump`:

```cron
# nightly logical backup, 02:30, keep 14 days
30 2 * * *  cucumber  /usr/local/bin/cucumber-backup.sh >> /opt/cucumber/logs/backup.log 2>&1
```

`/usr/local/bin/cucumber-backup.sh` (mode `750`, owner `cucumber`):

```bash
#!/usr/bin/env bash
set -euo pipefail
DEST=/opt/cucumber/backups
mkdir -p "$DEST"; chmod 700 "$DEST"
STAMP=$(date +%F_%H%M)
# PGPASSWORD read from a 600 ~/.pgpass or from the env file; do not hardcode
export PGPASSFILE=/etc/cucumber/.pgpass
pg_dump -h 127.0.0.1 -U findengine -d findengine -Fc \
    -f "$DEST/findengine_${STAMP}.dump"
# prune backups older than 14 days
find "$DEST" -name 'findengine_*.dump' -mtime +14 -delete
```

Test the restore path at least once: `pg_restore -d findengine_test <dump>`.
Optionally copy dumps off-box (rclone/restic to object storage).

---

## 4. nginx reverse proxy + UI

Build the UI (`ui/`) and copy `ui/dist` to `/opt/cucumber/app/ui/dist`. The UI
calls the API with credentials (HttpOnly cookie) — `ui/.env.example` sets
`VITE_API_BASE`; in production set it to your same-origin `/api` (or the public
HTTPS origin) so the cookie is first-party.

`/etc/nginx/sites-available/cucumber`:

```nginx
# ---- rate-limit zone for login (see §7) ----
limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;

# ---- HTTP -> HTTPS redirect ----
server {
    listen 80;
    listen [::]:80;
    server_name cucumber.example.com;
    # ACME challenge for certbot
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 301 https://$host$request_uri; }
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name cucumber.example.com;

    ssl_certificate     /etc/letsencrypt/live/cucumber.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/cucumber.example.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:10m;

    # ---- security response headers ----
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy "geolocation=(), microphone=(), camera=()" always;
    # Starter CSP — tighten to your bundle. frame-ancestors replaces X-Frame-Options
    # for modern browsers; keep both during transition.
    add_header Content-Security-Policy
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'" always;

    gzip on;
    gzip_types text/css application/javascript application/json image/svg+xml;
    gzip_min_length 1024;

    client_max_body_size 1m;   # API takes tiny JSON bodies; cap uploads

    # ---- UI static build ----
    root /opt/cucumber/app/ui/dist;
    index index.html;
    location / {
        try_files $uri $uri/ /index.html;   # SPA fallback
    }

    # ---- Analysis API ----
    location /api/ {
        proxy_pass http://127.0.0.1:8113/;
        proxy_http_version 1.1;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host  $host;
        # cookies pass through automatically; do not rewrite domain unless needed
        proxy_cookie_path / /;
        proxy_read_timeout 120s;
    }

    # ---- Login: stricter rate limit (see §7) ----
    location = /api/auth/login {
        limit_req zone=login burst=5 nodelay;
        proxy_pass http://127.0.0.1:8113/auth/login;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # The collector (/collector/ -> 127.0.0.1:8114) is internal/admin-only.
    # Prefer NOT exposing it publicly; reach it via SSH tunnel. If you must,
    # gate it behind auth + allow-list and a separate location block.
}
```

> Because the API is proxied under `/api/` on the **same origin** as the UI, the
> session cookie is naturally first-party and CORS is not even needed in the
> browser. If you instead host the UI on a different origin (e.g. a separate
> subdomain), you **must** configure the app's CORS allowlist with credentials —
> see §6.

Enable + TLS:

```bash
sudo ln -s /etc/nginx/sites-available/cucumber /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d cucumber.example.com   # auto-renews via systemd timer
```

After enabling HSTS, verify the renewal timer: `systemctl list-timers | grep certbot`.

---

## 5. Secrets / env management on the box

- Secrets live **only** in `/etc/cucumber/analysis.env` and
  `/etc/cucumber/collector.env`, referenced by `EnvironmentFile=`. Never in the
  repo, never in the systemd unit, never in the compose file.
- The repo already ignores env files (`.gitignore`: `.env`, `.env.*`,
  `!.env.example`) and only `*.env.example` templates are tracked — keep it that way.

```bash
sudo install -d -o cucumber -g cucumber -m 750 /etc/cucumber
sudo install -o cucumber -g cucumber -m 600 /dev/null /etc/cucumber/analysis.env
sudo install -o cucumber -g cucumber -m 600 /dev/null /etc/cucumber/collector.env
```

`/etc/cucumber/analysis.env` (mode `600`):

```
DB_URL_ANALYSIS=postgresql+asyncpg://analysis:<gen>@127.0.0.1:5432/findengine
DB_URL_READ=postgresql+asyncpg://analysis_ro:<gen>@127.0.0.1:5432/findengine
ANTHROPIC_AUTH_TOKEN=<trinity-token>
ANTHROPIC_BASE_URL=https://gate.trinity.tg/aurora
SESSION_SECRET=<openssl rand -base64 48>
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_NAME=cucumber_session
SESSION_TTL_HOURS=24
```

`/etc/cucumber/collector.env` (mode `600`): `DB_URL=...`, `GITHUB_TOKEN=...`,
Reddit creds, cron schedules (see `search engine/.env.example`).

**Rotation:** to rotate a secret (Trinity token, DB password, `SESSION_SECRET`),
edit the env file and `systemctl restart cucumber-analysis`. Rotating
`SESSION_SECRET` / DB password invalidates nothing automatically for opaque DB
sessions, but rotating the DB password requires updating the DSN. Rotate the
Trinity token and DB passwords on any suspected exposure; rotate routinely
(e.g. quarterly). Keep old `.env` backups out of the repo and `chmod 600`.

---

## 6. Production cookie/session + CORS

The app's auth is **server-side opaque sessions** with an HttpOnly cookie
(`analysis/analysis/auth/sessions.py` — `secrets.token_urlsafe(32)` stored in
Postgres, not JWT). Settings live in `analysis/analysis/config.py:59-67`.

The auth router is wired in `analysis/analysis/main.py`; cookie attributes are
centralized in `analysis/analysis/auth/dependencies.py`. Production values must be:

| Attribute | Value | Why |
|-----------|-------|-----|
| `HttpOnly` | `true` | JS cannot read the session token (XSS theft) |
| `Secure` | `true` | cookie only over HTTPS — set `SESSION_COOKIE_SECURE=true` (config default is `False` for localhost) |
| `SameSite` | `Lax` | CSRF mitigation; `Lax` works for same-origin `/api` + top-level nav |
| `Path` | `/` | scope to the app |
| `Domain` | unset by code; optionally set if needed | host-only cookie is fine for a single host; add a domain only for an intentional subdomain scope |
| name | `cucumber_session` | from `SESSION_COOKIE_NAME` |

Current `set_session_cookie` behavior:

```python
response.set_cookie(
    key=settings.session_cookie_name,
    value=token,
    max_age=settings.session_ttl_hours * 3600,
    httponly=True,
    secure=settings.cookie_secure,   # = true in prod via env
    samesite="lax",
    path="/",
)
```

**CORS:** the analysis app conditionally installs `CORSMiddleware` when
`CORS_ORIGINS` is non-empty (`analysis/analysis/main.py`). If the UI is served
same-origin under `/api` (recommended, §4), leave `CORS_ORIGINS` empty. If the UI
is on a **different origin**, set a strict CSV allowlist *with credentials* so the
browser sends the cookie:

```env
CORS_ORIGINS=https://cucumber.example.com
```

The implementation uses `allow_credentials=True`; wildcard origins are not
appropriate with cookie auth — always list exact origins.

---

## 7. Login protection (rate limit + fail2ban)

**nginx `limit_req`** (zone defined in §4): 5 requests/minute per IP to
`/api/auth/login`, with a small burst. Returns `503` when exceeded; tune `rate`
to taste. This blunts password-guessing before it reaches the app.

**fail2ban** — ban IPs that hammer login or trip nginx limits.

`/etc/fail2ban/jail.d/cucumber.conf`:

```ini
[nginx-limit-req]
enabled  = true
filter   = nginx-limit-req
port     = http,https
logpath  = /var/log/nginx/error.log
maxretry = 10
findtime = 600
bantime  = 3600

[sshd]
enabled  = true
maxretry = 5
bantime  = 3600
```

`sudo systemctl enable --now fail2ban`. For app-level lockout, the app can
additionally throttle failed `verify_password` attempts per account.

---

## 8. Firewall (ufw)

Only SSH + HTTP/HTTPS reach the box. Postgres (5432) and the two app ports
(8113/8114) are loopback-bound and must never be reachable externally.

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp        # SSH (consider limiting to your IP)
sudo ufw allow 80/tcp        # HTTP (redirect only)
sudo ufw allow 443/tcp       # HTTPS
sudo ufw enable
sudo ufw status verbose
```

Verify 5432 is closed from outside (run from another host):

```bash
nc -vz cucumber.example.com 5432    # must time out / be refused
```

If you used the Docker option, double-check Docker did not punch a hole: Docker's
iptables rules can bypass ufw. The `127.0.0.1:5432:5432` binding in §3.2 prevents
external publish; confirm with `sudo ss -ltnp | grep 5432` (should show
`127.0.0.1:5432` only, never `0.0.0.0:5432`).

---

## 9. Go-live checklist

Tick every box before sharing the URL:

- [ ] App runs as `cucumber` (non-root); `ps -o user= -C gunicorn` shows `cucumber`.
- [ ] Both systemd units active, `Restart=on-failure`, sandbox directives applied
      (`systemd-analyze security` scores low).
- [ ] `/etc/cucumber/*.env` are mode `600`, owned by `cucumber`; no secrets in repo
      (`git ls-files | grep -i env` shows only `*.example`).
- [ ] `SESSION_SECRET` set to a fresh random value (NOT `dev-insecure-change-me`).
- [ ] `SESSION_COOKIE_SECURE=true`; cookie is `HttpOnly`, `SameSite=Lax`, host-only
      unless an explicit deployment needs a `Domain`.
- [ ] Default `findengine/findengine` DB password changed; `analysis_ro` read-only role in use.
- [ ] Postgres `listen_addresses=localhost` (or Docker bound to `127.0.0.1:5432`);
      `ss -ltnp` shows no `0.0.0.0:5432`.
- [ ] nginx: HTTP→HTTPS redirect, valid Let's Encrypt cert, HSTS + security headers
      present (verify with `curl -I https://cucumber.example.com`).
- [ ] `client_max_body_size` set; gzip on.
- [ ] State-changing endpoints require admin login (see config-review doc): POST
      `/classify`, `/score`, `/research`, `/embed`, `/categories/{id}/approve|reject`.
- [ ] CORS: either same-origin `/api` (no CORS needed) OR strict allowlist with
      `allow_credentials=true` for the exact UI origin.
- [ ] `limit_req` on `/auth/login`; fail2ban enabled.
- [ ] ufw enabled: only 22/80/443 open; 5432/8113/8114 not externally reachable.
- [ ] Nightly `pg_dump` cron installed and a restore tested at least once.
- [ ] App does not run with FastAPI `debug=True`; client errors don't leak stack traces.
- [ ] Logs do not record passwords or full login request bodies.
```
