# Project cucumber — UI

React control panel over the `analysis` FastAPI backend. Phase 5 is implemented;
current acceptance coverage and remaining checks are in [VALIDATION.md](../docs/VALIDATION.md).
See [`../docs/phase-5-ui.md`](../docs/phase-5-ui.md) for the page-by-page
breakdown and deploy notes.

Stack: React 18 + Vite + TypeScript + Tailwind CSS + TanStack Query + Framer
Motion + React Router. Auth is **server sessions via HttpOnly cookie** — the
API client always sends `credentials: 'include'`, so no token is stored.

## Run

Use Node 22.12+ (Node 22 is used in CI and the build container). The package
engine range also permits Node 20.19+. Tailwind 4 targets Safari 16.4+, Chrome
111+, and Firefox 128+.

```bash
cd ui
npm ci
cp .env.example .env.local   # adjust VITE_API_BASE if needed
npm run dev                  # http://localhost:5173
```

Scripts: `dev`, `build` (`tsc --noEmit` then `vite build`), `preview`,
`lint` (`tsc --noEmit`).

## API base URL

There is no `/api` proxy. The client prefixes every request with
`VITE_API_BASE` (default `http://localhost:8113`, the analysis API). Set it in
`.env.local`. Because auth uses cookies, the backend must allow this origin via
CORS with `allow_credentials=true`.

## The frozen contract — `src/api/`

- **`types.ts`** — TypeScript interfaces mirroring every backend pydantic
  schema (field names + nullability copied from the Python source). This is the
  single source of truth; import from here, do not redefine shapes.
- **`client.ts`** — `apiFetch<T>` + `get`/`post`. Throws typed `ApiError`
  ({ status, message, body }); `isUnauthorized(err)` detects HTTP 401.
- **`hooks.ts`** — TanStack Query hooks for every endpoint. Reads:
  `useHealth`, `useDashboardStats`, `useCategories`, `usePendingCategories`,
  `useTierlist(filters)`,
  `useItemScore(id)`, `useResearchList(filters)`, `useItemResearch(id)`,
  `useCompetitors(id, limit)`. Mutations: `useSearch`, `useRunClassify`,
  `useRunScore`, `useRunResearch`, `useRunEmbed`, `useApproveCategory`,
  `useRejectCategory`. Query keys live in the `queryKeys` object.

### Endpoints mirrored

| Method | Path | Hook | Response type |
| --- | --- | --- | --- |
| GET | `/health` | `useHealth` | `HealthResponse` |
| GET | `/dashboard/stats` | `useDashboardStats` | `DashboardStatsOut` |
| GET | `/categories` | `useCategories` | `CategoryTreeNode[]` |
| GET | `/categories/pending` | `usePendingCategories` | `CategoryOut[]` |
| POST | `/categories/{id}/approve` | `useApproveCategory` | `ApproveResponse` |
| POST | `/categories/{id}/reject` | `useRejectCategory` | `RejectResponse` |
| POST | `/classify?limit=` | `useRunClassify` | `ClassifyRunOut` |
| GET | `/tierlist?tier=&category_id=&limit=` | `useTierlist` | `TierItemOut[]` |
| GET | `/items/{id}/score` | `useItemScore` | `ItemScoreOut` |
| POST | `/score?limit=` | `useRunScore` | `ScoreRunOut` |
| GET | `/research?has_competitors=&limit=` | `useResearchList` | `ItemResearchOut[]` |
| GET | `/items/{id}/research` | `useItemResearch` | `ItemResearchOut` |
| POST | `/research?limit=&min_tier=&min_coefficient=` | `useRunResearch` | `ResearchRunOut` |
| POST | `/search` (body `{query, limit}`) | `useSearch` | `SearchHitOut[]` |
| GET | `/items/{id}/competitors?limit=` | `useCompetitors` | `SearchHitOut[]` |
| POST | `/embed?limit=` | `useRunEmbed` | `EmbedRunOut` |
| POST | `/auth/login` (body `{username, password}`) | `useAuth().login` | `AuthUser` |
| POST | `/auth/logout` | `useAuth().logout` | 204 |
| GET | `/auth/me` | `AuthProvider` on mount | `AuthUser` / 401 |

> Note: `/items/{id}/competitors` returns `SearchHitOut[]`, NOT `CompetitorOut`.
> `CompetitorOut` only appears nested inside `ItemResearchOut.competitors`.

## Auth — `src/auth/AuthContext.tsx`

`useAuth()` → `{ user, isLoading, login, logout, refetch }`. `<RequireAuth>`
gates routes and redirects to `/login`. User shape: `{ username, role }`.

## Pages — `src/pages/`

Routes are wired in **`src/App.tsx`**. Only `/login` is public; every other route
is wrapped in `<RequireAuth><Layout/></RequireAuth>`.

| Route | Page | Hooks used |
| --- | --- | --- |
| `/login` | `LoginPage` | `useAuth().login` |
| `/` | `DashboardPage` | `useHealth`, `useDashboardStats` |
| `/tierlist` | `TierlistPage` | `useTierlist({tier, category_id, limit})`, `useCategories` |
| `/search` | `SearchPage` | `useSearch` |
| `/competitors` | `CompetitorsPage` | `useCompetitors`, `useItemResearch` |
| `/control` | `ControlPage` | `useRunClassify`, `useRunScore`, `useRunResearch`, `useRunEmbed`, `usePendingCategories`, `useApproveCategory`, `useRejectCategory` |
| `/settings` | `SettingsPage` | `useHealth`, `useAuth` (logout), `API_BASE` |

Dashboard counters come from `GET /dashboard/stats`, which aggregates the entire
corpus in SQL. Total items includes collected items with no analysis result, and
unscored items includes classified items without a coefficient. Counters refresh
every 30 seconds and after scoring, research, or a completed collection job.

Reusable primitives in `src/components/`: `Layout`, `Card`, `Button`, `Input`,
`Spinner`, `TierBadge`, `EmptyState`, `ErrorState`, plus feature components
`CategoryTree`, `ItemPicker`, `ScoreBreakdown`, `SearchResultCard`,
`SignalMeter`, `StageRunnerCard`, `TierlistRow`, `VectorCompetitorCard`.


## Dependency maintenance

The UI uses Vite 7.3, React Router 7, and Tailwind 4's Vite plugin. React remains
on 18.3. Tailwind explicitly loads `tailwind.config.js` through `@config`, so the
CSS-variable color palette and custom radii/font stay in one place. The small
backdrop blur and accessible outline utilities use their Tailwind 4 names.
PostCSS/autoprefixer are no longer separate build plugins.

After updating dependencies, run `npm ci`, `npm run build`, and `npm audit`.
CI runs the same build and audits both production and development dependencies.
The router upgrade also needs a login/navigation/logout smoke, and styling
changes need a browser check; a successful typecheck alone does not prove them.
