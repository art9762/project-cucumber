# Release v1.0.0 + VPS Docker Compose Deploy — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Довести монорепо до публичного релиза v1.0.0 (CHANGELOG, версии, release-workflow, чистка) и подготовить/выполнить деплой всего стека на VPS через Docker Compose с образами из GHCR.

**Architecture:** Новая папка `deploy/` с прод-compose (postgres + analysis + collector + ui + nginx-proxy на :80, единый origin `/api/` → analysis), идемпотентным `deploy.sh` (ssh+rsync) и init-скриптом ролей БД. Релиз — тег `v1.0.0` → существующий docker.yml собирает образы, новый release.yml создаёт GitHub Release.

**Tech Stack:** Docker Compose v2, nginx:1.27-alpine, pgvector/pgvector:pg16, GitHub Actions, bash.

**Спека:** `docs/superpowers/specs/2026-06-10-release-v1-deploy-design.md`

**Ключевые факты о кодовой базе (проверены):**
- Analysis-роуты БЕЗ глобального префикса: `/health`, `/auth/login`, `/categories`, ... (`analysis/analysis/api/routers/*.py`). Прокси должен срезать `/api`.
- UI-образ печёт `VITE_API_BASE=/api` по умолчанию (`ui/Dockerfile`, build-arg).
- Env analysis (`analysis/analysis/config.py`): `DB_URL_ANALYSIS`, `DB_URL_READ`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, `SESSION_SECRET`, `COOKIE_SECURE` (default false — оставляем), `CORS_ORIGINS` (пусто — ок при едином origin).
- Env collector (`search engine/find_engine/config.py`): `DB_URL`, опц. `GITHUB_TOKEN`, `REDDIT_*`, `CRON_*`.
- CLI админа: `python -m analysis.auth create-admin --username X --password Y`.
- Alembic в runtime-зависимостях обоих сервисов; `alembic.ini` и миграции попадают в образы (`COPY . .`); `script_location` относительный → запускать из `/app`.
- GHCR-образы: `ghcr.io/art9762/project-cucumber/{analysis,search-engine,ui}` (docker.yml).
- Git remote: `https://github.com/art9762/project-cucumber`.
- `test ui/` — пустой каталог, в git не отслеживается (только упоминание в README:18-19).

---

### Task 1: Чистка репо — `test ui/`, бейджи, версии

**Files:**
- Delete: `test ui/` (пустой каталог, не в git)
- Modify: `README.md:1`, `README.md:18-19`
- Modify: `analysis/pyproject.toml` (version), `search engine/pyproject.toml` (version), `ui/package.json` (version)

- [ ] **Step 1: Удалить пустой каталог**

```bash
rmdir "/Users/artem/Documents/Project cucumber/test ui"
```

- [ ] **Step 2: README — добавить бейджи после заголовка**

Заменить в `README.md`:

```markdown
# Project cucumber
```

на:

```markdown
# Project cucumber

[![CI](https://github.com/art9762/project-cucumber/actions/workflows/ci.yml/badge.svg)](https://github.com/art9762/project-cucumber/actions/workflows/ci.yml)
[![Docker](https://github.com/art9762/project-cucumber/actions/workflows/docker.yml/badge.svg)](https://github.com/art9762/project-cucumber/actions/workflows/docker.yml)
[![Release](https://img.shields.io/github/v/release/art9762/project-cucumber)](https://github.com/art9762/project-cucumber/releases)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)
```

- [ ] **Step 3: README — убрать абзац про `test ui/`**

Удалить из `README.md` строки:

```markdown
Прежний черновик `test ui/` оставлен пустым задел-каталогом и заменён рабочим
модулем [`ui/`](ui/).
```

- [ ] **Step 4: Поднять версии до 1.0.0**

В `analysis/pyproject.toml` и `search engine/pyproject.toml`: `version = "0.1.0"` → `version = "1.0.0"`.
В `ui/package.json`: `"version": "0.1.0"` → `"version": "1.0.0"`.

- [ ] **Step 5: Проверить, что ничего не сломалось**

```bash
cd "/Users/artem/Documents/Project cucumber/ui" && node -e "JSON.parse(require('fs').readFileSync('package.json'))" && echo OK
cd "/Users/artem/Documents/Project cucumber/analysis" && .venv/bin/python -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"
```

Expected: `OK` и `1.0.0`.

- [ ] **Step 6: Commit**

```bash
cd "/Users/artem/Documents/Project cucumber"
git add README.md analysis/pyproject.toml "search engine/pyproject.toml" ui/package.json
git commit -m "chore: bump versions to 1.0.0, add badges, drop empty test ui dir"
```

---

### Task 2: CHANGELOG.md

**Files:**
- Create: `CHANGELOG.md`

- [ ] **Step 1: Создать `CHANGELOG.md`**

```markdown
# Changelog

Формат — [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
версионирование — [SemVer](https://semver.org/lang/ru/).

## [1.0.0] — 2026-06-10

Первый публичный релиз: полный конвейер «сбор → анализ → панель управления».

### Added

- **search engine (find-engine)** — ядро сбора: GitHub, Reddit, Hacker News,
  arXiv → единый Postgres (pgvector); HTTP API + cron, инкрементальный добор,
  дедупликация.
- **analysis** — FastAPI-сервис анализа поверх собранной базы:
  - классификация по дереву категорий (фаза 1);
  - скоринг и тирлист с конфигурируемой формулой и эскалацией на глубокую
    модель (фаза 2);
  - веб-ресёрч и поиск конкурентов через Trinity web_search (фаза 3);
  - локальные эмбеддинги (fastembed) + семантический поиск по pgvector (фаза 4);
  - аутентификация: серверные сессии, HttpOnly-cookie, RBAC, CORS (фаза 6).
- **ui** — панель управления (React 18 + Vite + TS + Tailwind): дашборд,
  тирлист, умный поиск, поиск конкурентов, управление прогонами, настройки
  (фаза 5).
- **CI/CD** — GitHub Actions: lint + typecheck + tests для трёх сервисов;
  сборка и публикация Docker-образов в GHCR.
- **Деплой** — `deploy/`: Docker Compose прод-стек (Postgres + analysis +
  collector + UI + nginx) и `deploy.sh` для VPS; runbook
  `docs/deploy-compose.md`.

[1.0.0]: https://github.com/art9762/project-cucumber/releases/tag/v1.0.0
```

- [ ] **Step 2: Commit**

```bash
cd "/Users/artem/Documents/Project cucumber"
git add CHANGELOG.md
git commit -m "docs: add CHANGELOG for 1.0.0"
```

---

### Task 3: `deploy/` — compose, nginx, init-роли, .env.example

**Files:**
- Create: `deploy/docker-compose.prod.yml`
- Create: `deploy/nginx/proxy.conf`
- Create: `deploy/init/01-roles.sh`
- Create: `deploy/.env.example`

- [ ] **Step 1: Создать `deploy/docker-compose.prod.yml`**

```yaml
# Прод-стек Project cucumber на одном VPS. Наружу смотрит ТОЛЬКО proxy (:80);
# Postgres и оба приложения живут во внутренней сети compose.
#
# Образы тянутся из GHCR (собираются .github/workflows/docker.yml). Версию
# фиксирует IMAGE_TAG в deploy/.env (например 1.0.0); latest — для отладки.
#
# Запуск/обновление — через ../deploy.sh, runbook: docs/deploy-compose.md.
name: cucumber

services:
  postgres:
    image: pgvector/pgvector:pg16
    restart: unless-stopped
    environment:
      POSTGRES_USER: findengine
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set in deploy/.env}
      POSTGRES_DB: findengine
      # Используются init-скриптом ролей при ПЕРВОЙ инициализации тома.
      ANALYSIS_PASSWORD: ${ANALYSIS_PASSWORD:?set in deploy/.env}
      ANALYSIS_RO_PASSWORD: ${ANALYSIS_RO_PASSWORD:?set in deploy/.env}
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./init/01-roles.sh:/docker-entrypoint-initdb.d/01-roles.sh:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U findengine"]
      interval: 5s
      timeout: 5s
      retries: 10

  analysis:
    image: ghcr.io/art9762/project-cucumber/analysis:${IMAGE_TAG:-latest}
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      DB_URL_ANALYSIS: postgresql+asyncpg://analysis:${ANALYSIS_PASSWORD}@postgres:5432/findengine
      DB_URL_READ: postgresql+asyncpg://analysis_ro:${ANALYSIS_RO_PASSWORD}@postgres:5432/findengine
      ANTHROPIC_AUTH_TOKEN: ${ANTHROPIC_AUTH_TOKEN:?set in deploy/.env}
      ANTHROPIC_BASE_URL: ${ANTHROPIC_BASE_URL:-https://gate.trinity.tg/aurora}
      SESSION_SECRET: ${SESSION_SECRET:?set in deploy/.env}
      # Единый origin за прокси — CORS не нужен. Cookie без Secure: доступ по
      # HTTP/IP (домена и TLS нет); при появлении домена включить
      # COOKIE_SECURE=true и TLS на прокси.
      CORS_ORIGINS: ""

  collector:
    image: ghcr.io/art9762/project-cucumber/search-engine:${IMAGE_TAG:-latest}
    restart: unless-stopped
    # ВАЖНО: внутри процесса живёт APScheduler (find_engine/main.py lifespan) —
    # строго ОДНА реплика и один uvicorn-воркер, иначе источники опрашиваются
    # N раз. CMD образа уже задаёт --workers 1.
    deploy:
      replicas: 1
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      DB_URL: postgresql+asyncpg://findengine:${POSTGRES_PASSWORD}@postgres:5432/findengine
      GITHUB_TOKEN: ${GITHUB_TOKEN:-}
      REDDIT_CLIENT_ID: ${REDDIT_CLIENT_ID:-}
      REDDIT_CLIENT_SECRET: ${REDDIT_CLIENT_SECRET:-}

  ui:
    # Статический бандл за nginx внутри образа; VITE_API_BASE=/api запечён на
    # этапе сборки (ui/Dockerfile) — фронт ходит в /api того же origin.
    image: ghcr.io/art9762/project-cucumber/ui:${IMAGE_TAG:-latest}
    restart: unless-stopped

  proxy:
    image: nginx:1.27-alpine
    restart: unless-stopped
    ports:
      - "80:80"
    volumes:
      - ./nginx/proxy.conf:/etc/nginx/conf.d/default.conf:ro
    depends_on:
      - ui
      - analysis

volumes:
  pgdata:
```

- [ ] **Step 2: Создать `deploy/nginx/proxy.conf`**

```nginx
# Фронтовый прокси прод-стека: единственная публичная точка входа (:80).
#   /api/  → analysis:8113 (префикс /api срезается: роуты сервиса без префикса)
#   /      → ui:80 (статический бандл)
# Rate-limit на логин — защита от перебора паролей (см. phase-6 runbook).

limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;

server {
    listen 80;
    server_name _;

    # Базовые security-заголовки (без HSTS — TLS нет, доступ по IP).
    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options DENY always;
    add_header Referrer-Policy no-referrer always;

    # Логин — отдельный location с жёстким лимитом.
    location = /api/auth/login {
        limit_req zone=login burst=5 nodelay;
        proxy_pass http://analysis:8113/auth/login;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/ {
        # Завершающий слэш в proxy_pass срезает префикс /api/.
        proxy_pass http://analysis:8113/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        proxy_pass http://ui:80;
        proxy_set_header Host $host;
    }
}
```

- [ ] **Step 3: Создать `deploy/init/01-roles.sh`**

```bash
#!/bin/bash
# Выполняется официальным entrypoint'ом Postgres ОДИН раз — при первой
# инициализации тома pgdata (docker-entrypoint-initdb.d). Создаёт роли
# приложения с минимальными правами; пароли приходят из env compose-сервиса
# (deploy/.env), в файле ничего не захардкожено.
#
# Роли (см. docs/phase-6-deploy-hardening.md §3.3):
#   analysis    — RW: свои таблицы анализа + alembic (нужен CREATE на schema)
#   analysis_ro — read-only к таблицам движка (DB_URL_READ)
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE ROLE analysis LOGIN PASSWORD '${ANALYSIS_PASSWORD}';
    GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO analysis;
    GRANT USAGE, CREATE ON SCHEMA public TO analysis;

    CREATE ROLE analysis_ro LOGIN PASSWORD '${ANALYSIS_RO_PASSWORD}';
    GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO analysis_ro;
    GRANT USAGE ON SCHEMA public TO analysis_ro;
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO analysis_ro;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO analysis_ro;
EOSQL
```

```bash
chmod +x "/Users/artem/Documents/Project cucumber/deploy/init/01-roles.sh"
```

- [ ] **Step 4: Создать `deploy/.env.example`**

```bash
# Конфиг прод-стека (deploy/docker-compose.prod.yml) + параметры deploy.sh.
# Скопировать в deploy/.env и заполнить. Реальный .env НИКОГДА не коммитим
# (закрыт корневым .gitignore: .env/.env.*).

# ---- VPS (используется только deploy.sh, не compose) ----
VPS_HOST=
VPS_USER=root

# ---- Версия образов из GHCR (тег docker.yml: 1.0.0 | latest | sha-...) ----
IMAGE_TAG=1.0.0

# ---- Postgres ----
# Генерация: openssl rand -base64 24
POSTGRES_PASSWORD=
ANALYSIS_PASSWORD=
ANALYSIS_RO_PASSWORD=

# ---- Analysis ----
# Trinity (Anthropic-совместимый шлюз) — токен обязателен.
ANTHROPIC_AUTH_TOKEN=
ANTHROPIC_BASE_URL=https://gate.trinity.tg/aurora
# Генерация: openssl rand -base64 32
SESSION_SECRET=

# ---- Collector (опционально: без токенов работают анонимные лимиты) ----
GITHUB_TOKEN=
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
```

- [ ] **Step 5: Проверить валидность compose**

```bash
cd "/Users/artem/Documents/Project cucumber/deploy"
POSTGRES_PASSWORD=x ANALYSIS_PASSWORD=x ANALYSIS_RO_PASSWORD=x \
ANTHROPIC_AUTH_TOKEN=x SESSION_SECRET=x \
docker compose -f docker-compose.prod.yml config --quiet && echo CONFIG-OK
```

Expected: `CONFIG-OK` (warnings про отсутствующие опциональные env — допустимы).

- [ ] **Step 6: Проверить синтаксис init-скрипта**

```bash
bash -n "/Users/artem/Documents/Project cucumber/deploy/init/01-roles.sh" && echo SYNTAX-OK
```

Expected: `SYNTAX-OK`.

- [ ] **Step 7: Commit**

```bash
cd "/Users/artem/Documents/Project cucumber"
git add deploy/docker-compose.prod.yml deploy/nginx/proxy.conf deploy/init/01-roles.sh deploy/.env.example
git commit -m "feat(deploy): production Docker Compose stack (pg + analysis + collector + ui + nginx)"
```

---

### Task 4: `deploy/deploy.sh`

**Files:**
- Create: `deploy/deploy.sh` (chmod +x)

- [ ] **Step 1: Создать `deploy/deploy.sh`**

```bash
#!/usr/bin/env bash
# Деплой стека Project cucumber на VPS по SSH. Идемпотентен: повторный запуск
# просто обновляет файлы и перекатывает контейнеры (pull + up -d).
#
#   ./deploy.sh          — синк файлов, pull образов, up -d, smoke-check
#   ./deploy.sh --init   — то же + миграции БД и создание первого админа
#
# Параметры подключения и секреты — в deploy/.env (см. .env.example).
# Локальный .env по умолчанию НЕ копируется — спросим подтверждение.
set -euo pipefail
cd "$(dirname "$0")"

[[ -f .env ]] || { echo "ERROR: deploy/.env не найден — cp .env.example .env и заполни"; exit 1; }
# shellcheck disable=SC1091
source .env

: "${VPS_HOST:?VPS_HOST не задан в deploy/.env}"
VPS_USER="${VPS_USER:-root}"
REMOTE="${VPS_USER}@${VPS_HOST}"
REMOTE_DIR=/opt/cucumber/deploy
DC="docker compose -f ${REMOTE_DIR}/docker-compose.prod.yml --env-file ${REMOTE_DIR}/.env"

INIT=0
[[ "${1:-}" == "--init" ]] && INIT=1

echo "==> [1/5] Docker на ${REMOTE}"
# get.docker.com идемпотентен не вполне — ставим только если docker отсутствует.
ssh "$REMOTE" 'command -v docker >/dev/null 2>&1 || (curl -fsSL https://get.docker.com | sh)'
ssh "$REMOTE" 'docker compose version >/dev/null'

echo "==> [2/5] Синк deploy-файлов → ${REMOTE_DIR}"
ssh "$REMOTE" "mkdir -p ${REMOTE_DIR}"
rsync -rtv docker-compose.prod.yml nginx init "${REMOTE}:${REMOTE_DIR}/"

if ssh "$REMOTE" "test -f ${REMOTE_DIR}/.env"; then
    echo "    .env уже есть на сервере — не трогаю (перезалить: scp .env ${REMOTE}:${REMOTE_DIR}/)"
else
    read -r -p "    Скопировать локальный deploy/.env (С СЕКРЕТАМИ) на сервер? [y/N] " yn
    [[ "$yn" == y* || "$yn" == Y* ]] || { echo "Без .env стек не стартует. Прервано."; exit 1; }
    scp .env "${REMOTE}:${REMOTE_DIR}/.env"
    ssh "$REMOTE" "chmod 600 ${REMOTE_DIR}/.env"
fi

echo "==> [3/5] Pull образов и запуск"
ssh "$REMOTE" "$DC pull && $DC up -d"

if [[ "$INIT" == 1 ]]; then
    echo "==> [4/5] Инициализация: миграции + первый админ"
    # Схема движка (items, raw_records, jobs) — от имени findengine.
    ssh "$REMOTE" "$DC run --rm collector python -m alembic upgrade head"
    # Схема анализа (0001→0003) — от имени роли analysis.
    ssh "$REMOTE" "$DC run --rm analysis python -m alembic upgrade head"

    read -r -p    "    Логин админа [admin]: " ADMIN_USER
    ADMIN_USER="${ADMIN_USER:-admin}"
    read -r -s -p "    Пароль админа (не отображается): " ADMIN_PASS; echo
    [[ -n "$ADMIN_PASS" ]] || { echo "Пустой пароль. Прервано."; exit 1; }
    # Пароль уходит через stdin → env удалённого шелла, в argv процессов на
    # сервере он попадает только внутри короткоживущего контейнера.
    printf '%s' "$ADMIN_PASS" | ssh "$REMOTE" "read -r AP; $DC run --rm analysis \
        python -m analysis.auth create-admin --username '$ADMIN_USER' --password \"\$AP\""
else
    echo "==> [4/5] --init не задан: миграции/админ пропущены"
fi

echo "==> [5/5] Smoke-check"
ssh "$REMOTE" "curl -fsS http://127.0.0.1/api/health && echo"
ssh "$REMOTE" "$DC ps"
echo "OK: UI — http://${VPS_HOST}/"
```

```bash
chmod +x "/Users/artem/Documents/Project cucumber/deploy/deploy.sh"
```

- [ ] **Step 2: Проверить синтаксис**

```bash
bash -n "/Users/artem/Documents/Project cucumber/deploy/deploy.sh" && echo SYNTAX-OK
```

Expected: `SYNTAX-OK`.

- [ ] **Step 3: Проверить guard на отсутствие .env**

```bash
cd "/Users/artem/Documents/Project cucumber/deploy" && ./deploy.sh; echo "exit=$?"
```

Expected: `ERROR: deploy/.env не найден...` и `exit=1` (файла .env ещё нет).

- [ ] **Step 4: Commit**

```bash
cd "/Users/artem/Documents/Project cucumber"
git add deploy/deploy.sh
git commit -m "feat(deploy): idempotent SSH deploy script (bootstrap, sync, migrate, smoke)"
```

---

### Task 5: Release workflow

**Files:**
- Create: `.github/workflows/release.yml`

- [ ] **Step 1: Создать `.github/workflows/release.yml`**

```yaml
name: Release

# На тег v* — создать GitHub Release с автогенерированными notes.
# Образы НЕ собирает: docker.yml уже триггерится на те же теги.
on:
  push:
    tags: ["v*"]

permissions:
  contents: write

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          generate_release_notes: true
```

- [ ] **Step 2: Commit**

```bash
cd "/Users/artem/Documents/Project cucumber"
git add .github/workflows/release.yml
git commit -m "ci: create GitHub Release on v* tags"
```

---

### Task 6: Доки — runbook deploy-compose.md, примечание в phase-6, README

**Files:**
- Create: `docs/deploy-compose.md`
- Modify: `docs/phase-6-deploy-hardening.md` (примечание после заголовка)
- Modify: `README.md` (секция «Деплой», таблица доков)

- [ ] **Step 1: Создать `docs/deploy-compose.md`**

```markdown
# Деплой на VPS — Docker Compose (актуальный способ)

Весь стек (Postgres + analysis + collector + UI + nginx) поднимается одним
`docker compose` из готовых GHCR-образов. Файлы — в [`deploy/`](../deploy/),
запуск — скриптом [`deploy/deploy.sh`](../deploy/deploy.sh).

Углублённый hardening (ufw, ssh, fail2ban, бэкапы) — в
[`phase-6-deploy-hardening.md`](phase-6-deploy-hardening.md); этот runbook
покрывает только сам деплой.

## Топология

```
Internet ──:80──▶ proxy (nginx) ──┬── /api/ → analysis:8113 (префикс срезается)
                                  └── /     → ui:80 (статика)
внутренняя сеть compose: postgres:5432 ← analysis, collector
наружу опубликован ТОЛЬКО proxy:80
```

Домена/TLS нет — доступ по `http://<IP>`, cookie без Secure-флага
(`COOKIE_SECURE` по умолчанию false). При появлении домена: TLS на proxy
(certbot/Caddy) + `COOKIE_SECURE=true` в env analysis.

## Предусловия

- VPS: Ubuntu 22.04/24.04, SSH-доступ (ключом) под root или sudo-юзером.
- Docker ставится автоматически (`deploy.sh`, шаг 1) — либо поставь заранее.
- Образы в GHCR публичны (или `docker login ghcr.io` на сервере).

## Первый деплой

```bash
cd deploy
cp .env.example .env
# Заполнить: VPS_HOST, IMAGE_TAG (напр. 1.0.0), пароли БД
# (openssl rand -base64 24), ANTHROPIC_AUTH_TOKEN, SESSION_SECRET
# (openssl rand -base64 32); опционально GITHUB_TOKEN/REDDIT_*.

./deploy.sh --init
# --init: схема движка → схема анализа → создание первого админа
# (логин/пароль спросит интерактивно). В конце — smoke: /api/health + ps.
```

Открыть `http://<VPS_HOST>/`, залогиниться созданной учёткой.

## Обновление версии

```bash
# в deploy/.env поменять IMAGE_TAG на новый тег релиза
./deploy.sh        # pull новых образов + up -d, без миграций
./deploy.sh --init # если в релизе были новые миграции (alembic идемпотентен)
```

## Роли БД

При ПЕРВОЙ инициализации тома Postgres скрипт
[`deploy/init/01-roles.sh`](../deploy/init/01-roles.sh) создаёт:

| Роль | Права | Используется |
|------|-------|--------------|
| `findengine` | владелец БД | collector (`DB_URL`), миграции движка |
| `analysis` | CREATE на schema + свои таблицы | analysis (`DB_URL_ANALYSIS`), миграции анализа |
| `analysis_ro` | только SELECT | analysis (`DB_URL_READ`) |

Пароли — из `deploy/.env`. Если том уже существует, скрипт не выполняется —
роли заводить вручную (SQL в `phase-6-deploy-hardening.md` §3.3).

## Бэкап Postgres

```bash
ssh root@<VPS_HOST> 'docker exec cucumber-postgres-1 \
  pg_dump -U findengine findengine' | gzip > backup-$(date +%F).sql.gz
```

Автоматизация по cron — см. `phase-6-deploy-hardening.md` §3.4.

## Траблшутинг

| Симптом | Что смотреть |
|---------|--------------|
| 502 на `/api/` | `docker compose logs analysis` — чаще всего БД не готова или неверный DSN |
| Логин не проходит | rate-limit на `/api/auth/login` (5 r/m) — подождать минуту; логи analysis |
| Сбор не идёт | `docker compose logs collector`; токены источников в `.env`; ровно 1 реплика |
| Образы не тянутся | пакеты GHCR приватные → `docker login ghcr.io` на сервере |

Команды смотреть/перезапускать (на сервере, из `/opt/cucumber/deploy`):

```bash
docker compose -f docker-compose.prod.yml --env-file .env ps
docker compose -f docker-compose.prod.yml --env-file .env logs -f analysis
docker compose -f docker-compose.prod.yml --env-file .env restart proxy
```
```

- [ ] **Step 2: Примечание в начало `docs/phase-6-deploy-hardening.md`**

После строки `# Phase 6 — VPS Deployment & Hardening Runbook` вставить:

```markdown

> **Примечание (2026-06-10):** актуальный способ деплоя — Docker Compose, см.
> [`deploy-compose.md`](deploy-compose.md) и [`deploy/`](../deploy/). Этот
> документ остаётся справочником по hardening (ufw, ssh, fail2ban, бэкапы,
> nginx-заголовки) и по альтернативному systemd-варианту без Docker.
```

- [ ] **Step 3: README — секция «Деплой» и строка в таблице доков**

В `README.md` перед секцией `## Лицензия` добавить:

```markdown
## Деплой

Прод-стек разворачивается на VPS одним скриптом из готовых GHCR-образов:

```bash
cd deploy && cp .env.example .env   # заполнить секреты
./deploy.sh --init                  # bootstrap + миграции + первый админ
```

Runbook: [`docs/deploy-compose.md`](docs/deploy-compose.md). Hardening:
[`docs/phase-6-deploy-hardening.md`](docs/phase-6-deploy-hardening.md).
История версий: [`CHANGELOG.md`](CHANGELOG.md).
```

В таблицу «Документация по фазам» после строки «6 — деплой и хардненинг» добавить:

```markdown
| Деплой (Compose, актуальный) | [`docs/deploy-compose.md`](docs/deploy-compose.md) |
```

- [ ] **Step 4: Commit**

```bash
cd "/Users/artem/Documents/Project cucumber"
git add docs/deploy-compose.md docs/phase-6-deploy-hardening.md README.md
git commit -m "docs: Compose deploy runbook, deploy section in README, note in phase-6 doc"
```

---

### Task 7: Локальный smoke-тест прод-стека

Собираем три образа локально с теми же именами, что в compose (IMAGE_TAG=local),
поднимаем стек с тестовыми секретами, проверяем прокси/健康/логин, сносим.

**Files:** только временный `deploy/.env` (удаляется в конце; в git не попадает — закрыт `.gitignore`).

- [ ] **Step 1: Собрать образы локально**

```bash
cd "/Users/artem/Documents/Project cucumber"
docker build -t ghcr.io/art9762/project-cucumber/analysis:local analysis
docker build -t ghcr.io/art9762/project-cucumber/search-engine:local "search engine"
docker build -t ghcr.io/art9762/project-cucumber/ui:local ui
```

Expected: три успешных билда.

- [ ] **Step 2: Тестовый `deploy/.env`**

```bash
cd "/Users/artem/Documents/Project cucumber/deploy"
cat > .env <<'EOF'
IMAGE_TAG=local
POSTGRES_PASSWORD=test-pg-pass
ANALYSIS_PASSWORD=test-an-pass
ANALYSIS_RO_PASSWORD=test-ro-pass
ANTHROPIC_AUTH_TOKEN=test-not-used-in-smoke
SESSION_SECRET=test-session-secret
EOF
```

- [ ] **Step 3: Поднять стек** (порт 80 может быть занят локально — тогда временно поменять на `8080:80` в compose и проверять через :8080)

```bash
docker compose -f docker-compose.prod.yml --env-file .env up -d
docker compose -f docker-compose.prod.yml --env-file .env ps
```

Expected: 5 сервисов, postgres healthy.

- [ ] **Step 4: Миграции + админ (как сделает deploy.sh --init)**

```bash
docker compose -f docker-compose.prod.yml --env-file .env run --rm collector python -m alembic upgrade head
docker compose -f docker-compose.prod.yml --env-file .env run --rm analysis python -m alembic upgrade head
docker compose -f docker-compose.prod.yml --env-file .env run --rm analysis \
  python -m analysis.auth create-admin --username admin --password smoke-test-pass
```

Expected: миграции применились (движок 0001; анализ 0001→0003), админ создан.

- [ ] **Step 5: Smoke через прокси**

```bash
curl -fsS http://localhost/api/health && echo " HEALTH-OK"
curl -fsS -c /tmp/cj -X POST http://localhost/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"smoke-test-pass"}' && echo " LOGIN-OK"
curl -fsS -b /tmp/cj http://localhost/api/auth/me && echo " ME-OK"
curl -fsS http://localhost/ | grep -qi '<div id="root">' && echo "UI-OK"
```

Expected: `HEALTH-OK`, `LOGIN-OK`, `ME-OK`, `UI-OK` (эндпоинты `/auth/login`, `/auth/me` подтверждены в `analysis/analysis/api/routers/auth.py:28,69`).

- [ ] **Step 6: Снести стек и тестовый .env**

```bash
docker compose -f docker-compose.prod.yml --env-file .env down -v
rm /tmp/cj .env
```

- [ ] **Step 7: Зафиксировать найденные правки**

Если smoke выявил правки compose/nginx — внести их и закоммитить:

```bash
cd "/Users/artem/Documents/Project cucumber"
git add deploy/
git commit -m "fix(deploy): adjustments from local prod-stack smoke test"
```

(Если правок нет — шаг пропустить.)

---

### Task 8: Пуш, тег v1.0.0, проверка релиза

- [ ] **Step 1: Пуш main и зелёный CI**

```bash
cd "/Users/artem/Documents/Project cucumber"
git push origin main
gh run watch --exit-status || gh run list --limit 3
```

Expected: CI и Docker workflows зелёные.

- [ ] **Step 2: Тег и пуш тега**

```bash
git tag -a v1.0.0 -m "Project cucumber 1.0.0 — first public release"
git push origin v1.0.0
```

- [ ] **Step 3: Проверить Release и образы**

```bash
gh release view v1.0.0
gh api "/users/art9762/packages/container/project-cucumber%2Fanalysis/versions" --jq '.[].metadata.container.tags' | head -5
```

Expected: Release создан с notes; среди тегов образов есть `1.0.0`.

---

### Task 9 (интерактивный): Деплой на VPS

Выполняется вместе с пользователем — нужен IP и SSH-доступ.

- [ ] **Step 1: Настроить SSH** — пользователь даёт IP/учётку; при необходимости он запускает `! ssh-copy-id <user>@<ip>` (интерактив). Проверка: `ssh <user>@<ip> echo ok`.
- [ ] **Step 2: Заполнить `deploy/.env`** — реальные `VPS_HOST`, `IMAGE_TAG=1.0.0`, пароли (`openssl rand -base64 24`), `SESSION_SECRET` (`openssl rand -base64 32`), `ANTHROPIC_AUTH_TOKEN` (пользователь даёт), опц. токены источников.
- [ ] **Step 3: `./deploy.sh --init`** — следить за выводом; админ-учётку задаёт пользователь.
- [ ] **Step 4: Приёмка** — открыть `http://<IP>/`: логин, дашборд; запустить сбор/прогон анализа из UI; `/api/health` 200; `docker compose ps` — всё `Up`.
- [ ] **Step 5: Записать результат в память проекта** (deploy состоялся, IP/нюансы — без секретов).

---

## Self-review (выполнен)

- Покрытие спеки: чистка (T1), CHANGELOG (T2), версии (T1), deploy/ (T3-T4), release.yml (T5), доки (T6), локальный smoke (T7), тег (T8), VPS (T9) — всё из спеки покрыто.
- Типы/имена согласованы: `IMAGE_TAG`, имена ролей/env-переменных сверены с `analysis/config.py` и `find_engine/config.py`; пути GHCR — с docker.yml.
- Эндпоинты auth (`/auth/login`, `/auth/logout`, `/auth/me`) сверены с кодом.
