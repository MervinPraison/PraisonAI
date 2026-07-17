# Agent Instructions

You are working on the PraisonAI project.

## Project Guidelines
- Follow the existing code style and conventions
- Be concise and helpful in responses  
- Test implementation thoroughly
- Ensure backward compatibility with existing APIs
- Follow protocol-driven design across the eight packages: core protocols in `praisonaiagents/`, agentic terminal CLI in `praisonai-code/`, bots/gateway in `praisonai-bot/`, LLM fine-tuning + agent training in `praisonai-train/`, browser automation in `praisonai-browser/`, MCP server host in `praisonai-mcp/`, sandbox backends in `praisonai-sandbox/`, integrations/serve/dashboard in the `praisonai/` wrapper
- Preserve old `praisonai.*` import paths via shims when moving code between packages (see §2.3 in `src/praisonai-agents/AGENTS.md`; shim helpers in `src/praisonai/praisonai/cli/_shim.py`)
- Package boundaries and dependency rules: `ARCHITECTURE.md` §2 (Tier 2 packages must never PyPI-depend on the wrapper; cross-tier access goes through lazy `_*_bridge` modules)
- Boundary manifests: `src/praisonai/tests/PRAISONAI_BOT_MANIFEST.md` (C9), `src/praisonai/tests/PRAISONAI_TRAIN_MANIFEST.md` (C10), `src/praisonai/tests/PRAISONAI_BROWSER_MANIFEST.md` (C11), `src/praisonai/tests/PRAISONAI_MCP_MANIFEST.md` (C12), `src/praisonai/tests/PRAISONAI_SANDBOX_MANIFEST.md` (C13)
- When reviewing a PR or an issue, evaluate whether the change addresses a framework concern or a user goal, and design its surface (params, naming, defaults) accordingly
- The aim of this package is to stay **lightweight and powerful**. Do a critical review at each stage — when triaging an issue, when planning a fix, and when reviewing/implementing a PR. Reject scope creep for the sake of adding features: if a capability already exists (e.g. via existing Agent params like `instructions`/`backstory`/`tools`/`hooks`/`memory`), prefer it over a new API surface. A change must genuinely strengthen the SDK (simpler, more robust, more user-friendly) — do not add knobs, params, modules, or exports that have no live consumer or that merely duplicate existing behaviour.