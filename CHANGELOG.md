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
