---
name: phase-2-scoring-done
description: "Project cucumber — analysis/ Phase 2 (scoring + tierlist) built, tested, and verified live on real Postgres"
metadata: 
  node_type: memory
  type: project
  originSessionId: f4e490cf-f5a1-4af8-9d8e-0f690840ab4d
---

On 2026-06-05 built **Phase 2 (scoring + tierlist)** of `analysis/` via 4 parallel coder agents on disjoint files (I owned the frozen contract `score/models.py` + the spec `docs/phase-2-scoring.md` + integration). Cheap model (Haiku) rates each classified item on 5 params; a config-driven formula → coefficient → tier S/A/B/C/D; "borderline/important" items escalate to the deep model (Sonnet) and get re-scored.

**5 params (each 0..1, `PARAM_NAMES` order):** relevance, complexity, novelty, maturity, potential. `coefficient = clamp01(bias + Σ signed_weights[k]·param_k)` — relevance/novelty/potential have **positive** weights, complexity/maturity **negative** (they're costs). Tier = first threshold (desc) ≤ coefficient. Defaults in `ScoringConfig.default()`: weights relevance .45 / novelty .20 / potential .20 / complexity -.10 / maturity -.15, bias .15; tiers S≥.80 A≥.65 B≥.50 C≥.35 D≥0. Escalate if confidence<.55 OR coef≥.80 OR within .03 of any tier boundary.

**New files** (`analysis/analysis/score/`): `models.py` (frozen contract: `ScoreParams`/`ScoreResult`/`ScoringConfig`/`ScoreStats`, `PARAM_NAMES` — I wrote this first to kill cross-file races), `prompt.py` (`build_score_prompt`/`parse_scores`, pure, per-param clamp to .5 default), `formula.py` (`compute_coefficient`/`assign_tier`/`should_escalate`/`load_scoring_config` — reads optional env overrides via getattr, falls back to default), `selector.py` (`select_unscored_items` → items with category_id set but coefficient NULL, INNER JOIN), `scorer.py` (`run_scoring(*, analysis_sessionmaker, trinity, config=None, limit=None, cheap_model=None, deep_model=None)` — mirrors classifier.py: early-commit run row, `begin_nested()` SAVEPOINT per item, **UPDATEs** the existing item_analysis row from Phase 1, never inserts), `__main__.py` (`python -m analysis.score [--limit N] [--cheap-model] [--deep-model]`). API: `api/score_schemas.py` + `api/routers/scores.py` (`GET /tierlist?tier=&category_id=&limit=` coef DESC, `GET /items/{id}/score` 404 if none, `POST /score`), wired into `main.py`.

**No new migration** — Phase 0 already had `item_analysis.scores`(JSONB)/`.coefficient`(Float)/`.tier`(String(1)) as nullable placeholders.

**Integration edits (I did these, not agents):** `main.py` +`scores.router`; `config.py` +6 optional scoring override fields (`scoring_weights`/`scoring_bias`/`scoring_tiers` as JSON strings, `escalate_*`) — all None by default so `load_scoring_config()` uses defaults; change weights/tiers via env to re-score without code change.

**Verified live on real Postgres** (the same 60 items, classified by Phase 1): `python -m analysis.score --limit 60` → scored 60/60, **0 failed, 18 escalated to Sonnet** (42 stayed Haiku), tiers A=44 (avg coef .719) / B=16 (avg .604), 1 `analysis_runs` row kind=score status=success. Idempotent re-run → seen=0. API live via uvicorn:8112 — /tierlist sorts by coef desc, ?tier=B returns exactly the 16 B-items, /items/{id}/score returns full 5-param scores + model_used, 404 on missing. Gates: **pytest 192 passed** (was 103), ruff clean, mypy clean (33 files).

**How to apply:** same run recipe as Phase 1 — Postgres up via `search engine/docker-compose` (container `searchengine-postgres-1`), then from `analysis/`: `export DB_URL_ANALYSIS=postgresql+asyncpg://findengine:findengine@localhost:5432/findengine; DB_URL_READ=same; ANTHROPIC_BASE_URL=https://gate.trinity.tg/aurora` + `ANTHROPIC_AUTH_TOKEN` from shell env (71 chars, never committed), then `.venv/bin/python -m analysis.score`. Tools via `.venv/bin/python -m <tool>` (stale shebangs); ruff/mypy need ABSOLUTE paths or the `analysis/` dir form (space in repo path breaks relative globs). Phase 2 work is **uncommitted** — commit/push only when asked, via ROOT `project-cucumber` repo (find-engine remote archived). Next: Phase 3 (research/web-search) or Phase 4 (embeddings + API). See [[phase-1-classification-done]], [[phase-0-analysis-scaffold-done]], [[trinity-gateway-config]].
