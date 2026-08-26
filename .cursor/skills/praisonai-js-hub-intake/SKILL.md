---
name: praisonai-js-hub-intake
description: >-
  Explains Option B hub intake for PraisonAI TypeScript/JavaScript (npm praisonai):
  accept TS issues on MervinPraison/PraisonAI, implement fixes in MervinPraison/praisonai-js,
  sync to src/praisonai-ts/. Use when routing issues, implementing TS fixes, sync workflows,
  merge-gate TS paths, or when the user mentions praisonai-js, praisonai-ts, npm SDK, or TS hub intake.
---

# praisonai-js hub intake (Option B)

## Model in one sentence

**Users file TypeScript issues on [PraisonAI](https://github.com/MervinPraison/PraisonAI); fixes land in [praisonai-js](https://github.com/MervinPraison/praisonai-js); the monorepo `src/praisonai-ts/` is a sync mirror only.**

Do **not** ask users to re-file on praisonai-js unless they opened a duplicate on the wrong repo.

## Routing table

| Topic | Report | Fix repo | Monorepo mirror |
|-------|--------|----------|-----------------|
| Python SDK / CLI | PraisonAI | `src/praisonai-agents/`, `src/praisonai/` | — |
| TypeScript / npm `praisonai` | PraisonAI (preferred) or praisonai-js | **praisonai-js** | `src/praisonai-ts/` |
| Cross-language parity | PraisonAI | Often both Python + praisonai-js | sync after TS merge |
| Agent-callable tools | PraisonAI | PraisonAI-Tools | — |
| Lifecycle plugins | PraisonAI | PraisonAI-Plugins | — |

## End-to-end flow

```
Issue on PraisonAI
  → issue-triage: labels javascript, praisonai-js (if TS focus)
  → claude label → Claude STEP 3-ALT clones praisonai-js
  → PR on praisonai-js with body: Fixes MervinPraison/PraisonAI#N
  → merge on praisonai-js (CI + merge gate there)
  → Sync to PraisonAI Monorepo workflow on praisonai-js
  → PR on PraisonAI: sync: update src/praisonai-ts/...
```

## Agent rules

1. **Never implement TS features in `src/praisonai-ts/` on PraisonAI** — edit praisonai-js instead.
2. **External PR body** must include `Fixes MervinPraison/PraisonAI#<n>` when fixing a hub issue.
3. **After praisonai-js merge**, run sync workflow (or tell maintainer to):
   ```bash
   gh workflow run "Sync to PraisonAI Monorepo" \
     --repo MervinPraison/praisonai-js \
     -f upstream_issue=<issue_number>
   ```
4. **Merge gate on PraisonAI** blocks direct `src/praisonai-ts/` changes unless sync PR (title `sync:` or body mentions praisonai-js).
5. **Tests for TS fixes**: `npm install && npm run build && npm test` in praisonai-js clone.

## TS issue detection (PraisonAI triage)

Labels `javascript` + `praisonai-js` when issue mentions: `praisonai-js`, `praisonai-ts`, `src/praisonai-ts`, `typescript`+`praisonai`, `npm`+`praisonai` (not pypi).

## Key files

See [reference.md](reference.md) for paths in both repos.

## Quick commands

```bash
# Sync Claude secrets to praisonai-js (from PraisonAI hub)
gh workflow run "Sync Claude Secrets" \
  --repo MervinPraison/PraisonAI \
  -f target_repo=MervinPraison/praisonai-js

# Sync code praisonai-js → monorepo mirror
gh workflow run "Sync to PraisonAI Monorepo" \
  --repo MervinPraison/praisonai-js \
  -f upstream_issue=1234
```

## Related docs

- Monorepo: `CONTRIBUTING.md` (hub intake table)
- praisonai-js: `AGENTS.md` §2.1.1 Hub intake
- Security: `SECURITY.md` (npm canonical = praisonai-js)

## Cursor skill locations

| Repo | Path |
|------|------|
| PraisonAI monorepo | `.cursor/skills/praisonai-js-hub-intake/` |
| praisonai-js | `.cursor/skills/praisonai-js-hub-intake/` |
