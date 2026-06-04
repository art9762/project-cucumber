# find-engine

Ядро для парсинга публичных источников (GitHub, Reddit, Hacker News, arXiv) и
сбора данных о новых идеях и проектах в сфере ИИ и IT в единую базу PostgreSQL.

Ядро **только собирает** данные. Аналитику и поиск конкурентов выполняет
отдельный софт поверх собранной базы.

## Статус

v1 реализован. Полный дизайн и план:
[`docs/superpowers/specs/2026-06-04-find-engine-design.md`](docs/superpowers/specs/2026-06-04-find-engine-design.md).

## Документация

Полная документация — в [`docs/`](docs/README.md): архитектура, модель данных,
HTTP API, конфигурация, эксплуатация и гайд по добавлению источника.

## Запуск

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env            # заполнить DB_URL, токены
docker-compose up -d            # Postgres
alembic upgrade head            # схема
uvicorn find_engine.main:app    # API на :8000
```

Запустить сбор: `POST /jobs {"source":"arxiv"}` → `GET /jobs/{id}` (статус+stats),
`GET /health` (живость + список источников).

Тесты: `pytest` (нормализация на фикстурах, orchestrator с моком; repository-тесты
требуют поднятого Postgres, иначе пропускаются).

## Кратко

- **Источники v1:** GitHub, Reddit, Hacker News, arXiv (через API/RSS).
- **Стек:** Python + PostgreSQL (pgvector — на будущее).
- **Управление:** HTTP API (FastAPI) — ручной запуск задач + cron-расписание.
- **Данные:** нормализованная таблица `items` для поиска + `raw_records` (JSONB)
  для деталей + `jobs` с per-source watermark для инкрементального добора и дедупа.
- **Расширяемость:** новый источник = новый плагин по интерфейсу `Source`.

## Вне scope v1

- Аналитика, дашборды, поиск конкурентов — отдельный софт.
- HTML-парсинг произвольных форумов — v2.
- Семантический поиск / эмбеддинги — позже (схема к этому готова).
