# Agent Instructions

You are working on the PraisonAI project.

## Project Guidelines
- Follow the existing code style and conventions
- Be concise and helpful in responses  
- Test implementation thoroughly
- Ensure backward compatibility with existing APIs
- Follow protocol-driven design across the nine Python PyPI packages plus the TypeScript SDK: core protocols in `praisonaiagents/`, agentic terminal CLI in `praisonai-code/`, bots/gateway in `praisonai-bot/`, LLM fine-tuning + agent training in `praisonai-train/`, browser automation in `praisonai-browser/`, MCP server host in `praisonai-mcp/`, sandbox backends in `praisonai-sandbox/`, deployment in `praisonai-deploy/`, integrations/serve/dashboard in the `praisonai/` wrapper, TypeScript/JavaScript SDK in `src/praisonai-ts/` (`npm: praisonai`)
- **TypeScript review routing:** For TS/JS issues and PRs, read [`src/praisonai-ts/AGENTS.md`](src/praisonai-ts/AGENTS.md) (not just this file). Canonical source is `src/praisonai-ts/` in this monorepo; [MervinPraison/praisonai-js](https://github.com/MervinPraison/praisonai-js) is the npm mirror only (sync: monorepo → praisonai-js via workflow **Sync to praisonai-js**). Do not implement TS fixes in praisonai-js for PraisonAI issues.
- Preserve old `praisonai.*` import paths via shims when moving code between packages (see §2.3 in `src/praisonai-agents/AGENTS.md`; shim helpers in `src/praisonai/praisonai/cli/_shim.py`)
- Package boundaries and dependency rules: `ARCHITECTURE.md` §2 (Tier 2 packages must never PyPI-depend on the wrapper; cross-tier access goes through lazy `_*_bridge` modules)
- Boundary manifests: `src/praisonai/tests/PRAISONAI_BOT_MANIFEST.md` (C9), `src/praisonai/tests/PRAISONAI_TRAIN_MANIFEST.md` (C10), `src/praisonai/tests/PRAISONAI_BROWSER_MANIFEST.md` (C11), `src/praisonai/tests/PRAISONAI_MCP_MANIFEST.md` (C12), `src/praisonai/tests/PRAISONAI_SANDBOX_MANIFEST.md` (C13), `src/praisonai/tests/PRAISONAI_DEPLOY_MANIFEST.md` (C14)
- When reviewing a PR or an issue, evaluate whether the change addresses a framework concern or a user goal, and design its surface (params, naming, defaults) accordingly
- The aim of this package is to stay **lightweight and powerful**. Do a critical review at each stage — when triaging an issue, when planning a fix, and when reviewing/implementing a PR. Reject scope creep for the sake of adding features: if a capability already exists (e.g. via existing Agent params like `instructions`/`backstory`/`tools`/`hooks`/`memory`), prefer it over a new API surface. A change must genuinely strengthen the SDK (simpler, more robust, more user-friendly) — do not add knobs, params, modules, or exports that have no live consumer or that merely duplicate existing behaviour.

## Issue and PR routing

| Area | Where to implement | AGENTS.md to read | Tests |
|------|-------------------|-------------------|-------|
| Python core SDK | `src/praisonai-agents/praisonaiagents/` | `src/praisonai-agents/AGENTS.md` | `pytest` in `src/praisonai-agents/tests/` |
| Python wrapper / CLI | `src/praisonai/`, `src/praisonai-code/`, etc. | `src/praisonai-agents/AGENTS.md` | `pytest` under `src/praisonai/tests/` |
| **TypeScript / JavaScript SDK** | **`src/praisonai-ts/`** | **`src/praisonai-ts/AGENTS.md`** | `cd src/praisonai-ts && npm run build && npm test` |
| Agent-callable tools / new vendor `*_tools.py` | [PraisonAI-Tools](https://github.com/MervinPraison/PraisonAI-Tools) — **not** new modules under `praisonaiagents/tools/` (legacy bundled tools are not precedent) | — | repo tests |
| Lifecycle plugins | [PraisonAI-Plugins](https://github.com/MervinPraison/PraisonAI-Plugins) | — | repo tests |
| Documentation | [PraisonAIDocs](https://github.com/MervinPraison/PraisonAIDocs) | — | `nav-check` |
| Rust SDK | `src/praisonai-rust/` | `src/praisonai-rust/AGENTS.md` | `cargo test` in `src/praisonai-rust/` |
| Bots / gateway | `src/praisonai-bot/` (wrapper `praisonai.bots`/`gateway` are shims) | `src/praisonai-agents/AGENTS.md` §2.3, §12 | `pytest` in the package's tests |
| npm mirror (read-only for fixes) | [praisonai-js](https://github.com/MervinPraison/praisonai-js) | mirror of `src/praisonai-ts/AGENTS.md` | CI on praisonai-js |

## Pull request rules

- Base every PR on `main`. Never base a PR on another PR's branch: a child merged into a parent branch does not reach `main`.
- Keep a PR small: aim for at most 5 non-test files and under 100 non-test lines. Split larger work into steps, each with its own test.
- PRs that edit the same lines (for example one sorted import) go in one PR or land one at a time.
- A non-draft PR may be auto-merged by the merge gate once checks pass. Open as a draft when a human must merge.
- Before merging several PRs together, merge them in a scratch worktree and run every touched test file; two green PRs can break `main` together.
- No feature is removed without a deprecation cycle. Prefer delegate, shim or alias.
- Guard and ratchet tests (`tests/unit/named_loggers/`, `test_silent_except_ratchet.py`, `tests/unit/contract/`) encode decisions. Fix the code, not the guard.

## Security

- Report and discuss vulnerabilities only through private advisories, as `SECURITY.md` describes. Do not describe an unfixed vulnerability in a public issue, PR title, PR body or commit message; use a neutral title.
- Fix the class, not one input: a path check, URL check, bind default or approval gate belongs in one shared helper with a test that covers every caller.
- A new network server defaults to loopback (`127.0.0.1`); a non-loopback bind needs authentication.
