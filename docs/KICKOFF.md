# Kickoff — старт работы над Project cucumber

Точка входа для новой сессии. Читать в порядке: этот файл → корневой
[`README.md`](../README.md) → README нужного модуля:
[`search engine/`](../search%20engine/README.md), [`analysis/`](../analysis/README.md),
[`ui/`](../ui/README.md). Исторический план фаз сохранён в
[`analysis-plan.md`](analysis-plan.md); phase-документы в `docs/` — спеки и
записи решений по уже реализованным этапам.

## Где мы

- Монорепо **Project cucumber** (приватный `github.com/art9762/project-cucumber`).
- `search engine/` — движок сбора, **v1 готов** (GitHub/Reddit/HN/arXiv →
  Postgres: `items`, `raw_records`, `jobs`). Только собирает данные.
- `analysis/` — FastAPI-сервис анализа поверх общей Postgres. Реализованы фазы
  0–6: классификация, скоринг/тирлист, веб-ресёрч, эмбеддинги/семантический
  поиск, auth/RBAC и CORS для cookie-сессий.
- `ui/` — React/Vite-панель управления поверх analysis API. Реализованы login,
  dashboard, tierlist, smart search, competitors, control и settings.

## Что делаем дальше

Следующий практический фокус зависит от задачи, но общий порядок такой:

1. Для продуктовых/API/UI-правок сначала свериться с контрактами в
   [`analysis/README.md`](../analysis/README.md) и [`ui/README.md`](../ui/README.md).
2. Для деплоя и шаринга друзьям идти по
   [`phase-6-deploy-hardening.md`](phase-6-deploy-hardening.md) и
   [`phase-6-config-review.md`](phase-6-config-review.md).
3. Для новых источников данных работать через контракт `Source` в
   `search engine/` и гайд [`adding-a-source.md`](../search%20engine/docs/adding-a-source.md).

## Ключевые факты для разработчика

- **Trinity** = Anthropic-совместимый шлюз. `ANTHROPIC_BASE_URL=https://gate.trinity.tg/aurora`,
  токен в `ANTHROPIC_AUTH_TOKEN`. Дешёвая модель — `claude-haiku-4-5`, эскалация —
  `claude-sonnet-4-6` / `claude-opus-4-8`. Подробности и список моделей — `Trinity.md`.
- **Секреты только из env** (паттерн движка: `config.py` на pydantic-settings,
  `.env` в gitignore). Реальный токен Trinity НИКОГДА не коммитим.
- **Доступ к данным движка — read-only.** Не писать в `items/raw_records/jobs`,
  не импортировать ORM движка; свой минимальный read-маппинг `items`.
- **Инкрементальность:** «новые items» = нет строки в `item_analysis`
  / `item_research` / `item_embeddings` в зависимости от прогона (LEFT JOIN).
  UUID id движка не монотонный — не вести курсор по id.
- **Миграции анализа — своя alembic-история**, не пересекать с миграциями движка.
- **Auth:** серверные opaque-сессии в БД, HttpOnly-cookie `cucumber_session`, роли
  `viewer`/`admin`. Read-эндпоинты analysis требуют `viewer+`, state-changing
  прогоны и модерация категорий требуют `admin`; `/health`, `/auth/login`,
  `/auth/logout` публичные, `/auth/me` требует валидную сессию.
- **UI:** токен не хранится в браузере; клиент всегда делает запросы с
  `credentials: 'include'`.
- **Тесты:** Trinity мокаем; unit-тесты analysis не требуют сети и Postgres,
  Postgres нужен для миграций и боевого запуска.
- **Деплой:** один VPS, процессы под отдельным системным юзером `cucumber`,
  nginx + TLS спереди, analysis на `127.0.0.1:8113`, collector на
  `127.0.0.1:8114` ровно в один worker, Postgres только loopback.

## Полная карта фаз

Все фазы из исходного плана реализованы:

0. Каркас `analysis/`
1. Классификация (Haiku → дерево категорий)
2. Скоринг + тирлист (комплексный коэффициент, осн. вес — актуальность)
3. `research/` — веб-серч и поиск конкурентов в вебе
4. Эмбеддинги (pgvector) + analysis API
5. UI / панель управления
6. Аккаунты, безопасность, аудит, deploy hardening
