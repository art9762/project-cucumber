# Project cucumber — UI

React control panel over the `analysis` FastAPI backend. **Phase 5 scaffold.**

Stack: React 18 + Vite + TypeScript + Tailwind CSS + TanStack Query + Framer
Motion + React Router. Auth is **server sessions via HttpOnly cookie** — the
API client always sends `credentials: 'include'`, so no token is stored.

## Run

```bash
cd ui
npm install
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
  `useHealth`, `useCategories`, `usePendingCategories`, `useTierlist(filters)`,
  `useItemScore(id)`, `useResearchList(filters)`, `useItemResearch(id)`,
  `useCompetitors(id, limit)`. Mutations: `useSearch`, `useRunClassify`,
  `useRunScore`, `useRunResearch`, `useRunEmbed`, `useApproveCategory`,
  `useRejectCategory`. Query keys live in the `queryKeys` object.

### Endpoints mirrored

| Method | Path | Hook | Response type |
| --- | --- | --- | --- |
| GET | `/health` | `useHealth` | `HealthResponse` |
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

## For feature agents

Pages are wired in **`src/App.tsx`** as `PageStub` placeholders under an authed
`<Layout>` shell. Replace the `element` of each route with your real page —
keep the path the same:

| Route | Stub | Suggested hooks |
| --- | --- | --- |
| `/` | Dashboard | `useHealth`, `useTierlist`, `useResearchList` |
| `/tierlist` | Tierlist | `useTierlist`, `TierBadge` |
| `/search` | Search | `useSearch` |
| `/competitors` | Competitors | `useCompetitors`, `useItemResearch` |
| `/control` | Control | `useRunClassify`, `useRunScore`, `useRunResearch`, `useRunEmbed`, `useApproveCategory`, `useRejectCategory` |
| `/settings` | Settings | — |

Reusable primitives in `src/components/`: `Layout`, `Card`, `Button`, `Input`,
`Spinner`, `TierBadge`, `EmptyState`, `ErrorState`.
