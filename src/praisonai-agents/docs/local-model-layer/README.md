# Local Model Layer — implementation ledger

**Status:** every order below has an open PR. See §4.
**Owner workstream:** local model runtimes (Ollama, LM Studio, llama.cpp, vLLM, MLX, `transformers serve`)
**Created:** 2026-09-03

---

## 0. How to use this document

This directory is a **work-order ledger**. It exists so that any agent — including one
with no memory of the conversation that produced it — can pick up exactly one unit of
work and execute it correctly, in isolation, without re-deriving the analysis.

**If you are an agent starting work here, do this in order:**

1. Read [`00-ground-truth.md`](00-ground-truth.md). It records what was measured, how, and
   when. Do not trust a claim in any work order that contradicts it; re-measure instead.
2. Read §2 (Invariants) and §3 (File ownership) of this file. §3 is what stops two agents
   corrupting each other's work.
3. Open the single work order you were assigned. Execute only that one.
4. Update the status row in §4 of this file in the same commit as your change. That row is
   the only shared file content; keep the edit to one line to avoid conflicts.

**Do not** expand scope, batch two work orders into one PR, or "fix while you're in there".
Each order is independently revertible by design and that property is worth more than
convenience.

> **Two corrections this ledger has already had to make.** Both were caught by measuring rather
> than reasoning, and both would have sent an agent down the wrong path.
>
> **The D7 root cause is not `provider_ollama`.** The audit blamed the per-file `provider_ollama`
> tag. Measurement (`04-test-gating.md` §2) shows `not network` deselects all seven tests **on its
> own**, because the plugin implies `network` from *any* provider marker and the file also matches
> `provider_openai`. **Removing `not provider_ollama` from the workflows would change nothing.**
> That is why order `04` touches no YAML at all — the fix is marker-side.
> Its first draft told an agent to "wire
> the twelve dead adapter methods". Measurement (`06-adapter-revival.md` §1) says the opposite:
> **12 of 20 items should be deleted, only 3 wired.** Six of the dead methods have no inline
> equivalent anywhere — they are speculative API, and an agent told to "wire them up" would
> invent an implementation that no test could ever have failed against. Read the decision table
> before touching `llm/adapters/`; do not act on the summary in §1 of this file.

---

## 1. Why this work exists

Every local runtime worth supporting already speaks `POST /v1/chat/completions`, and
`litellm` already handles that transport. So the problem is not calling local models — the
SDK can already do that. The problems are:

- **Discovery.** A user with a running daemon still hand-types a URL, a port and an exact
  model tag; getting any one wrong produces `OPENAI_API_KEY environment variable is required`.
- **Capability.** "Does this model support tools?" is answerable by asking the server
  (`/api/show`, `/props`, `/server_info`). The SDK asks nothing and guesses from a name prefix.
- **Quirks.** Local stacks fail silently with HTTP 200. The sharpest: sending `format` and
  `tools` together to Ollama suppresses the tool call and the model fabricates an answer.

The layer being built is therefore a **resolver, not a transport**: it returns data about
what is running and what it will get wrong. Compensating behaviour stays in
`llm/adapters/`, which already declares methods for exactly this purpose.

---

## 2. Invariants — never break these

These come from `src/praisonai-agents/AGENTS.md` §4.6 plus the structural review in
`00-ground-truth.md`. Every work order inherits them; none may waive them.

| # | Invariant | Why it binds this work specifically |
|---|-----------|--------------------------------------|
| I1 | **Backward compatible.** Public API changes need a deprecation cycle. | Several fixes change which code path a given input takes. Each order carries an explicit list of inputs whose behaviour must not change. |
| I2 | **Lazy imports.** Optional deps never imported at module level. | Discovery must not import `litellm` or any runtime SDK at import time. |
| I3 | **Safe defaults.** New features are opt-in. | Discovery must not fire unless the model spec is `"local"` or unset. Never probe the network on a fully-specified config. |
| I4 | **Deterministic tests.** No dependence on timing or external state. | Every test must pass with **no server running**. Live-server tests go behind an explicit marker and never run in the default suite. |
| I5 | **Protocol-driven core.** No heavy implementations in core. | `local/` returns dataclasses. It performs no chat calls, no retry, no request mutation. |
| I6 | **`local/` is a dependency sink.** | It may import the **standard library only** — nothing from `praisonaiagents`, and no third-party distribution (`httpx`/`requests`/`aiohttp` are forbidden; use `urllib.request`). Enforced by a test. See §5 and `07` §3. |
| I7 | **No second abstraction.** | `llm/adapters/` is the extension point. Do not add a parallel quirk/adapter registry beside it. |
| I8 | **No new public knobs without a live consumer.** | Root `AGENTS.md`: do not add params, modules or exports that merely duplicate existing behaviour. |

### I6 in detail — the import rule

An AST pass over `praisonaiagents/` (595 files, 238,936 lines) found **65 subpackages, 212
directed edges and 26 mutually-importing subpackage pairs**. `llm/` already imports upward
into `agent/`, and 15 subpackages import `llm/` back. Consequently a shared helper placed in
`llm/` **cannot** be adopted by `memory/` or `eval/` without deepening the existing cycles.

`local/` is therefore specified as a leaf. That single property is what allows the 21
modules which currently bypass the LLM layer to adopt it later. Treat any import of
`praisonaiagents.*` from inside `local/` as a build break, not a style issue.

The HTTP client is stdlib `urllib.request`, **not** `httpx`. An earlier draft of this ledger
permitted `httpx` on the grounds that it is a transitive dependency of `openai>=2.0.0`. That
was reversed in `07` §3: the edge is undeclared in `pyproject.toml`, so a future `openai`
release that drops `httpx` would silently break the sink — precisely the class of failure this
package exists to catalogue. The boundary test in §5 hard-forbids `httpx`/`requests`/`aiohttp`
so the decision cannot drift.

---

## 3. File ownership — collision avoidance

Two work orders that touch the same file **must not run concurrently**. This table is the
authority. Before starting, check that no in-flight PR owns your files.

| Work order | Owns (may edit) | Must not edit |
|---|---|---|
| `01-d1-default-model` | `agent/agent.py` (branch chain only) | `llm/llm.py`, `llm/adapters/` |
| `02-d3-provider-detection` | `llm/llm.py` (`_detect_provider`, `_is_ollama_provider` only) | `agent/agent.py`, `llm/adapters/` |
| `03-d2-base-url-routing` | `agent/agent.py` (base_url branch), root `README.md` | `llm/llm.py`, `llm/adapters/` |
| `04-test-gating` | `tests/_pytest_plugins/test_gating.py`, both `pytest.ini`, `tests/conftest.py`, `tests/integration/test_base_url_api_base_fix.py`, `tests/unit/cli/test_test_command.py` | any `praisonaiagents/` source; **`.github/workflows/**` — the `-m` expressions are not the bug** |
| `05-live-ci-job` | `.github/workflows/test-optimized.yml`, `tests/integration/test_ollama_tool_calling_live.py` | any `praisonaiagents/` source; `test_gating.py` |
| `06-adapter-revival` | `llm/adapters/__init__.py`, `llm/llm.py` (3 response paths) | `agent/agent.py` |
| `07-local-package` | `praisonaiagents/local/**` (new), `src/praisonai/tests/unit/llm/local/**` (new), `pyproject.toml` extras | everything else |
| `08-reachability` | `memory/`, `eval/`, `context/`, `lite/`, `telemetry/` | `llm/`, `agent/` |

### Enforced serialisation

- **`01` then `03`** — both edit `agent/agent.py`. Land `01` first.
- **`02` then `06`** — both edit `llm/llm.py`. Land `02` first; it is far smaller.
- **`04` then `05`** — before `04`, `-m provider_ollama` selects 32 tests across 5 files (only 7
  are Ollama tests), so `05` has no usable selector and is unbuildable.
- **`04` and `07` are independent** of orders 01/02/03/06 and may run in parallel with them.
- **`08` requires `07`** to have landed, because it consumes `local/`.

---

## 4. Status

Update your row in the same commit as your change. One line only.

Additional PRs not in the original order list, found while executing it:
D4 (local route prefixes) #4798, D5 (local embedding dimensions) #4802,
D6 (registry accepts local providers) #4800.

**Three claims in this ledger were corrected by executing it.** Each is marked
inline where it appears, but they are collected here because a reader who trusts
the summary would otherwise carry the wrong version:

1. *"Wire the twelve dead adapter methods."* Measurement said the opposite:
   **12 of 20 items should be deleted, only 3 wired** (`06` §1). Six had no
   inline equivalent at all — an agent told to wire them would have invented
   behaviour no test could fail against.
2. *"`provider_ollama` deselects the mocked base_url suite."* It does not.
   **`not network` deselects it on its own**, because the plugin implies
   `network` from any provider marker (`04` §1). Editing the workflow `-m`
   strings would have changed nothing.
3. *"Running fully locally is unachievable, not merely unconfigured."* Not so:
   litellm and the openai SDK both honour `OPENAI_BASE_URL`, so the bypass sites
   **do** reach a local server. The blocker is the hardcoded model name they then
   ask for (`00` §5, `08`).

| Order | Title | Branch | PR | Status |
|---|---|---|---|---|
| 01 | D1 — provider-prefixed default model never reaches litellm | `fix/d1-default-provider-model` | #4795 | PR open |
| 02 | D3 — provider over-detection from base_url | `fix/d3-provider-detection` | #4797 | PR open |
| 03 | D2 — README recipe + local-endpoint diagnostic | `fix/d2-base-url-routing` | #4799 | PR open |
| 04 | D7 — per-file provider marker deselects unrelated tests | `fix/d7-per-test-provider-markers` | #4801 | PR open |
| 05 | Live local-model CI job | `feat/ci-ollama-live-job` | #4803 | PR open |
| 06 | A1/A2 — make the provider adapter load-bearing (6 sub-steps) | 6 branches, stacked | #4804 #4806 #4808 #4809 #4810 #4811 | **complete — KNOWN_DEAD empty** |
| 07 | `praisonaiagents/local/` — discovery and capability resolver | `feat/local-model-resolver` | #4807 | PR open |
| 08 | A3 — auxiliary-model fallback configurable everywhere | `fix/reachability-local-endpoint` | #4812 | PR open (model half; parameter half deferred) |

---

## 5. The two tests that keep this work honest

Both are cheap, both are anti-regression, and both should land with their respective orders.

**Import boundary (`07`).** Asserts `local/` imports nothing from `praisonaiagents`. Without
it, I6 decays silently and the leaf property — the whole reason the package can be adopted
by `memory/` and `eval/` — is lost.

**Adapter reachability (`06`).** Asserts every method on `DefaultAdapter` has at least one
call site. This is the test whose absence allowed 11 of 17 adapter methods to become dead code
while `llm.py` grew 145 hand-written Ollama references. Two limits, both real: it cannot detect
an *unreachable* call site (proven by `should_skip_streaming_with_tools`, which a caller would
have satisfied while the branch stayed dead), and **one call site satisfies it — so it does not
detect the three-path divergence at all.** A floor, not a ceiling.

---

## 6. Deliberately out of scope

Named here so that deferring them is a decision rather than an oversight. Do not let a work
order quietly grow into one of these.

| Deferred | Measured size | Why not now |
|---|---|---|
| Consolidating `LLM` and `OpenAIClient` behind one protocol | 7,160 + 2,691 lines, selected by one boolean at 6 sites | Neither is a superset of the other; the merge is larger than every order in this ledger combined. |
| Decomposing `LLM.get_response` | 1,675 lines, 194 branch/loop/try nodes | Highest-risk file in the package. Order `06` must edit it surgically without reflowing it. |
| Removing the sync/async divergence | ~1,628 duplicated lines across 10 pairs; `get_response` vs `_async` only 22.3% similar | Requires the consolidation above to be worth doing. |

The one obligation this ledger accepts toward them: **do not make them worse.** No order may
add a fifth copy of any compensation, and no order may add new logic inside `get_response`
that is not a delegation to an adapter.
