# Contributing to PraisonAI

Thank you for your interest! Here's how to get started:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## Where to report issues (hub intake)

| Topic | Report here | Where fixes land |
|-------|-------------|------------------|
| Python SDK, CLI, wrapper | **This repo** ([PraisonAI](https://github.com/MervinPraison/PraisonAI)) | `src/praisonai-agents/`, `src/praisonai/` |
| TypeScript / JavaScript SDK (`npm install praisonai`) | **This repo** (preferred) or [praisonai-js](https://github.com/MervinPraison/praisonai-js) | [praisonai-js](https://github.com/MervinPraison/praisonai-js) → synced to `src/praisonai-ts/` |
| Cross-language parity | **This repo** | Often both Python and praisonai-js PRs |
| Agent-callable tools | **This repo** | [PraisonAI-Tools](https://github.com/MervinPraison/PraisonAI-Tools) |
| Lifecycle plugins (tracing, hooks, guardrails) | **This repo** | [PraisonAI-Plugins](https://github.com/MervinPraison/PraisonAI-Plugins) |

You do **not** need to re-file TypeScript issues on praisonai-js — report on PraisonAI and automation routes fixes to the canonical TS repo.

## Guidelines

- Follow existing code style
- Add tests for new features
- Update documentation as needed
- TypeScript changes: implement in [praisonai-js](https://github.com/MervinPraison/praisonai-js), then run **Sync to PraisonAI Monorepo** workflow to update `src/praisonai-ts/`
