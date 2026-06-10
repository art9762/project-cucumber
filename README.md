# Project cucumber

[![CI](https://github.com/art9762/project-cucumber/actions/workflows/ci.yml/badge.svg)](https://github.com/art9762/project-cucumber/actions/workflows/ci.yml)
[![Docker](https://github.com/art9762/project-cucumber/actions/workflows/docker.yml/badge.svg)](https://github.com/art9762/project-cucumber/actions/workflows/docker.yml)
[![Release](https://img.shields.io/github/v/release/art9762/project-cucumber)](https://github.com/art9762/project-cucumber/releases)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

Платформа для отслеживания новых идей и проектов в сфере ИИ и IT: собирает данные
из публичных источников в единую базу и строит поверх неё анализ, поиск и панель
управления.

Проект состоит из трёх частей с чётким разделением: **сбор** данных, **анализ**
поверх собранной базы и **UI** поверх анализа.

## Структура

| Часть | Что это | Статус |
|-------|---------|--------|
| [`search engine/`](search%20engine/) | Ядро сбора (`find-engine`, v1): парсит GitHub, Reddit, Hacker News, arXiv в единую базу PostgreSQL. HTTP API + cron, инкрементальный добор и дедуп. | v1 реализован |
| [`analysis/`](analysis/) | FastAPI-сервис анализа поверх собранной базы: классификация, скоринг/тирлист, веб-ресёрч, эмбеддинги/семантический поиск, аутентификация. Читает таблицы движка read-only, складывает результаты в свои. | Фазы 0–6 реализованы |
| [`ui/`](ui/) | Панель управления (React 18 + Vite + TS + Tailwind + TanStack Query + Framer Motion) поверх analysis API: дашборд, тирлист, умный поиск, поиск конкурентов, управление прогонами, настройки. Аутентификация через cookie-сессию. | Фаза 5 реализована |

План модуля анализа и разбивка по фазам: [`docs/analysis-plan.md`](docs/analysis-plan.md),
[`docs/KICKOFF.md`](docs/KICKOFF.md).

## Архитектура в двух словах

```
источники (GitHub, Reddit, HN, arXiv)
        │
        ▼
  search engine  ──►  PostgreSQL (pgvector: items + raw_records + jobs)
                            │  read-only к таблицам движка
                            ▼
                        analysis  (классификация, скоринг, ресёрч,
                            │       эмбеддинги, семантический поиск,
                            │       auth/сессии — свои таблицы)
                            │  HTTP API (cookie-сессия)
                            ▼
                          ui  (панель управления, умный поиск)
```

Ядро **только собирает** данные. Анализ, поиск конкурентов, аутентификация и UI
живут отдельно и читают готовую базу — это позволяет развивать сбор и анализ
независимо. Доступ к LLM — через **Trinity** (Anthropic-совместимый шлюз),
секреты только из окружения (`ANTHROPIC_AUTH_TOKEN`) — см. [`docs/Trinity.md`](docs/Trinity.md).

## Quick start — запуск всего стека локально

Нужны Docker (для Postgres c pgvector), Python 3.11+ и Node 18+.

### 1. Postgres (pgvector) — из движка

```bash
cd "search engine"
docker-compose up -d            # поднимает pgvector/pgvector:pg16 на :5432
.venv/bin/python -m alembic upgrade head   # схема движка (items, raw_records, jobs)
```

Подробнее про движок и сбор данных — [`search engine/README.md`](search%20engine/README.md).

### 2. Analysis — миграции, админ, API

```bash
cd analysis
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env            # заполнить ANTHROPIC_AUTH_TOKEN и DSN при необходимости

.venv/bin/python -m alembic upgrade head            # свои таблицы анализа (0001→0003)
.venv/bin/python -m analysis.auth create-admin \
    --username admin --password 'change-me'         # сидинг первого админа

# Запуск API. Порт 8113 — тот же, что в проде за nginx (см. docs/phase-6-deploy-hardening.md).
SESSION_SECRET='change-me' \
CORS_ORIGINS='http://localhost:5173,http://127.0.0.1:5173' \
.venv/bin/uvicorn analysis.main:app --port 8113
```

Полный справочник API, env-переменных и CLI — [`analysis/README.md`](analysis/README.md).

### 3. UI — панель управления

```bash
cd ui
npm install
cp .env.example .env.local      # VITE_API_BASE по умолчанию http://localhost:8113
npm run dev                     # http://localhost:5173
```

Логин — учётка, созданная `create-admin`. Подробнее — [`ui/README.md`](ui/README.md).

## С чего начать

- **Запустить сбор данных** → [`search engine/README.md`](search%20engine/README.md)
- **Понять, как устроено ядро** → [`search engine/docs/`](search%20engine/docs/README.md)
- **Модуль анализа (API, CLI, env)** → [`analysis/README.md`](analysis/README.md)
- **Панель управления** → [`ui/README.md`](ui/README.md)
- **План анализа и фазы** → [`docs/analysis-plan.md`](docs/analysis-plan.md)

## Документация по фазам

| Фаза | Документ |
|------|----------|
| 0 — каркас analysis | [`docs/phase-0-analysis-scaffold.md`](docs/phase-0-analysis-scaffold.md) |
| 1 — классификация | [`docs/phase-1-classification.md`](docs/phase-1-classification.md) |
| 2 — скоринг и тирлист | [`docs/phase-2-scoring.md`](docs/phase-2-scoring.md) |
| 3 — веб-ресёрч | [`docs/phase-3-research.md`](docs/phase-3-research.md) |
| 4 — эмбеддинги + API | [`docs/phase-4-embeddings-api.md`](docs/phase-4-embeddings-api.md) |
| 5 — UI / панель | [`docs/phase-5-ui.md`](docs/phase-5-ui.md) |
| 6 — конфиг-ревью | [`docs/phase-6-config-review.md`](docs/phase-6-config-review.md) |
| 6 — деплой и хардненинг | [`docs/phase-6-deploy-hardening.md`](docs/phase-6-deploy-hardening.md) |
| Trinity (LLM-шлюз) | [`docs/Trinity.md`](docs/Trinity.md) |

## Лицензия

[Apache License 2.0](LICENSE) © 2026 art9762.
