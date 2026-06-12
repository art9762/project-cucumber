# План: управление сбором (collection) из UI

Дата: 2026-06-12. Цель: вывести сбор данных в панель управления — (a) ручной
запуск сбора по источнику, (b) редактирование cron-расписания по источнику, с
персистентностью в БД. Отдельная страница **Collect** в боковом меню.

## Архитектурное решение (важно)

Collector API **не аутентифицирован** и сейчас не выведен наружу (только во
внутренней docker-сети). Выставлять его напрямую через nginx нельзя — nginx не
проверяет сессионную куку, и сбор/расписание стали бы доступны любому из
интернета.

**Шлюз = analysis.** У analysis уже есть сессии + RBAC (`require_role("admin")`).
Добавляем в analysis новый роутер `collect`, который проксирует запросы в
collector по внутренней сети (`http://collector:8114`, httpx уже в зависимостях).
nginx и docker-compose **не меняются** — всё идёт через существующий
`/api/ → analysis`. Collector остаётся без публичного доступа.

Решения пользователя: персистентность cron — **через БД** (миграция движка);
размещение UI — **отдельная страница Collect**.

---

## Backend — collector (search engine/find_engine/)

1. **Миграция `0002_source_schedules.py`** (`storage/migrations/versions/`):
   таблица `source_schedules` (`source` PK text, `cron` text not null,
   `updated_at` timestamptz). Создаётся от роли `findengine` (владелец БД).

2. **ORM** (`storage/orm.py`): `SourceScheduleORM` (__tablename__
   `source_schedules`).

3. **Repository** (`storage/repository.py`): `get_schedules() -> dict[str,str]`,
   `upsert_schedule(source, cron)`, `delete_schedule(source)`.

4. **Scheduler** (`core/scheduler.py`): добавить методы
   - `reschedule(source, cron)` — `add_job`/`reschedule_job` с
     `CronTrigger.from_crontab`; пустой cron → `remove_job` (снять расписание);
   - `current_schedules() -> dict[str,str]` — отдать активные cron из
     APScheduler;
   - `start()` доработать: после env-дефолтов накатывать сохранённые в БД
     расписания (БД приоритетнее env) — читается через repository при старте
     (lifespan).

5. **Роутер** (`api/routers/schedule.py`, монтируется в `main.py`):
   - `GET /schedule` → `{source: cron}` для всех источников (активные + пустые);
   - `PUT /schedule/{source}` body `{cron: str|""}` → валидирует cron
     (`CronTrigger.from_crontab` в try/except → 400), пишет в БД через
     repository, зовёт `scheduler.reschedule`. Валидные источники —
     `available_sources()`, иначе 404.
   - Эндпоинты **без своей auth** (collector внутренний; защищает analysis-шлюз).

6. **POST /jobs** уже готов — менять не нужно.

## Backend — analysis (analysis/analysis/) — шлюз

7. **config.py**: добавить `collector_base_url: str = "http://collector:8114"`.

8. **Роутер `api/routers/collect.py`** (монтируется в `main.py`), все эндпоинты
   под `Depends(require_role("admin"))`, проксируют через httpx
   (`AsyncClient`, таймаут из настроек):
   - `GET  /collect/sources`          → collector `GET /health` (`.sources`);
   - `POST /collect/jobs` `{source}`  → collector `POST /jobs`;
   - `GET  /collect/jobs/{id}`        → collector `GET /jobs/{id}`;
   - `GET  /collect/schedule`         → collector `GET /schedule`;
   - `PUT  /collect/schedule/{src}`   → collector `PUT /schedule/{src}`.
   Прозрачно пробрасывать статус/тело; на ошибки сети collector → 502 с
   понятным detail.

9. **Схемы** (`api/collect_schemas.py`): pydantic-зеркала ответов collector
   (`CollectJobOut`, `ScheduleOut`, `SourcesOut`).

## UI (ui/src/)

10. **api/types.ts**: `CollectJobOut`, `CollectorSourcesOut`, `ScheduleOut`,
    `ScheduleUpdateRequest`.

11. **api/hooks.ts** + `queryKeys`:
    - `useCollectorSources()` (query);
    - `useRunCollect()` (mutation → POST /collect/jobs);
    - `useCollectJob(jobId)` (query с `refetchInterval` пока job не
      success/failed — поллинг прогресса);
    - `useCollectorSchedule()` (query), `useUpdateSchedule()` (mutation,
      инвалидирует schedule).

12. **pages/CollectPage.tsx** (новая):
    - **Manual run**: на каждый источник карточка на базе `StageRunnerCard`
      (или его обёртки) с кнопкой Run; после запуска — поллинг статуса job и
      показ stats (fetched/inserted/updated/skipped). Источники из
      `useCollectorSources`.
    - **Collection schedule**: список источников с инпутом cron-строки
      (placeholder-примеры, напр. `0 6 * * *`), кнопка Save → `useUpdateSchedule`;
      пустая строка = снять расписание. Подсказка про формат cron (UTC).
    - Admin-gate как в ControlPage (`isAdmin`); viewer видит, но действия
      заблокированы.

13. **App.tsx**: маршрут `/collect` → `CollectPage`.

14. **components/Layout.tsx**: пункт NAV `{ to: "/collect", label: "Collect" }`
    (между Competitors и Control).

## Тесты

15. **collector**: тест на `GET/PUT /schedule` (валидный/битый cron → 400,
    неизвестный источник → 404, персист в БД), тест repository-методов,
    тест что `start()` накатывает расписания из БД поверх env.
16. **analysis**: тест роутера `collect` — admin-guard (403 для viewer/гостя),
    проксирование (мок httpx-ответа collector), 502 на сетевую ошибку.
17. **UI**: проектом не предусмотрен тест-раннер (build = tsc + vite) —
    проверяем `npm run build` зелёным.

## Деплой (после ревью кода)

18. Патч-релиз **v1.0.2**: коммиты → тег `v1.0.2` → CI собирает образы
    analysis/search-engine/ui → на сервере `IMAGE_TAG=1.0.2` + `./deploy.sh`.
    Миграция движка (`0002`) накатывается через
    `collector ... alembic upgrade head` (как при первичном `--init`).
    docker-compose/nginx без изменений.

## Критерий готовности

Из UI (страница Collect, под admin): кнопка Run по источнику запускает сбор и
показывает результат (fetched/inserted); редактирование cron сохраняется,
переживает рестарт контейнера и реально меняет расписание APScheduler.
Collector наружу по-прежнему недоступен; все collect-эндпоинты требуют
admin-сессию. pytest (collector + analysis) и `npm run build` зелёные.

## Порядок реализации (через ruflo-агентов)

1. collector: миграция + ORM + repository + scheduler-методы + роутер schedule + тесты;
2. analysis: config + collect-роутер (proxy) + схемы + тесты;
3. UI: types + hooks + CollectPage + route + nav + build;
4. ревью (ruflo reviewer), фиксы;
5. релиз v1.0.2 и накат на сервер.
