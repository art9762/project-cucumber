# Релиз v1.0.0 + деплой на VPS через Docker Compose — дизайн

Дата: 2026-06-10. Статус: одобрен пользователем (вариант A: compose + deploy-скрипт,
деплой вручную с локальной машины по SSH).

## Цель

Довести монорепо до публичного релиза v1.0.0 и задеплоить весь стек на один VPS
(Ubuntu, доступ по IP без домена) через Docker Compose с образами из GHCR.

## Контекст и ограничения

- Сервисы: `analysis` (FastAPI, :8113), `search engine` (collector, FastAPI +
  APScheduler, :8114, **строго 1 воркер/реплика**), `ui` (Vite SPA → nginx),
  Postgres `pgvector/pgvector:pg16`.
- CI уже есть (`.github/workflows/ci.yml`); Docker-образы уже публикуются в GHCR
  на push в main и на теги `v*` (`.github/workflows/docker.yml`):
  `ghcr.io/art9762/project-cucumber/{analysis,search-engine,ui}`.
- UI-образ печёт `VITE_API_BASE=/api` по умолчанию (build-arg) — фронтовый прокси
  обязан отдавать UI и `/api/` с одного origin.
- Auth — серверные сессии, HttpOnly-cookie, `cookie_secure: false` по умолчанию
  (`analysis/config.py:67`) — подходит для HTTP-по-IP. CORS не нужен при
  едином origin (`CORS_ORIGINS` оставляем пустым в проде).
- Роли БД: `analysis` (RW к своим таблицам) и `analysis_ro` (read-only к таблицам
  движка) — описаны в `docs/phase-6-deploy-hardening.md:292-302`.
- Домена нет → HTTP по IP, без TLS. Secure-cookie не включаем.
- VPS уже арендован; SSH с этой машины пока не настроен — настраивается
  интерактивно на этапе деплоя (пользователь даёт IP/ключ).

## Объём работ

### 1. Чистка и полировка репо

- Удалить пустой каталог `test ui/`; убрать упоминание из `README.md`.
- Добавить CI-бейджи (workflows CI и Docker) в шапку `README.md`.
- Создать `CHANGELOG.md` (формат Keep a Changelog): одна запись `1.0.0` со
  сводкой фаз 0–6 + ссылка на сравнение тегов.
- Поднять версии до `1.0.0`: `analysis/pyproject.toml`,
  `search engine/pyproject.toml`, `ui/package.json`.

### 2. Деплой-каркас — новая папка `deploy/`

```
deploy/
├── docker-compose.prod.yml   # postgres + analysis + collector + ui + proxy
├── nginx/proxy.conf          # фронт: / → ui, /api/ → analysis:8113
├── .env.example              # все переменные стека (секреты — заполнить)
├── deploy.sh                 # bootstrap VPS + rsync + pull/up + миграции
└── init/01-roles.sh          # создание ролей analysis/analysis_ro при init PG
```

Решения:

- **proxy** (nginx:alpine) — единственный сервис с публичным портом (80).
  Маршруты: `/api/` → `analysis:8113` (strip-prefix `/api`), всё остальное →
  `ui:80`. Лимит запросов на `/api/auth/login` (как в phase-6 runbook).
- **postgres** — named volume, healthcheck, пароли из `deploy/.env`;
  `init/01-roles.sh` монтируется в `/docker-entrypoint-initdb.d/` (официальный
  entrypoint выполняет `.sh` при первой инициализации тома, env доступен) и
  создаёт роли `analysis`/`analysis_ro` с паролями из env; пароли не хардкодим.
- **analysis** — образ из GHCR; env: `DB_URL_ANALYSIS`, `DB_URL_READ`,
  `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, `SESSION_SECRET`,
  `CORS_ORIGINS=` (пусто). Внутренняя сеть, порт не публикуется.
- **collector** — образ из GHCR; env: `DB_URL`, токены источников.
  `deploy: replicas: 1` + комментарий-предупреждение про APScheduler.
- **ui** — образ из GHCR (дефолтный build-arg `/api`), внутренняя сеть.
- **Миграции и сидинг** — не в entrypoint'ах, а явными шагами deploy.sh:
  `docker compose run --rm` для alembic движка, alembic analysis,
  `python -m analysis.auth create-admin` (пароль запрашивается/из env).
- **deploy.sh** — идемпотентный bash; параметры подключения (`VPS_HOST`,
  `VPS_USER`, путь) из `deploy/.env` (локального, не коммитится). Шаги:
  1. ssh: установить Docker + compose plugin, если нет (официальный get.docker.com);
  2. rsync `deploy/` → `/opt/cucumber/deploy/` (без локального `.env` секретов —
     отдельный шаг копирования `.env` с подтверждением);
  3. ssh: `docker compose pull && docker compose up -d`;
  4. однократно (флаг `--init`): миграции + create-admin + роли;
  5. smoke: `curl /api/health` изнутри VPS, вывод статуса стека.

### 3. Release-механика

- Новый workflow `.github/workflows/release.yml`: на тег `v*` → создать GitHub
  Release с `generate_release_notes: true`. Сборку образов не дублирует
  (docker.yml уже триггерится на теги).
- Финальный шаг (после мержа и зелёного CI): `git tag v1.0.0 && git push --tags`,
  проверить Release и образы `:1.0.0` в GHCR.

### 4. Доки

- Новый `docs/deploy-compose.md` — основной runbook деплоя: prerequisites,
  заполнение `deploy/.env`, запуск `deploy.sh`, обновление версии
  (pull нового тега), бэкап тома Postgres, траблшутинг. Ссылается на
  `phase-6-deploy-hardening.md` за углублённым хардненингом (ufw, ssh, fail2ban).
- В начало `phase-6-deploy-hardening.md` — примечание: «актуальный способ
  деплоя — Docker Compose, см. deploy-compose.md; этот док остаётся справочником
  по hardening и systemd-варианту».
- `README.md`: бейджи, секция «Деплой» со ссылкой на новый runbook, ссылка на
  CHANGELOG, убрать `test ui/`.

### 5. Деплой (интерактивная фаза)

1. Пользователь даёт IP/учётку; настраиваем SSH-ключ (`! ssh-copy-id ...` при
   необходимости — интерактивные команды запускает пользователь).
2. Заполняем `deploy/.env` реальными секретами (генерация `openssl rand`).
3. `./deploy.sh --init`, затем smoke-тест: `/api/health`, логин в UI с создан-
   ной админ-учёткой, ручной прогон сбора, тирлист в UI.

## Тестирование

- `docker compose -f deploy/docker-compose.prod.yml config` — валидность.
- Локальный прогон прод-стека: собрать образы локально (`docker compose build`
  c override или `--build`), поднять, smoke: `/api/health` 200, login → 200,
  UI отдаётся, `/api` проксируется. Только после этого — реальный деплой.
- Существующие тесты не трогаем; CI должен остаться зелёным.

## Вне объёма

- TLS/домен (нет домена; добавится отдельно — Caddy или certbot).
- Автодеплой из GitHub Actions (вариант B — возможное продолжение).
- Изменения в коде сервисов (только версии в метаданных).
- Перевод systemd-runbook'а — остаётся как справочник.

## Критерии готовности

1. Репо: нет `test ui/`, есть CHANGELOG, бейджи, версии 1.0.0, release.yml.
2. `deploy/` поднимает весь стек локально, smoke-тесты проходят.
3. Тег `v1.0.0` опубликован: GitHub Release создан, образы `:1.0.0` в GHCR.
4. Стек работает на VPS: UI открывается по `http://<IP>`, логин работает,
   сбор и анализ выполняются.
