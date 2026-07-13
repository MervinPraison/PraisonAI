# Agent Instructions

You are working on the PraisonAI project.

## Project Guidelines
- Follow the existing code style and conventions
- Be concise and helpful in responses  
- Test implementation thoroughly
- Ensure backward compatibility with existing APIs
- Follow protocol-driven design across the five packages: core protocols in `praisonaiagents/`, agentic terminal CLI in `praisonai-code/`, bots/gateway in `praisonai-bot/`, LLM fine-tuning + agent training in `praisonai-train/`, integrations/serve/dashboard in the `praisonai/` wrapper
- Preserve old `praisonai.*` import paths via shims when moving code between packages (see §2.3 in `src/praisonai-agents/AGENTS.md`; shim helpers in `src/praisonai/praisonai/cli/_shim.py`)
- Package boundaries and dependency rules: `ARCHITECTURE.md` §2 (Tier 2 packages must never PyPI-depend on the wrapper; cross-tier access goes through lazy `_*_bridge` modules)
- Boundary manifests: `src/praisonai/tests/PRAISONAI_BOT_MANIFEST.md` (C9), `src/praisonai/tests/PRAISONAI_TRAIN_MANIFEST.md` (C10)
- When reviewing a PR or an issue, evaluate whether the change addresses a framework concern or a user goal, and design its surface (params, naming, defaults) accordingly