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
- After merge, sync the npm mirror: `gh workflow run "Sync to praisonai-js" --repo MervinPraison/PraisonAI`

## Release gate: live SDK smoke

Every PyPI release must pass 7/7 core live scenarios in `scripts/live_sdk_smoke.py`. `pypi-release.yml` runs it as a required job, so a failure or a missing `OPENAI_API_KEY` blocks publishing. A waiver needs a written exception in the release notes.

- Reproduce locally: `OPENAI_API_KEY=... python scripts/live_sdk_smoke.py` (add `--extended` for the non-blocking set)
- Run in CI: `gh workflow run "Live SDK Smoke"`, or add the `run-live-smoke` label to a risky SDK PR
- The extended set runs weekly. Failed scenario names are printed and saved to the `live-sdk-smoke` artifact (`live_sdk_smoke.json`)
