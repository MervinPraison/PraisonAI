# TypeScript SDK — monorepo reference

## Fix path

`src/praisonai-ts/` — canonical in monorepo. Read `src/praisonai-ts/AGENTS.md`.

## Automation (no external TS routing)

| File | TS behaviour |
|------|----------------|
| `.github/workflows/claude.yml` | Fix in `src/praisonai-ts/`; STEP 3-ALT = Tools/Docs/Plugins only |
| `.github/scripts/merge-gate.js` | FINAL scope includes `src/praisonai-ts/`; no `tsMirrorPathReasons` block |
| `.github/workflows/claude-merge-gate.yml` | No BLOCK for src/praisonai-ts/ |
| `CONTRIBUTING.md` | TS fixes in monorepo |
| `.github/workflows/sync-to-praisonai-js.yml` | Mirror sync: monorepo → praisonai-js |

## Mirror sync (after TS merge)

```bash
gh workflow run "Sync to praisonai-js" --repo MervinPraison/PraisonAI
```

Direction: **`src/praisonai-ts/` → praisonai-js** (not the reverse).

## Tests

```bash
cd src/praisonai-ts && npm install && npm run build && npm test
```

## External repos (not TS)

- PraisonAI-Tools — agent-callable tools
- PraisonAI-Plugins — lifecycle plugins
- PraisonAIDocs — documentation

## Anti-patterns

| Wrong | Right |
|-------|-------|
| Route TS fix to praisonai-js in merge gate / Claude | Fix in `src/praisonai-ts/` |
| Sync praisonai-js → monorepo | Sync **monorepo → praisonai-js** after merge |

## praisonai-js mirror

npm repo; updated from monorepo via `Sync to praisonai-js`. See praisonai-js `SYNC.md`.
