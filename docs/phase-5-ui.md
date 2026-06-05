# Фаза 5 — UI / панель управления

Веб-панель поверх analysis API ([Фаза 4](phase-4-embeddings-api.md)): просмотр
проектов, тирлист, умный (семантический) поиск, поиск конкурентов, **управление**
прогонами анализа (классификация/скоринг/ресёрч/эмбеддинги, модерация категорий)
и настройки. Аутентификация — через cookie-сессию analysis API
([Фаза 6](phase-6-config-review.md)).

Код — в [`../ui/`](../ui/); подробный справочник по `src/api/` (контракт типов,
клиент, хуки) — в [`../ui/README.md`](../ui/README.md).

## Что делает Фаза 5

- Фронтенд-приложение (SPA) поверх analysis API, без собственного бэкенда.
- Полное покрытие read-эндпоинтов хуками TanStack Query и POST-прогонов —
  мутациями.
- Гейтинг по cookie-сессии: неаутентифицированного пользователя редиректит на
  `/login`; admin-only действия видны/доступны только админам.
- Статическая сборка (`ui/dist`), которую в проде раздаёт nginx тем же origin,
  что и API (см. [`phase-6-deploy-hardening.md`](phase-6-deploy-hardening.md) §4).

## Стек

React 18 + Vite 5 + TypeScript 5 + Tailwind CSS 3 + TanStack Query 5 + Framer
Motion 11 + React Router 6. Скрипты (`ui/package.json`): `dev` (Vite dev-server),
`build` (`tsc --noEmit` затем `vite build`), `preview`, `lint` (`tsc --noEmit`).

## Маршруты и страницы

Маршрутизация — в `ui/src/App.tsx`. Публичен только `/login`; все остальные
маршруты обёрнуты в `<RequireAuth><Layout/></RequireAuth>`.

| Маршрут | Страница (`ui/src/pages/`) | Хуки / эндпоинты | Назначение |
|---------|----------------------------|------------------|------------|
| `/login` | `LoginPage` | `useAuth().login` → `POST /auth/login` | форма входа (username/password) |
| `/` | `DashboardPage` | `useHealth`, `useTierlist({limit})`, `useResearchList({limit})` | сводка: здоровье сервиса, счётчики по тирам, статистика ресёрча |
| `/tierlist` | `TierlistPage` | `useTierlist({tier, category_id, limit})`, `useCategories` | тирлист с фильтрами по тиру/категории |
| `/search` | `SearchPage` | `useSearch` → `POST /search` | семантический поиск по тексту |
| `/competitors` | `CompetitorsPage` | `useCompetitors(id, limit)`, `useItemResearch(id)` | соседи по вектору + веб-ресёрч выбранного item |
| `/control` | `ControlPage` | `useRunClassify`, `useRunScore`, `useRunResearch`, `useRunEmbed`, `usePendingCategories`, `useApproveCategory`, `useRejectCategory` | запуск прогонов и модерация категорий (admin-only) |
| `/settings` | `SettingsPage` | `useHealth`, `useAuth` (logout), `API_BASE` | текущий пользователь, базовый URL API, выход |

Переиспользуемые примитивы — в `ui/src/components/` (`Layout`, `Card`, `Button`,
`Input`, `Spinner`, `TierBadge`, `EmptyState`, `ErrorState`, а также прикладные
`CategoryTree`, `ItemPicker`, `ScoreBreakdown`, `SearchResultCard`,
`SignalMeter`, `StageRunnerCard`, `TierlistRow`, `VectorCompetitorCard`).

## Интеграция с аутентификацией

- Модель — серверные сессии: opaque-токен в HttpOnly-cookie `cucumber_session`
  (НЕ JWT). Клиент токен не хранит и не читает.
- API-клиент (`ui/src/api/client.ts`) всегда шлёт `credentials: 'include'`,
  поэтому cookie ездит с каждым запросом. HTTP 401 распознаётся через
  `isUnauthorized(err)`.
- `ui/src/auth/AuthContext.tsx`: `useAuth()` → `{ user, isLoading, login,
  logout, refetch }`; на маунте дёргает `GET /auth/me`. `<RequireAuth>` гейтит
  маршруты и редиректит на `/login`.
- admin-only действия на `/control` опираются на роль (`useAuth().user.role`) и
  на серверный `require_role("admin")` — UI скрывает кнопки, API отдаёт 403.

## Конфигурация

`VITE_API_BASE` (`ui/.env.example`, по умолчанию `http://localhost:8113`) —
базовый URL analysis API; клиент префиксует им каждый запрос. Прокси `/api` нет.
Для локальной разработки бэкенд должен разрешить origin UI через CORS с
`allow_credentials=true` — задать `CORS_ORIGINS` в `analysis/.env` (напр.
`http://localhost:5173`). В проде UI и API на одном origin за nginx — CORS не
нужен, `VITE_API_BASE` указывает на same-origin `/api`.

## Запуск / сборка / деплой

```bash
cd ui
npm install
cp .env.example .env.local      # при необходимости поправить VITE_API_BASE
npm run dev                     # dev-server на http://localhost:5173

npm run build                   # статическая сборка в ui/dist
npm run preview                 # локальный предпросмотр прод-сборки
```

В проде `ui/dist` раздаётся nginx (`root .../ui/dist`, SPA-фолбэк на
`index.html`), API проксируется на `127.0.0.1:8113` под `/api/` — конфиг nginx и
хардненинг описаны в [`phase-6-deploy-hardening.md`](phase-6-deploy-hardening.md)
§4.

## Известное ограничение

Счётчики по тирам на дашборде (`DashboardPage`) считаются **на клиенте** из
`useTierlist({ limit: 1000 })` — отдельного агрегирующего эндпоинта нет. При
объёме базы свыше ~1000 заскоренных items счётчики станут неполными; в этом
случае нужен серверный агрегат (напр. `GET /tierlist/counts`).
