# Agent Instructions

You are working on the PraisonAI project.

## Project Guidelines
- Follow the existing code style and conventions
- Be concise and helpful in responses  
- Test implementation thoroughly
- Ensure backward compatibility with existing APIs
- Follow protocol-driven design. Use the routing table to find the owning package and [ARCHITECTURE.md](ARCHITECTURE.md) §2 for dependency direction.
- Preserve old `praisonai.*` imports and CLI entry points when moving code between packages. See §2.3 of the [Python SDK guide](src/praisonai-agents/AGENTS.md) and the [shim helpers](src/praisonai/praisonai/cli/_shim.py).
- When reviewing a PR or an issue, evaluate whether the change addresses a framework concern or a user goal, and design its surface (params, naming, defaults) accordingly
- The aim of this package is to stay **lightweight and powerful**. Do a critical review at each stage — when triaging an issue, when planning a fix, and when reviewing/implementing a PR. Reject scope creep for the sake of adding features: if a capability already exists (e.g. via existing Agent params like `instructions`/`backstory`/`tools`/`hooks`/`memory`), prefer it over a new API surface. A change must genuinely strengthen the SDK (simpler, more robust, more user-friendly) — do not add knobs, params, modules, or exports that have no live consumer or that merely duplicate existing behaviour.

## Issue and PR routing

Read the [Python SDK guide](src/praisonai-agents/AGENTS.md) for Python changes and the linked manifest when a package boundary is involved. Run the affected tests from the owning package and the wrapper compatibility tests for any changed legacy entry points. See the Python SDK guide §9 for test isolation and live test requirements.

| Area | Source | Package guidance and validation |
|------|--------|---------------------------------|
| Python core SDK and protocols (`praisonaiagents`) | [src/praisonai-agents/](src/praisonai-agents/) | `pytest tests/unit/` |
| Wrapper, classic CLI, integrations, serve and dashboard (`praisonai`) | [src/praisonai/](src/praisonai/) | `pytest tests/unit/` or the affected suites |
| Agentic terminal CLI and OpenShip runtime (`praisonai-code`) | [src/praisonai-code/](src/praisonai-code/) | Python SDK guide §2.3 and `pytest tests/unit/` |
| Bots and gateway (`praisonai-bot`) | [src/praisonai-bot/](src/praisonai-bot/) | Python SDK guide §12, [C9 manifest](src/praisonai/tests/PRAISONAI_BOT_MANIFEST.md), `pytest tests/unit/` |
| Fine-tuning and agent training (`praisonai-train`) | [src/praisonai-train/](src/praisonai-train/) | [C10 manifest](src/praisonai/tests/PRAISONAI_TRAIN_MANIFEST.md), `pytest tests/unit/` |
| Browser automation (`praisonai-browser`) | [src/praisonai-browser/](src/praisonai-browser/) | [C11 manifest](src/praisonai/tests/PRAISONAI_BROWSER_MANIFEST.md), `pytest tests/browser/` |
| MCP server host (`praisonai-mcp`) | [src/praisonai-mcp/](src/praisonai-mcp/) | [C12 manifest](src/praisonai/tests/PRAISONAI_MCP_MANIFEST.md), `pytest tests/unit/ tests/mcp_server/` |
| Sandbox backends (`praisonai-sandbox`) | [src/praisonai-sandbox/](src/praisonai-sandbox/) | [C13 manifest](src/praisonai/tests/PRAISONAI_SANDBOX_MANIFEST.md), `pytest tests/ -m 'not network and not local_service'` |
| Deployment (`praisonai-deploy`) | [src/praisonai-deploy/](src/praisonai-deploy/) | [C14 manifest](src/praisonai/tests/PRAISONAI_DEPLOY_MANIFEST.md), `pytest tests/ -m 'not network and not local_service'` |
| TypeScript and JavaScript SDK (npm `praisonai`) | [src/praisonai-ts/](src/praisonai-ts/) | [TypeScript SDK guide](src/praisonai-ts/AGENTS.md), `npm run build && npm test` |
| Rust SDK and CLI | [src/praisonai-rust/](src/praisonai-rust/) | [Rust SDK guide](src/praisonai-rust/AGENTS.md), `cargo test --workspace` |
| Desktop app | [src/praisonai-desktop/](src/praisonai-desktop/) | [Desktop CI](.github/workflows/desktop.yml) and [release checks](.github/workflows/desktop-release.yml) |
| Mobile app | [src/praisonai-mobile/](src/praisonai-mobile/) | [Mobile CI](.github/workflows/mobile.yml), including the TypeScript SDK build used by the app |
| Agent-callable tools and new vendor `*_tools.py` | [PraisonAI-Tools](https://github.com/MervinPraison/PraisonAI-Tools) | Add new vendor tools in PraisonAI-Tools. Existing core tools are legacy. Run repo tests. |
| Lifecycle plugins | [PraisonAI-Plugins](https://github.com/MervinPraison/PraisonAI-Plugins) | Repo tests |
| Documentation | [PraisonAIDocs](https://github.com/MervinPraison/PraisonAIDocs) | `nav-check` |

For TS/JS issues and PRs, always read the TypeScript SDK guide. Implement fixes in this monorepo. The **Sync to praisonai-js** workflow updates the [npm mirror](https://github.com/MervinPraison/praisonai-js) from here. Include Mobile CI when changing SDK exports consumed by the app.

## Reviewing a pull request

- Use the review instructions from `main` and record the PR head SHA you reviewed. Read the full diff and the guides for each package it affects.
- Trace changes to public APIs, dependencies, entry points or shared protocols into the packages and legacy paths that consume them.
- Report actionable findings with file and line references. List which tests ran, their results and any unavailable checks. A green shard establishes coverage only for the tests it collects.
- Keep review-only requests read-only. Apply or push fixes only when asked.

## Before you build

Check these before writing code. If a check fails, move the code or drop the change.

- **Package and tier.** Use the routing table above. Tier 1 `praisonaiagents` holds protocols, hooks, base classes and light adapters only. Heavy code goes to a Tier 2 package or the wrapper.
- **Dependency direction.** Tier 2 packages depend only on `praisonaiagents`, never on the `praisonai` wrapper or on each other. Reach another tier through a lazy `_*_bridge` module. `src/praisonai/tests/unit/test_tier_dependencies.py` enforces this.
- **Reuse before adding.** Does an Agent parameter, config object, hook or tool already do it? Then do not add a parameter, module or export.
- **New extension point.** Write the `XProtocol` in that module's `protocols.py` first, then the adapters.
- **New Agent parameter.** Resolve it in `config/agent_init.py` (`resolve_agent_<param>`), using `False` / `True` / `XConfig`.
- **Imports.** No optional dependency at module level, and nothing heavy in `__init__.py`.
- **Speed.** For changes to `Agent.__init__` or `config/agent_init.py`, run `benchmarks/simple_benchmark.py` and `benchmarks/import_time.py` before and after. Neither may get slower.

## Pull request rules

- Base every PR on `main`. Never base a PR on another PR's branch: a child merged into a parent branch does not reach `main`.
- Keep PRs small and independently testable. Auto-merge eligibility requires at most 5 non-test files and fewer than 100 changed non-test lines. Larger PRs require manual review.
- PRs that edit the same lines (for example one sorted import) go in one PR or land one at a time.
- The merge gate can auto-merge eligible non-draft PRs after it verifies checks and the review verdict for the current head SHA. A maintainer merges fork PRs manually. Open as a draft to hold a PR for human review.
- Before merging several PRs together, merge them in a scratch worktree and run every touched test file; two green PRs can break `main` together.
- No feature is removed without a deprecation cycle. Prefer delegate, shim or alias.
- Guard and ratchet tests (`tests/unit/named_loggers/`, `test_silent_except_ratchet.py`, `tests/unit/contract/`, `tests/unit/security/`, `tools/test_outbound_fetch_guard.py`, `test_tier_dependencies.py`) encode decisions. Fix the code, not the guard.

## Security

- Report and discuss vulnerabilities only through private advisories, as `SECURITY.md` describes. Do not describe an unfixed vulnerability in a public issue, PR title, PR body or commit message; use a neutral title.
- Fix the class, not one input: a path check, URL check, bind default or approval gate belongs in one shared helper with a test that covers every caller.
- A new network server defaults to loopback (`127.0.0.1`); a non-loopback bind needs authentication.

Use the shared helper for each concern; do not write a one-off check:

| Concern | Shared helper in `praisonaiagents` |
|---|---|
| Server bind and token | `require_bind_token`, `token_matches` (`agent/launch_security.py`) |
| A path from a model, a peer or a project file | `resolve_inside` (`tools/path_safety.py`) |
| An outbound URL from a model or a peer | `safe_fetch`, `safe_stream` (`tools/url_safety.py`) |
| Settings read from a project folder | `key_allowed`, `drop_project_trust_keys` (`config/trust.py`) |
| MCP servers named in a project file | `mcp/trust.py` (`mcp.trusted_servers` in the user's config) |
| A tool with an outside effect | Declare that it needs approval; `tests/unit/approval/test_side_effect_tools_require_approval.py` lists every such tool |
