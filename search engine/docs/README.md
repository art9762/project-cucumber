# Документация find-engine

Ядро парсинга публичных источников (GitHub, Reddit, Hacker News, arXiv) в единую
базу PostgreSQL. Ядро **только собирает** данные; аналитику и поиск конкурентов
выполняет отдельный софт поверх собранной базы.

## Содержание

| Документ | О чём |
|----------|-------|
| [architecture.md](architecture.md) | Слоистая архитектура, поток данных job, абстракция `Source`, инкрементальный сбор и дедуп, жизненный цикл приложения, HTTP-клиент с retry. |
| [data-model.md](data-model.md) | Схема БД (`items`, `raw_records`, `jobs`), pydantic↔ORM, upsert/дедуп по `(source, external_id)`, watermark. |
| [api.md](api.md) | HTTP API: `GET /health`, `POST /jobs`, `GET /jobs/{id}`, состояния job, типичный сценарий, примеры curl. |
| [configuration.md](configuration.md) | Переменные окружения / `.env`, база данных, секреты и rate limits, настройка источников, cron-расписание. |
| [operations.md](operations.md) | Установка, Postgres через docker-compose, миграции Alembic, запуск uvicorn, сбор вручную и по cron, тесты, production-замечания. |
| [adding-a-source.md](adding-a-source.md) | Гайд для разработчика: как добавить новый источник-плагин по контракту `Source`, с полным примером. |

## С чего начать

- **Запустить локально** → [operations.md](operations.md)
- **Понять, как устроено** → [architecture.md](architecture.md) + [data-model.md](data-model.md)
- **Дёргать API** → [api.md](api.md)
- **Добавить источник** → [adding-a-source.md](adding-a-source.md)

Дизайн и план v1: [superpowers/specs/2026-06-04-find-engine-design.md](superpowers/specs/2026-06-04-find-engine-design.md).
