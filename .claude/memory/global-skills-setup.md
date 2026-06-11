---
name: global-skills-setup
description: Where globally-installed agent skills live and how to enable/disable them without re-token-cost
metadata: 
  node_type: memory
  type: reference
  originSessionId: 82cfe3bc-4906-43e9-95b2-a5f53e15c93d
---

Global agent skills (installed 2026-06-10 via `npx skills add ... --global`) live as real files in `~/.agents/skills/` and are exposed to Claude Code via symlinks in `~/.claude/skills/`. Claude scans the symlink dir's frontmatter every session (~30 tokens/skill), so only symlinks in `~/.claude/skills/` cost tokens — files in `~/.agents/skills/` alone cost nothing.

**Currently active (symlinked):** `stop-slop` only (strips AI writing tells; negligible cost).

**Installed but parked on-disk (NOT scanned):** `mukul975/Anthropic-Cybersecurity-Skills` — 754 skills, 35M, in `~/.agents/skills/`. Symlinks were deleted on 2026-06-10 because all 754 active = ~22k tokens/session overhead for skills rarely needed in this project.

**Re-enable a parked cyber skill (no reinstall needed):**
- One-off, zero permanent cost: `npx -y skills@latest use mukul975/Anthropic-Cybersecurity-Skills@<skill-name>`
- Re-link a few, project-scoped: `cd <project> && npx -y skills@latest add mukul975/Anthropic-Cybersecurity-Skills --skill '<name>' --project`
- Or just read `~/.agents/skills/<skill-name>/SKILL.md` directly.

**`/plugin`-based installs (user runs these, not the agent):** Superpowers (`obra/superpowers-marketplace`) as primary framework; Impeccable (`pbakaus/impeccable`) for UI design/polish. GStack + ECC deliberately skipped to avoid stacking competing harnesses.
