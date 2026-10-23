# Project status and validation

The collection → analysis → UI workflow is implemented. The dashboard now counts
all collected items, including those that have not been scored. This page records
what was checked on 2026-10-23 and what still needs an environment with real
providers and production infrastructure.

## Verified locally

| Area | Result | Boundary |
| --- | --- | --- |
| Analysis API and business logic | 386 pytest cases passed; Ruff and mypy passed | SQLite fixtures and stubbed model/provider clients |
| Collection engine | 64 pytest cases passed; Ruff and mypy passed | Includes three real PostgreSQL 16.15 integration cases, zero skips |
| PostgreSQL integration | Insert/update deduplication, job watermark, schedule create/update/delete passed | Fresh loopback-only database, not the application database |
| Test isolation | A synthetic public-schema sentinel survived integration tests; temporary schemas were removed | Explicit `TEST_DB_URL`; application `DB_URL`/`.env` is never a test fallback |
| UI dependency tree | `npm ci`, production build, `npm audit`, and `npm audit --omit=dev` passed | Zero reported advisories at this check; audit results can change |
| Browser acceptance | Login, dashboard, tierlist navigation, logout, and return-to-requested-page passed | Production preview and real API/session logic over synthetic SQLite data |
| UI runtime baseline | Node 22.23.1, npm 10.9.8; Vite 7.3.7, Router 7.18.4, Tailwind 4.3.3 | React remains 18.3.1; Safari 16.4+, Chrome 111+, Firefox 128+ |

An explicitly configured but unavailable test database causes a test error; it
cannot silently turn a broken integration environment into a successful skip.
Without `TEST_DB_URL`, the three PostgreSQL cases remain opt-in locally. CI
provisions its own PostgreSQL 16 service and sets the variable for the complete
suite. Analysis tests continue to use SQLite and provider stubs.

For the exact local commands, run from each component directory:

```bash
# analysis/
ruff check .
mypy analysis
pytest -q

# search engine/ — use a separate disposable database
ruff check .
mypy find_engine
TEST_DB_URL='postgresql+asyncpg://test_user:test_password@localhost:55432/cucumber_test' pytest -q

# ui/
npm ci
npm run build
npm audit
```

## Remaining acceptance

- The browser smoke verified 1,008 total items, 1,005 researched, 503 with
  competitors, 1,005 in tier S, and three unscored items. It also verified the
  50-row tierlist, logout, and return to the requested page after login. Dark
  theme, navigation, cards, and form controls rendered correctly. Cross-browser
  and mobile layout coverage remains a separate acceptance task.
- Live collection from GitHub, Reddit, Hacker News, and arXiv needs the intended
  runtime and credentials. Tests exercise stored/synthetic responses.
- Real Trinity classification/scoring/research quality, latency, and cost remain
  unmeasured. No paid provider calls were made for this maintenance.
- The PostgreSQL checks cover collection storage. Real pgvector semantic search
  with the downloaded embedding model still needs separate end-to-end acceptance.
- The production Compose/GHCR deployment and migrations were not run; there is no
  deployment or release implied by a merged maintenance change.

## Dependency migration references

The UI uses the [Tailwind 4 Vite plugin](https://tailwindcss.com/docs/installation/using-vite),
loads its existing JavaScript theme explicitly using `@config`, and uses the
renamed small-blur and accessible-outline classes from the
[upgrade guide](https://tailwindcss.com/docs/upgrade-guide).
React Router 7 retains the React 18 declarative router APIs; the minimum runtime
and migration notes are in the [official changelog](https://reactrouter.com/start/start/changelog).
Vite 7.3 receives security fixes under the [Vite support policy](https://vite.dev/releases).
