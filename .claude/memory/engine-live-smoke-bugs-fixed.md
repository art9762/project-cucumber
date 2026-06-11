---
name: engine-live-smoke-bugs-fixed
description: Project cucumber — live smoke test of search engine found & fixed 3 real bugs; full e2e green on Postgres
metadata: 
  node_type: memory
  type: project
  originSessionId: f4e490cf-f5a1-4af8-9d8e-0f690840ab4d
---

On 2026-06-05 we ran the `search engine/` (find-engine) module live and found 3 real bugs (not env issues), all fixed & verified e2e on real Postgres:

1. **arXiv `http://` → 301 crash** (`sources/arxiv.py`): API now forces HTTPS; old `_ARXIV_API="http://export.arxiv.org/api/query"` returned 301, and the shared client didn't follow redirects so `raise_for_status()` crashed. Fix: `https://` + `follow_redirects=True` added to the `httpx.AsyncClient(...)` in all 4 sources (arxiv/hackernews/github/reddit) as future-proofing.
2. **`ItemORM.xmax` AttributeError** (`storage/repository.py:62`): `xmax` is a Postgres system column not mapped in ORM; upsert returning-clause crashed on first job. Fix: `literal_column("xmax")`.
3. **GitHub `fetch` returned a coroutine, not an async-iterable** (`sources/github.py`): was `async def fetch(...): return self._fetch_pages(...)` → `async for` in orchestrator would `TypeError` at runtime. Every other source is `async def ... yield`. Fix: make `fetch` a plain `def` returning the async generator. (mypy had flagged this; it was a real latent bug — GitHub collection never worked.)

**Verified:** pytest 48 passed, ruff clean, mypy clean (0 errors, was 3). Live HN job via real API: `POST /jobs {"source":"hackernews"}` → success, fetched=10/inserted=10, rows in items/raw_records/jobs. Idempotency: HN re-run uses `jobs.finished_at` watermark → fetched=0, no dupes.

**Committed & pushed:** the find-engine GitHub repo (`art9762/find-engine`) is ARCHIVED (read-only, push 403). The repo layout is two-level: root `Project cucumber` is its own git repo (remote `art9762/project-cucumber`, LIVE) and tracks the engine files directly (NOT a submodule); `search engine/` is a nested git repo pointing at the archived find-engine remote. So push engine changes via the ROOT repo to project-cucumber. The 3 fixes were committed at root as `b6f755e` and pushed `818f07f..b6f755e main`.

**Live collection results (2026-06-05):** arXiv fully works through the pipeline — one run fetched=50/inserted=50 real cs.AI/LG/CL papers (the 429 earlier was just same-IP rate-limiting from a day of hammering; it cleared). Reddit returns `403 Blocked` on `www.reddit.com/r/.../new.json` — Reddit blocks anonymous .json since 2023, needs OAuth `REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET` (source handles it cleanly: job→failed with the 403 in `error`). GitHub still untested (needs `GITHUB_TOKEN`). So token-free sources that actually yield data: **arXiv + Hacker News**.

**Current `.env` (kept by user, gitignored, tokens blank):** `HN_MIN_POINTS=5`, `HN_QUERY=AI OR LLM OR "machine learning" OR agents OR "neural network"`, `ARXIV_CATEGORIES=cs.AI,cs.LG,cs.CL`. Backup at `.env.bak`.

**How to apply:** Engine genuinely works e2e. Postgres runs via `docker-compose up -d` in `search engine/` (Docker Desktop at /Applications/Docker.app, ~2min to start). NOTE: venv console-script shebangs are stale (`project find engine` old path) — always run tools via `.venv/bin/python -m <tool>`, not `.venv/bin/<tool>`. This DB (`items`/`raw_records`/`jobs`) is exactly what `analysis/` reads read-only — handy real data for testing Phase 1. See [[phase-0-analysis-scaffold-done]].
