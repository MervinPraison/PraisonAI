# Config kernel — Phase 0 substitute

Wrapper Architecture Phase 0 proposed `praisonai/common/` for shared configuration.
That extraction was **skipped**; the config kernel lives in **`praisonai-code`** instead.

## Canonical location

| Concern | Module |
|---------|--------|
| Config schema / resolver | `praisonai_code/cli/configuration/` |
| Env helpers | `praisonai_code/cli/utils/env_utils.py` |
| LLM credentials | `praisonai_code/llm/credentials.py` |

## Cross-tier access

| Consumer | Mechanism |
|----------|-----------|
| `praisonai-code` CLI | Direct import |
| `praisonai-bot` | Lazy `praisonai_bot._code_bridge` (no PyPI cycle) |
| `praisonai` wrapper | Direct import via `praisonai-code` dependency |

## Not planned (deferred)

- **`praisonai/common/` folder** — superseded by code-first config kernel
- **uv workspace root** — monorepo still uses per-package path deps
- **`praisonai daemon` → `praisonai runtime` rename** — warm-runtime naming unchanged; OS gateway service remains `praisonai-bot`

## Standalone limitations

| Feature | Standalone `praisonai-bot` | Needs wrapper co-install |
|---------|---------------------------|--------------------------|
| Gateway scheduler tick | Yes (`praisonai_bot.scheduler`) | — |
| Async jobs API (`praisonai.jobs`) | No | Yes (recipe + legacy PraisonAI paths) |
| PraisonAIUI jobs/kanban injection | Partial (kanban store in bot) | Jobs store/executor |
