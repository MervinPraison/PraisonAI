---
name: praisonai-js-hub-intake
description: >-
  Explains TypeScript/JavaScript issue and fix routing in the PraisonAI monorepo:
  TS issues filed on MervinPraison/PraisonAI, fixes implemented in src/praisonai-ts/.
  Use when routing npm/TS issues, merge-gate TS paths, or when the user mentions
  praisonai-ts, javascript label, or TypeScript SDK in the monorepo.
---

# TypeScript SDK in the PraisonAI monorepo

## Model

**Issues and fixes both live in `MervinPraison/PraisonAI`.** TypeScript code path: `src/praisonai-ts/`.

Do **not** route TS fixes to external repos in automation prompts. The separate [praisonai-js](https://github.com/MervinPraison/praisonai-js) repo is an npm mirror updated **from** the monorepo (`Sync to praisonai-js` workflow).

## Routing table

| Topic | Report | Fix path |
|-------|--------|----------|
| Python SDK / CLI | PraisonAI | `src/praisonai-agents/`, `src/praisonai/` |
| TypeScript / npm | PraisonAI | **`src/praisonai-ts/`** |
| Agent-callable tools | PraisonAI | PraisonAI-Tools (external) |
| Lifecycle plugins | PraisonAI | PraisonAI-Plugins (external) |

## Agent rules

1. TS fixes → edit **`src/praisonai-ts/`** in the monorepo.
2. Read **`src/praisonai-ts/AGENTS.md`** for TS architecture rules.
3. Tests: `cd src/praisonai-ts && npm install && npm run build && npm test`.
4. Merge gate FINAL reviewer: Python + `src/praisonai-ts/` in scope; **no praisonai-js routing line**.
5. External STEP 3-ALT only for Tools, Docs, Plugins — not TS.

## Issue triage

`javascript` label when issue mentions typescript, javascript, or npm.

## Key automation files

See [reference.md](reference.md).
