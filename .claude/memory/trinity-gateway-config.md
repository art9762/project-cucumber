---
name: trinity-gateway-config
description: Trinity is an Anthropic-compatible LLM gateway used across Project cucumber
metadata: 
  node_type: memory
  type: reference
  originSessionId: f4e490cf-f5a1-4af8-9d8e-0f690840ab4d
---

Trinity = Anthropic-compatible gateway. Use the official `anthropic` SDK pointed at it:
`ANTHROPIC_BASE_URL=https://gate.trinity.tg/aurora`, token in `ANTHROPIC_AUTH_TOKEN`.

Models (ctx): claude-opus-4-8 / -1m (frontier, expensive), claude-opus-4-7, claude-opus-4-6, claude-sonnet-4-6 (best general, normal price) / -1m, claude-haiku-4-5 (cheap, for heavy/bulk analysis). Doc: `docs/Trinity.md`.

In `analysis/`: cheap=`claude-haiku-4-5` (bulk), deep=`claude-sonnet-4-6` (escalation). Secrets only from env / `.env` (never commit the token). Related: [[phase-0-analysis-scaffold-done]].
