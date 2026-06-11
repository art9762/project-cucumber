# Handoff: деплой Project cucumber на VPS (для ИИ-агента)

Инструкция для агента, который будет выполнять последний шаг релиза v1.0.0 —
деплой стека на VPS. Всё остальное уже сделано и проверено; твоя задача —
только Task 9. Работай вместе с пользователем: у него IP, SSH-доступ и секреты.

## Текущее состояние (на 2026-06-11)

- Репо: `/Users/artem/Documents/Project cucumber`, remote
  `https://github.com/art9762/project-cucumber`, ветка `main`, всё запушено.
- Релиз **v1.0.0** опубликован: GitHub Release создан, GHCR-образы
  `ghcr.io/art9762/project-cucumber/{analysis,search-engine,ui}` с тегом
  `1.0.0` существуют и публичны (проверено `docker manifest inspect` без логина).
- `deploy/` готов и **прогнан локально end-to-end** (полный smoke: миграции,
  админ, health/login/me/UI/categories/tierlist через nginx-прокси). Известные
  баги первичной инициализации уже исправлены — НЕ переделывай
  `deploy/init/01-roles.sh`, он рабочий.
- Подробный runbook: [`deploy-compose.md`](deploy-compose.md). Этот документ —
  его агентская версия с нюансами, которые в runbook не попали.

## Что нужно получить от пользователя ДО старта

1. **IP VPS** (Ubuntu 22.04/24.04, ≥2 ГБ RAM) и имя пользователя (обычно `root`).
2. **SSH-доступ по ключу.** Проверка: `ssh <user>@<ip> echo ok`. Если ключа на
   сервере нет — пользователь сам выполняет интерактивную команду через `!`:
   `! ssh-copy-id <user>@<ip>`.
3. **`ANTHROPIC_AUTH_TOKEN`** — токен Trinity-шлюза (Anthropic-совместимый,
   base URL `https://gate.trinity.tg/aurora` уже дефолт). Без него analysis
   стартует, но классификация/скоринг/ресёрч работать не будут.
4. Опционально: `GITHUB_TOKEN`, `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` —
   без них коллектор работает на анонимных лимитах (медленнее, но работает).

## Шаги

### 1. Заполнить `deploy/.env`

```bash
cd "/Users/artem/Documents/Project cucumber/deploy"
cp .env.example .env
```

Заполнить в `.env`:
- `VPS_HOST=<ip>`, `VPS_USER=<user>`
- `IMAGE_TAG=1.0.0`
- Три пароля БД — сгенерировать: `openssl rand -base64 24` (для каждого свой)
- `SESSION_SECRET` — `openssl rand -base64 32`
- `ANTHROPIC_AUTH_TOKEN` — от пользователя
- Опциональные токены коллектора, если пользователь дал

`.env` закрыт `.gitignore` — он не попадёт в git. Не выводи его содержимое в
ответах целиком (там секреты).

### 2. Запустить деплой

```bash
cd "/Users/artem/Documents/Project cucumber/deploy"
./deploy.sh --init
```

**ВАЖНО: скрипт интерактивный.** Он спросит:
1. Подтверждение копирования `.env` на сервер (`y`) — только при первом деплое;
2. Логин админа (default `admin`; допустимы только `[A-Za-z0-9_.-]+`);
3. Пароль админа (скрытый ввод, пустой нельзя).

Поэтому запускай его так, чтобы пользователь мог отвечать: предложи ему
выполнить `! cd deploy && ./deploy.sh --init` самому, либо запускай через
терминал с интерактивом. Не пытайся пайпить ответы автоматически — пароль
админа должен задать пользователь.

Что делает скрипт (идемпотентен, повторный запуск безопасен):
1. Ставит Docker, если его нет (`get.docker.com`);
2. rsync `docker-compose.prod.yml`, `nginx/`, `init/` → `/opt/cucumber/deploy`
   (с `--delete --exclude='.env'` — серверный `.env` не трогается);
3. `docker compose pull && up -d` (5 сервисов: postgres, analysis, collector, ui, proxy);
4. `--init`: миграции движка (контейнер collector) → миграции анализа
   (контейнер analysis) → создание админа;
5. Smoke: `curl http://127.0.0.1/api/health` + `docker compose ps`.

### 3. Приёмка

```bash
curl -fsS http://<ip>/api/health        # {"status":"ok","database":true,...}
```

Затем пользователь в браузере: `http://<ip>/` → логин админом → дашборд.
Из UI: запустить сбор (страница прогонов) и затем прогон анализа. Убедиться,
что в тирлисте появляются элементы.

Проверка, что коллектор реально собирает (на сервере):

```bash
ssh <user>@<ip> "cd /opt/cucumber/deploy && docker compose -f docker-compose.prod.yml --env-file .env logs --tail 30 collector"
```

### 4. Записать результат в память проекта

Создай memory-файл (тип `project`) в
`/Users/artem/.claude/projects/-Users-artem-Documents-Project-cucumber/memory/`:
деплой состоялся, IP (если пользователь не против), дата, нюансы. Секреты и
пароли в память НЕ писать. Обнови `MEMORY.md` (заменив строку про «осталось
Task 9») и пометь шаг 5 в Task 9 плана
`docs/superpowers/plans/2026-06-10-release-v1-deploy.md`.

## Известные нюансы и траблшутинг

- **Роли БД создаются ТОЛЬКО при первой инициализации тома** `pgdata`
  (`docker-entrypoint-initdb.d`). Если стек поднимали с другими паролями и том
  уже существует — либо `docker compose down -v` (снесёт данные!), либо завести
  роли вручную (SQL в `phase-6-deploy-hardening.md` §3.3 + добавить
  `CREATE EXTENSION IF NOT EXISTS vector;` и
  `ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, REFERENCES ON TABLES TO analysis;`
  от имени `findengine`).
- **Порядок миграций имеет значение**: сначала движок (collector), потом
  анализ — миграции анализа ссылаются FK на `items`.
- **502 на `/api/`** — смотри `logs analysis`: чаще всего БД не готова или
  неверный DSN.
- **Логин не проходит / 429** — на `/api/auth/login` rate-limit 5 запросов/мин
  с IP; подождать минуту.
- **Образы не тянутся** — на момент handoff пакеты GHCR публичны; если стали
  приватными — `docker login ghcr.io` на сервере.
- **Коллектор — строго одна реплика** (внутри APScheduler); compose уже так
  настроен, не масштабируй.
- **HTTP без TLS — осознанно** (доступ по IP, `COOKIE_SECURE=false`). Если у
  пользователя появится домен: TLS на proxy (certbot/Caddy) +
  `COOKIE_SECURE=true` в env analysis. Предложи, но не делай без запроса.
- Файрвол/ssh-hardening (ufw, fail2ban) — отдельная задача, runbook
  `phase-6-deploy-hardening.md`. Предложи пользователю после успешного деплоя.

## Критерий готовности

Деплой считается завершённым, когда: `/api/health` отдаёт 200 с
`"database":true`; пользователь залогинился в UI; запущенный из UI сбор
добавляет элементы; прогон анализа их классифицирует/скорит; всё это — на
`http://<ip>/` с VPS, не локально.
