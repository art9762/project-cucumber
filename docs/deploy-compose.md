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
