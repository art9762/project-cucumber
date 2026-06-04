# Kickoff — старт работы над анализом (для новой сессии / swarm)

Точка входа для следующей сессии. Читать в порядке: этот файл →
[`analysis-plan.md`](analysis-plan.md) → [`phase-0-analysis-scaffold.md`](phase-0-analysis-scaffold.md).

## Где мы

- Монорепо **Project cucumber** (приватный `github.com/art9762/project-cucumber`).
- `search engine/` — движок сбора, **v1 готов** (GitHub/Reddit/HN/arXiv →
  Postgres: `items`, `raw_records`, `jobs`). Только собирает данные.
- Строим поверх базы модуль **анализа**. Общий план и решения — в `analysis-plan.md`.

## Что делаем дальше

**Фаза 0 — каркас `analysis/`.** Полная спека: `phase-0-analysis-scaffold.md`.
Коротко: новый сервис-пакет `analysis/` рядом с `search engine/`, тот же стек
(FastAPI + SQLAlchemy async + Alembic), Trinity-клиент, read-only к таблицам
движка, свои таблицы (`analysis_runs`, `categories`, `item_analysis`),
инкрементальный селектор «новых items», `GET /health`. Без логики анализа.

## Ключевые факты для разработчика

- **Trinity** = Anthropic-совместимый шлюз. `ANTHROPIC_BASE_URL=https://gate.trinity.tg/aurora`,
  токен в `ANTHROPIC_AUTH_TOKEN`. Дешёвая модель — `claude-haiku-4-5`, эскалация —
  `claude-sonnet-4-6` / `claude-opus-4-8`. Подробности и список моделей — `Trinity.md`.
- **Секреты только из env** (паттерн движка: `config.py` на pydantic-settings,
  `.env` в gitignore). Реальный токен Trinity НИКОГДА не коммитим.
- **Доступ к данным движка — read-only.** Не писать в `items/raw_records/jobs`,
  не импортировать ORM движка; свой минимальный read-маппинг `items`.
- **Инкрементальность:** «новые items» = нет строки в `item_analysis`
  (LEFT JOIN). UUID id движка не монотонный — не вести курсор по id.
- **Миграции анализа — своя alembic-история**, не пересекать с миграциями движка.
- **TDD**: Trinity мокаем, БД-тесты skip без Postgres (как repository-тесты движка).
- Стиль и инфра-ориентир — как в `search engine/` (см. его `docs/` и `CLAUDE.md`).

## Инфра-контекст (для будущих фаз, не для Фазы 0)

- Деплой: один VPS (Нидерланды), всё под отдельным системным юзером (не root).
- Веб — полная панель управления (Фаза 5), не просто витрина.
- Аккаунты + безопасность + аудит — отдельная финальная Фаза 6 (шаринг друзьям).

## Полная карта фаз

0. Каркас `analysis/` ← **сейчас**
1. Классификация (Haiku → дерево категорий)
2. Скоринг + тирлист (комплексный коэффициент, осн. вес — актуальность)
3. `research/` — веб-серч и поиск конкурентов в вебе
4. Эмбеддинги (pgvector) + analysis API
5. UI / панель управления (ui/ux + motion)
6. Аккаунты, безопасность, аудит
