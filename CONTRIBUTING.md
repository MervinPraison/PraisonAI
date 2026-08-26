# Contributing to PraisonAI

Thank you for your interest! Here's how to get started:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## Where to report issues

| Topic | Report here | Where fixes land |
|-------|-------------|------------------|
| Python SDK, CLI, wrapper | **This repo** | `src/praisonai-agents/`, `src/praisonai/` |
| TypeScript / JavaScript (`npm install praisonai`) | **This repo** | `src/praisonai-ts/` |
| Cross-language parity | **This repo** | Often both Python and TypeScript paths |
| Agent-callable tools | **This repo** | [PraisonAI-Tools](https://github.com/MervinPraison/PraisonAI-Tools) |
| Lifecycle plugins (tracing, hooks, guardrails) | **This repo** | [PraisonAI-Plugins](https://github.com/MervinPraison/PraisonAI-Plugins) |

## Guidelines

- Follow existing code style
- Add tests for new features
- Update documentation as needed
- TypeScript changes: implement in `src/praisonai-ts/` and run `npm test` there
