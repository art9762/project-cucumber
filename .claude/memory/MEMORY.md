# Memory index — Project cucumber

- [Phase 0 analysis scaffold done](phase-0-analysis-scaffold-done.md) — analysis/ caркас built & green; next is Phase 1 classification
- [Trinity gateway config](trinity-gateway-config.md) — Anthropic-compatible LLM gateway + model list used across the project
- [Engine live smoke: 3 bugs fixed](engine-live-smoke-bugs-fixed.md) — arXiv https/redirect, xmax, github coroutine; full e2e green; fixes uncommitted
- [Phase 1 classification done](phase-1-classification-done.md) — analysis/ classify built via swarm; 60/60 items classified live on real Postgres; alembic version_table bug fixed; pytest 103 green; uncommitted, next is Phase 2 scoring
- [Phase 2 scoring done](phase-2-scoring-done.md) — analysis/ score built via 4 agents; 60/60 scored live (18 escalated to Sonnet), tierlist API; config-driven formula; pytest 192 green; uncommitted, next is Phase 3/4
- [Phase 3+4 research & embeddings done](phase-3-4-research-embeddings-done.md) — research (Trinity web_search) + local fastembed/pgvector semantic search built via 7-agent swarm; live verified (60 embedded, 6 researched); PG image→pgvector; pytest 342 green; committed 554a67a
- [Phase 5+6 UI & auth done](phase-5-6-ui-auth-done.md) — React/Vite control panel (6 pages) + cookie-session auth/RBAC + CORS + hardening docs, built via 2-round agent swarm; live verified e2e; pytest 361 green, UI build green; committed+pushed (54cd7a2 backend, fadf16b UI); admin/<dev-pass> local; next is VPS deploy
- [v1.0.0 released + deploy stack done](release-v1-deploy-done.md) — tag/Release/GHCR 1.0.0 live, deploy/ Compose smoke-tested locally; осталось Task 9: VPS deploy (нужны IP+SSH юзера)
- [Global skills setup](global-skills-setup.md) — stop-slop active; 754 cyber skills parked on-disk (not scanned) to save ~22k tok/session; how to re-enable
