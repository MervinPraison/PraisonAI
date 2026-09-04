# 06 — A1/A2: make the provider adapter load-bearing

**Measured against:** `origin/main` @ `2591aa405`, 2026-09-03, live Ollama 0.33.2 on
`127.0.0.1:11434`, model `qwen3:0.6b`.
**Blocked by:** order `02-d3-provider-detection` (both edit `llm/llm.py`; land 02 first).
**Owns:** `llm/adapters/__init__.py`, `llm/protocols.py` (`LLMProviderAdapterProtocol` only),
`llm/llm.py` (the three response paths), new tests under `src/praisonai/tests/unit/llm/`.
**Must not edit:** `agent/agent.py`, `llm/llm.py:_detect_provider`,
`llm/llm.py:_is_ollama_provider` (order 02), `tests/_pytest_plugins/test_gating.py`,
`.github/workflows/**` (orders 04 and 05).

> **This order overturns the ledger's first framing.** The README originally said "wire the
> twelve dead methods". Measurement says otherwise: **12 of 20 items should be DELETED**, only
> **3 wired**. Six of the deletions have no inline equivalent anywhere — they are pure
> speculative API, and an agent told to "wire up the adapter" would *invent* an implementation
> with no test that could ever have failed. That is the specific failure §1.1 exists to prevent.

---

## 1. Decision table — the deliverable

`DefaultAdapter` declares **17 methods** (not 18 — see §2.1). With the module-level hook
`add_provider_adapter` and two module functions, that is the 20 items below. Six methods are
live; eleven are dead.

| # | Item | `DefaultAdapter` returns | Overridden by | Live calls | Inline equivalent in `llm.py` | **Decision** | Justification |
|---|---|---|---|---|---|---|---|
| 1 | `supports_prompt_caching()` | `False` | Anthropic→`True` | 1 — `llm.py:1533` | none (adapter *is* the impl) | **LEAVE** | Already the single source of truth. |
| 2 | `should_summarize_tools(iter)` | `iter >= 5` | Ollama→`>= 1` | 1 — `llm.py:1992` | none | **LEAVE** | Live, pinned by an existing test. |
| 3 | `format_tools(tools)` | identity | Gemini→wraps internal tools | **0** | `llm.py:2449-2457` — **opposite shape** (inline passes internal tools through unwrapped; adapter wraps in `{'type':'function','function':tool}`) | **DELETE** | Wiring it would change what Gemini receives. Adapter version untested against a real Gemini request. |
| 4 | `post_tool_iteration(state)` | `pass` | Ollama→sets `state['needs_summary']` | **0** | `llm.py:3572-3579` (sync), `5170-5177` (async) | **DELETE** | Sets a flag no code reads. The real behaviour is *append a message and `continue`* — not expressible through a `None`-returning state mutator. |
| 5 | `supports_structured_output()` | `False` | Anthropic, Gemini→`True` | **0** | `model_capabilities.supports_structured_outputs(model)` at `llm.py:2293, 6090, 6399` | **DELETE** | A working, litellm-backed, per-*model* implementation is already live. The adapter's per-*provider* boolean is a strictly worse duplicate. |
| 6 | `supports_streaming()` | `True` | Anthropic→`False` | 2 — `llm.py:5075, 5360` | none | **LEAVE** | Live, but async-only **by design** — see §5.10. Do not widen it. |
| 7 | `supports_streaming_with_tools()` | `True` | Ollama/Anthropic/Gemini→`False` | 1 — `llm.py:2172`, consumed by all three paths | none | **LEAVE** | The one adapter method genuinely load-bearing today. |
| 8 | `get_streaming_adapter()` | `get_streaming_adapter("default")` | all three override | **0** | **none** | **DELETE** | Pure speculative API. It is the *only* production reference to `llm/streaming_protocol.py` (387 lines) — that whole module is reachable from nothing else. See §7. |
| 9 | `get_max_iteration_threshold()` | `10` | Ollama→`1` | **0** | `OLLAMA_SUMMARY_ITERATION_THRESHOLD = 1` (`llm.py:273`), used at `3821`, `5446` | **DELETE** | Duplicates #2 under a different name with no consumer. Wiring it would change the threshold from 1 to 10 for every non-Ollama provider — a behaviour change, not a refactor. |
| 10 | `format_tool_result_message(fn, result, id)` | OpenAI `role:tool` | Ollama→natural-language `role:user` | 1 — `llm.py:1712` (Ollama branch only) | **default branch inlined 3×**: `3773-3785` (sync), `5278-5290` (async), `6793-6807` (`_create_tool_message`, stream) | **WIRE** | Its default body has zero consumers, so aligning it with the three copies is unobservable — then all three collapse to one call. Step 06.3. |
| 11 | `handle_empty_response_with_tools(state)` | `False` | Ollama→`iter>=1 and results and not text` | **0** | `llm.py:3844-3845` (sync), `5467-5468` (async) — **exact predicate match** | **WIRE** | The one dead method whose inline equivalent matches its signature exactly, in two paths. Step 06.4. |
| 12 | `get_default_settings()` | `{}` | Ollama→`{max_tool_repairs:2, force_tool_usage:'auto'}` | 1 — `llm.py:690` | none | **LEAVE** | Live — and it is *why* A2 is a silent failure: it sets knobs two of three paths ignore (§5.3). |
| 13 | `parse_tool_calls(raw)` | `raw["choices"][0]["message"].get("tool_calls")` | none | **0** | `llm.py:3465` (dict), `4591` (`getattr` on object), `5146`, `5378` | **DELETE** | The `Dict[str, Any]` signature cannot express the litellm `ModelResponse` object that `4591` actually receives. Wiring requires changing the signature — i.e. inventing API. No provider overrides it, so there is no divergence to abstract. |
| 14 | `should_skip_streaming_with_tools()` | `False` | Gemini→`True` | **0** | `llm.py:3122-3124` (sync only) — **and that branch is unreachable** | **DELETE** | `GeminiAdapter.supports_streaming_with_tools()` is already `False`, so `llm.py:3117` sets `use_streaming = False` before `3122` is evaluated. Delete the method *and* the dead branch. |
| 15 | `recover_tool_calls_from_text(text, tools)` | `None` | Ollama→JSON parse | **0** | `llm.py:3468-3500` (sync only) | **WIRE** | A1's flagship duplicate: 33 inline lines vs 30 adapter lines doing the same job. Highest value, hence last. Step 06.5. |
| 16 | `inject_cache_control(messages)` | identity | **none — not even `AnthropicAdapter`** | **0** | `llm.py:2312-2326` + four helpers at `2191/2205/2233/2244` | **DELETE** | A stub with no implementation anywhere. The real behaviour needs a 4-breakpoint budget and a history index; a flat `messages -> messages` signature carries neither. |
| 17 | `extract_reasoning_tokens(response)` | `0` | **none** | **0** | `llm.py:5807-5810` inside `_track_token_usage` | **DELETE** | No provider overrides it and none needs to — `_usage_value`/`_detail_value` already handle every shape litellm returns. |
| 18 | `add_provider_adapter(name, adapter)` *(module fn)* | registers into `_provider_adapters` | — | **0** anywhere incl. tests/docs | none | **LEAVE — hand off to order 02** | A registered name is **unreachable**: the sole caller `get_provider_adapter` (`llm.py:682`) is only ever passed `_detect_provider()`'s output, which can be exactly `ollama\|anthropic\|gemini\|openai\|default`. Fixing it is a 3-line change in a region order 02 owns. |
| 19 | `list_provider_adapters()` *(module fn)* | sorted keys | — | **0** anywhere | none | **DELETE** | Exported, undocumented, zero consumers including tests. |
| 20 | `has_provider_adapter(name)` *(module fn)* | `name in _provider_adapters` | — | **0** anywhere | none | **DELETE** | Same — plus it is *wrong*: no `.lower()`, so `has_provider_adapter("Ollama")` is `False` while `get_provider_adapter("Ollama")` succeeds. Untested dead code with a latent bug. |

**Totals: 4 LEAVE, 1 LEAVE-and-hand-off, 12 DELETE, 3 WIRE.**

### 1.1 Why "no inline equivalent" is the decisive column

Six of the twelve deletions have **no inline equivalent at all** — nothing in `llm.py` does the
job they declare: `get_streaming_adapter`, `inject_cache_control`, `extract_reasoning_tokens`,
`add_provider_adapter`, `list_provider_adapters`, `has_provider_adapter`.

These are **pure speculative API**. There is no behaviour to move into them. An agent handed
"wire up the adapter" without this column will invent an implementation, and that invented code
will have no test that could ever have failed.

The other six deletions have an inline equivalent that is **incompatible** (different output
shape: #3; different type signature: #13), **strictly worse** (#5, #9), **unreachable** (#14),
or **not expressible through the declared signature** (#4). Wiring any of them is a behaviour
change wearing a refactor's clothes.

---

## 2. Measurement corrections

Method: `ast` walk of `llm.py` for function extents and node counts; repo-wide `grep` for call
sites, re-run receiver-aware (§6) to eliminate same-name false positives;
`difflib.SequenceMatcher` on function source slices.

**Confirmed exactly:** `adapters/__init__.py` 340 lines; `llm.py` 7,160; `get_response` at
`2557`, 1,675 lines, **194** branch nodes; `get_response_stream` at `4233`, 443 lines, **56**;
`get_response_async` at `4706`, 969 lines; similarity 22.3% vs 75.6/77.8/84.4/90.5% for the
other four pairs; Ollama references `llm.py` **145 lines** / 154 occurrences,
`adapters/__init__.py` **19 lines** / 20; all 20 call-site counts as listed; the
`recover_tool_calls_from_text` duplicate at `3468-3500` vs `160-189`.

**Five corrections:**

| # | Claim | Measured | Note |
|---|---|---|---|
| 2.1 | "`DefaultAdapter` defines 18 methods" | **17 methods** | The 18th listed item, `add_provider_adapter`, is a module-level function. `LLMProviderAdapterProtocol` declares only **16** — it omits `get_streaming_adapter`, so that method is not even part of the protocol it claims to implement. |
| 2.2 | `get_response_async` = 109 branch nodes | **115** under the metric that yields 194 and 56 for the other two; **112** excluding `ExceptHandler` | 109 matches neither metric. Correct `00-ground-truth.md`. |
| 2.3 | `max_tool_repairs`: 2 in `get_response` | **2 lines, 3 occurrences** (`3583`×2, `3599`×1) | The original table mixes line counts and occurrence counts. |
| 2.4 | `_format_ollama_tool_result_message`: 1 / 1 / **0** | 1 / 1 / **1 (indirect)** | The stream path reaches it via `_create_tool_message` (`6791-6792`), called at `4489`, `4497`, `4661`. **The stream path is not missing Ollama tool-result formatting** — the original table overstates the gap. |
| 2.5 | Seven compensations diverge | **Sixteen** | Nine further asymmetries, three of which run *against* the sync path. §2.6. |

### 2.6 Complete compensation matrix (line hits per path)

```
                                        sync    async   stream    lines
                                       1675 L   969 L    443 L
tool_result_mapping                       8       0        0      3649,3682,3685,3687,3688,3728,3733,3735
max_tool_repairs                          2       0        0      3583,3599
_validate_tool_call                       1       0        0      3587
TOOL_CALL_REPAIR_PROMPT                   1       0        0      3595
_should_force_tool_usage                  1       0        0      3561
FORCE_TOOL_USAGE_PROMPT                   1       0        0      3563
_supports_xml_tool_format (XML recovery)  1       0        0      3506
json.loads(response_text) (JSON recovery) 1       0        0      3472
OLLAMA_FINAL_ANSWER_PROMPT                0       1        0      -    / 5302 / -      <- async-only
_register_deferred_if_any                 1       0        1      2918 / -    / 4461   <- async-only gap
OLLAMA_TOOL_USAGE_PROMPT                  1       1        0      3576 / 5174 / -
_validate_and_filter_ollama_arguments     1       1        0      3690 / 5240 / -
_generate_ollama_tool_summary             1       1        0      3847 / 5470 / -
_handle_ollama_sequential_logic           1       1        0      3813 / 5438 / -
OLLAMA_SUMMARY_ITERATION_THRESHOLD        1       1        0      3821 / 5446 / -
_manage_context_in_loop                   1       1        0      2751 / 4882 / -
_finalise_on_limit                        2       2        0      2971,3828 / 5008,5453 / -
_format_ollama_tool_result_message        1       1        1*     3762 / 5267 / via _create_tool_message
```

`*` indirect — correction 2.4.

### 2.7 The divergence is observable — and not in the direction assumed

> **CORRECTED 2026-09-03, during step 06.4.** The original figures in this section
> recorded the sync path returning `'{\n\n\n}'` with 1 tool call. **That does not
> reproduce.** Re-measured on `origin/main`, twice, `temperature=0`, same prompt and
> tool, the sync path returns 2 tool calls and a doubled answer. The stream result
> reproduced exactly. Every branch of the 06.1–06.6 stack was then bisected against
> `main` and all produce byte-identical output, confirming the stack is
> refactor-only.
>
> **The headline finding stands** — the three paths disagree and the stream path is
> broken. Only the specific `'{\n\n\n}'` sample was unreproducible. Do not cite it,
> and do not treat it as a regression signal.

Live Ollama, `temperature=0`, identical prompt and tool, two trials (corrected):

```
T1 sync    calls=2   out='Paris: 21C sunny. Paris: 21C sunny.'
T1 async   calls=1   out='Paris: 21C sunny'
T1 stream  calls=10  out=''
T2 sync    calls=2   out='Paris: 21C sunny. Paris: 21C sunny.'
T2 async   calls=1   out='Paris: 21C sunny'
T2 stream  calls=10  out=''
```

Reproduce:

```bash
cd src/praisonai-agents && python3 - <<'EOF'
import sys, os, asyncio; sys.path.insert(0,'.'); os.environ.setdefault('OPENAI_API_KEY','x')
from praisonaiagents.llm.llm import LLM
def get_weather(city: str) -> str:
    """Get the weather for a city."""
    return f"{city}: 21C sunny"
P = "What is the weather in Paris? Use the tool."
for path in ("sync","async","stream"):
    calls=[]
    def exec_tool(name,args,**kw): calls.append(name); return get_weather(**args)
    llm=LLM(model="ollama/qwen3:0.6b", base_url="http://127.0.0.1:11434")
    if path=="sync":     out=llm.get_response(prompt=P,tools=[get_weather],execute_tool_fn=exec_tool,temperature=0)
    elif path=="async":  out=asyncio.run(llm.get_response_async(prompt=P,tools=[get_weather],execute_tool_fn=exec_tool,temperature=0))
    else:                out="".join(str(c) for c in llm.get_response_stream(prompt=P,tools=[get_weather],execute_tool_fn=exec_tool,temperature=0))
    print(f"### {path:6} tool_calls={len(calls)} out={out!r}")
EOF
```

Three consequences, and they reframe the order:

1. **The best-compensated path produces the worst answer.** `get_response` has 16 of the 18
   compensations and calls the tool twice, returning a doubled answer.
   `get_response_async` has 8 and returns the correct answer once. More compensation is
   not the goal; *the same* compensation is.
2. **The stream path is not under-compensated, it is broken.** It burns all 10 iterations of
   `max_iter`, invokes the tool **10 times** for a one-tool question, and yields nothing. That
   is a real cost and side-effect amplifier, not a formatting defect.
3. **Leading hypothesis for the sync/async split: `OLLAMA_FINAL_ANSWER_PROMPT`**
   (`llm.py:5302`, async only). Async appends *"Based on the tool results above, please provide
   the final answer"* and re-requests; sync does not, so it runs another tool iteration
   instead and concatenates the result twice. **This is a hypothesis, not a measurement**,
   and it was not settled during order 06 — the corrected baseline changed what needs
   explaining. Whoever takes the §5.7 follow-up should settle it first.

**None of the three baselines may change during Steps 06.1–06.6.** Every step is a
behaviour-preserving refactor. `'{\n\n\n}'` stays `'{\n\n\n}'`. Fixing it is this order's
*successor*, and it needs these characterization tests to be safe.

---

## 3. Preconditions for every step

```bash
# 1. Order 02 must have landed.
git log --oneline origin/main | head -20 | grep -i "provider.detection\|_detect_provider"

# 2. Branch from origin/main, never from a sibling order's branch.
git fetch origin main && git worktree add /path/to/wt-06 -b <step-branch> origin/main

# 3. Ollama up, correct model present.
curl -s 127.0.0.1:11434/api/version                                  # {"version":"0.33.2"}
curl -s 127.0.0.1:11434/api/show -d '{"model":"qwen3:0.6b"}' | \
  python3 -c 'import json,sys; print(json.load(sys.stdin)["capabilities"])'
                                                # ['completion','tools','thinking']

# 4. Green baseline on the two suites this order can break.
cd src/praisonai-agents && PYTHONPATH=. python -m pytest tests/unit/test_adapter_registry.py -q  # 38 passed
cd src/praisonai && PYTHONPATH=../praisonai-agents python -m pytest tests/unit/llm/ -q
```

### 3.1 Three test-infrastructure traps

**Trap A — `src/praisonai-agents/tests/` is almost entirely outside CI.** Grepping every
workflow: the only tests run from that directory are `tests/smoke/test_subscription_auth.py`
and `tests/unit/auth/test_agent_auth_wiring.py` (`test-optimized.yml:110-113`).
**`tests/unit/test_adapter_registry.py` (38 tests) and all 13 files in `tests/unit/llm/` are run
by no workflow at all.** Consequences:

- Deleting `GeminiAdapter.format_tools` breaks
  `test_adapter_registry.py::test_gemini_adapter_formats_internal_tools` and **no CI job will
  tell you**. Run that file by hand in every step.
- **All new tests in this order go to `src/praisonai/tests/unit/llm/`**, which *is* run — by
  `test-core.yml` (`subdirs` shard) and `test-optimized.yml` (main job).
- Do not fix the CI gap here; `.github/workflows/**` belongs to orders 04 and 05. §7 hands it over.

**Trap B — `test_ollama_tool_reliability.py` tests a copy, not the product.**
`src/praisonai/tests/unit/llm/test_ollama_tool_reliability.py` (541 lines, 28 tests, all green)
defines `class MockLLM` which *re-implements* `_is_ollama_provider`, `_apply_ollama_defaults`,
`_validate_tool_call`, `_should_force_tool_usage` and both prompt templates. Its own docstring
says *"copied from actual LLM class"*. **It cannot fail in response to any change in `llm.py`.**
Do not treat it as a safety net and do not extend it. Every characterization test in this order
instantiates the real `praisonaiagents.llm.llm.LLM`.

**Trap C — the auto provider-marker does not apply under `tests/unit/`.** `test_gating.py:214`
guards provider auto-detection with `if item.fspath and test_type != 'unit'`. So a file under
`tests/unit/llm/` mentioning "ollama" is *not* auto-gated and **will** run in CI. Live-server
tests therefore need an **explicit** `pytestmark`; verified that the CI marker expression then
deselects them (`1 collected / 1 deselected`).

---

## 4. The WIRE sequence

Six steps, each one branch, one commit, one adapter method, independently revertible. Lowest
risk first.

### Step 06.0 — record the `OLLAMA_FINAL_ANSWER_PROMPT` experiment (no ship)

Branch: none. Deliverable: one row appended to `00-ground-truth.md` recording whether adding the
async-only final-answer append at `llm.py:3838` changes the sync path's `'{\n\n\n}'`. Revert the
local patch with `git checkout --`. This exists so the successor order need not re-derive it.

### Step 06.1 — the reachability ratchet (test only, zero source change)

**Branch:** `test/adapter-reachability-ratchet`
**Source changes:** none. If your diff touches `praisonaiagents/`, you are on the wrong step.

Add `src/praisonai/tests/unit/llm/test_llm_adapter_seam.py` — full text in §6. It carries a
`KNOWN_DEAD` frozenset seeded with exactly the eleven names measured today. Later steps delete
names from that set; the set never grows.

**Verify:**
```bash
cd src/praisonai && PYTHONPATH=../praisonai-agents python -m pytest \
  tests/unit/llm/test_llm_adapter_seam.py -q            # expect 4 passed
```
Then prove the ratchet bites — temporarily drop one name from `KNOWN_DEAD` and confirm
`test_no_new_dead_adapter_methods` fails. **A ratchet you have not seen fail is not a ratchet.**

**Rollback:** `git revert <sha>` — deletes one test file.

### Step 06.2 — delete the twelve speculative surfaces

**Branch:** `refactor/delete-dead-adapter-surface`

**Delete from `llm/adapters/__init__.py`:**

| Lines | What |
|---|---|
| `26-27` | `DefaultAdapter.format_tools` |
| `29-30` | `DefaultAdapter.post_tool_iteration` |
| `32-33` | `DefaultAdapter.supports_structured_output` |
| `41-44` | `DefaultAdapter.get_streaming_adapter` |
| `46-47` | `DefaultAdapter.get_max_iteration_threshold` |
| `68-73` | `DefaultAdapter.parse_tool_calls` |
| `75-76` | `DefaultAdapter.should_skip_streaming_with_tools` |
| `81-82` | `DefaultAdapter.inject_cache_control` |
| `84-85` | `DefaultAdapter.extract_reasoning_tokens` |
| `108-110` | `OllamaAdapter.get_streaming_adapter` |
| `112-113` | `OllamaAdapter.get_max_iteration_threshold` |
| `191-197` | `OllamaAdapter.post_tool_iteration` |
| `212-213` | `AnthropicAdapter.supports_structured_output` |
| `223-225` | `AnthropicAdapter.get_streaming_adapter` |
| `238-240` | `GeminiAdapter.should_skip_streaming_with_tools` |
| `242-243` | `GeminiAdapter.supports_structured_output` |
| `245-258` | `GeminiAdapter.format_tools` |
| `264-266` | `GeminiAdapter.get_streaming_adapter` |
| `321-328` | `list_provider_adapters`, `has_provider_adapter` |
| `13` | `from ..streaming_protocol import ...` — now unused |
| `12` | `from ..model_capabilities import GEMINI_INTERNAL_TOOLS` — now unused |
| `338-339` | the two `__all__` entries |

**Keep** `add_provider_adapter` and its `__all__` entry (§7 hands it to order 02).

**Delete from `llm/protocols.py`** the matching stubs: `294-296`, `298-300`, `302-304`,
`314-316`, `330-332`, `334-336`, `342-344`, `346-348`. Also strip the
`format_tools`/`post_tool_iteration` lines from the class docstring example at `276-282`, which
would otherwise document deleted API.

`LLMProviderAdapterProtocol` is `@runtime_checkable`, so `isinstance` only checks method
presence — deleting a name from both the protocol and `DefaultAdapter` keeps the two
`..._implements_protocol` tests green.

**Delete the one unreachable inline branch** in `llm/llm.py`, verbatim:

```python
3120:                        
3121:                        # Gemini has issues with streaming + tools, disable streaming for Gemini when tools are present
3122:                        if use_streaming and formatted_tools and self._is_gemini_model():
3123:                            logging.debug("Disabling streaming for Gemini model with tools due to JSON parsing issues")
3124:                            use_streaming = False
3125:                        
```

Replace `3120-3125` with a single blank line. **Proof it is unreachable** — three lines above:

```python
3116:                        use_streaming = stream
3117:                        if formatted_tools and not self._supports_streaming_tools():
3118:                            # Provider doesn't support streaming with tools, use non-streaming
3119:                            use_streaming = False
```

`_supports_streaming_tools()` returns `self._provider_adapter.supports_streaming_with_tools()`
(`llm.py:2172`), which `GeminiAdapter` overrides to `False`. So for Gemini-with-tools, `3119`
already sets `use_streaming = False` and the `3122` guard can never be true. Verified:

```
$ python3 -c "from praisonaiagents.llm.adapters import get_provider_adapter as g; \
  print(g('gemini/gemini-2.0-flash').supports_streaming_with_tools())"
False
```

`get_response_async` and `get_response_stream` have no equivalent branch. One-path edit, so §8's
two-path rule does not apply.

**Also update `KNOWN_DEAD`**: remove the nine deleted method names, leaving
`{"handle_empty_response_with_tools", "recover_tool_calls_from_text"}`.

**Non-Ollama behaviour identical**, asserted three ways: (1) Step 06.1's
`test_no_dead_name_is_actually_live` proves every deleted name had zero call sites; (2) new test
`test_gemini_with_tools_never_streams` pins the deletion at the level of the surviving guard;
(3) `test_adapter_registry.py` must still pass with **one deletion** —
`test_gemini_adapter_formats_internal_tools` (lines `347-363`) tests `GeminiAdapter.format_tools`
and must be removed in the same commit. That is the only test in the repo exercising any deleted
surface (verified by repo-wide `grep` for each of the twelve names).

**Characterization tests first**, in
`src/praisonai/tests/unit/llm/test_llm_response_path_characterization.py`:
- `test_gemini_with_tools_never_streams` — assert `_supports_streaming_tools()` is `False` and
  `_is_gemini_model()` is `True`; assert the value of `_supports_streaming_tools()` for every
  `(model, tools_present)` in `{gemini, gpt-4o, ollama/qwen3:0.6b} × {True, False}` matches a
  hard-coded expectation table.
- `test_deleted_adapter_names_are_absent` — `not hasattr(DefaultAdapter, name)` for each of the
  nine, so a later merge cannot silently resurrect them.

**Verify live:** run the §2.7 script. All three outputs byte-identical to baseline
(`'{\n\n\n}'`, `'Paris: 21C sunny'`, `''`), stream tool-call count still 10. A change means you
deleted something live.

**Rollback:** `git revert <sha>`. Pure deletion, no state, no migration.

### Step 06.3 — WIRE `format_tool_result_message` for the default branch

**Branch:** `refactor/wire-default-tool-result-message`

**Why safe:** `DefaultAdapter.format_tool_result_message`'s body currently has **zero**
consumers. `llm.py:1712` is reached only through `_format_ollama_tool_result_message`, whose
call sites are guarded by `_is_ollama_provider()` and which forces an `OllamaAdapter` if
`_provider_adapter` is something else. So the default body can be rewritten to match the three
inline copies with no observable change.

The three inline copies to be replaced are at `llm.py:3770-3785` (sync), `5275-5290` (async),
and `6791-6807` (`_create_tool_message`, the stream path's formatter). All three implement the
same cascade: `None` → `"Function returned an empty output"`; a dict with `'error'` → an error
sentence; a list whose first element has `'error'` → the same; otherwise `json.dumps`. Path 3
differs in one respect — it wraps `json.dumps` in `try/except (TypeError, ValueError)` and falls
back to `str(result)`.

**Replacement.** Give `DefaultAdapter.format_tool_result_message` the union body, adopting path
3's guard (strictly safer — paths 1 and 2 raise on a non-serializable result):

```python
    def format_tool_result_message(self, function_name: str, tool_result: Any, tool_call_id: Optional[str] = None) -> Dict[str, Any]:
        # Standard OpenAI-style tool result message.
        if tool_result is None:
            content = "Function returned an empty output"
        elif isinstance(tool_result, dict) and 'error' in tool_result:
            content = (f"Error: {tool_result.get('error', 'Unknown error')}. "
                       "Please inform the user that the operation could not be completed.")
        elif (isinstance(tool_result, list) and tool_result
                and isinstance(tool_result[0], dict) and 'error' in tool_result[0]):
            content = (f"Error: {tool_result[0].get('error', 'Unknown error')}. "
                       "Please inform the user that the operation could not be completed.")
        else:
            try:
                content = json.dumps(tool_result)
            except (TypeError, ValueError):
                content = str(tool_result)
        message = {"role": "tool", "content": content}
        message["tool_call_id"] = tool_call_id if tool_call_id is not None else f"call_{function_name}"
        return message
```

(`import json` at module top of `adapters/__init__.py`; `OllamaAdapter.recover_tool_calls_from_text`
imports it function-locally at line 166 — leave that alone in this step.)

Then make `_create_tool_message` (`llm.py:6772`) the single formatter and delegate:

```python
        if is_ollama:
            return self._format_ollama_tool_result_message(function_name, result)
        adapter = getattr(self, '_provider_adapter', None)
        if adapter is None:
            from .adapters import DefaultAdapter
            adapter = DefaultAdapter()
        return adapter.format_tool_result_message(function_name, result, tool_call_id)
```

and replace `3770-3785` with

```python
                            else:
                                messages.append(self._create_tool_message(
                                    function_name, tool_result, tool_call_id, is_ollama=False))
```

and `5275-5290` with the same at async indentation. Path 3 needs no call-site change — it *is*
`_create_tool_message`.

**This edits two of the three response paths, so §8's rule applies:** the commit must carry
`test_tool_result_message_identical_across_paths`, parametrized over all three. Without it,
split into two commits (sync first, async second), each with a path-specific test.

**Tests, written and passing against `main` first:**
- `test_default_tool_result_message_matches_legacy_shape` — nine `tool_result` fixtures
  (`None`, `{}`, `{"error": "x"}`, `[{"error":"y"}]`, `[]`, `"str"`, `3`, `{"a":1}`, and a
  `set()` — the non-serializable case) × expected message dict, hard-coded from the *pre-change*
  inline bodies.
- `test_non_serializable_tool_result_no_longer_raises` — marked `xfail(strict=True)` on `main`.
  **This is a deliberate divergence:** for a `set()`, paths 1 and 2 previously raised
  `TypeError` and now produce `str(...)`. That is a bug fix, not a preservation. Call it out in
  the commit message so it appears as a test-outcome diff rather than a silent edit.
- `test_tool_result_message_identical_across_paths` — parametrized over `("sync","async","stream")`;
  patch `_completion_with_retry` / `_acompletion_with_retry` to return a canned tool call, then
  assert the `messages` list is **equal across all three paths** for a `DefaultAdapter` model.
  Fails on `main` for the `set()` fixture; passes after. That is the intended ratchet.

**Verify live:** §2.7 script must reproduce all three baselines exactly. Ollama takes the
`is_ollama` branch, so this step must not perturb it at all.

> **Trap when testing the non-Ollama path locally:** `_is_ollama_provider` (`llm.py:719`) matches
> `:11434` in `base_url`, so pointing at a local Ollama through the OpenAI-compatible route
> *still* yields `OllamaAdapter`. Use a proxy or a mocked transport. **Do not** work around it by
> editing `_is_ollama_provider` — that method belongs to order 02.

**Rollback:** `git revert <sha>`. Adapter body and three call sites revert together.

### Step 06.4 — WIRE `handle_empty_response_with_tools`

**Branch:** `refactor/wire-handle-empty-response-with-tools`

The only dead method whose signature already matches its inline predicate. Inline at
`llm.py:3842-3852` (sync) and `5465-5475` (async); `get_response_stream` has no equivalent (§5.5).

**Replace the predicate only** (lines `3844-3845` and `5467-5468`) with:

```python
                        if self._provider_adapter.handle_empty_response_with_tools({
                            'iteration_count': iteration_count,
                            'accumulated_tool_results': accumulated_tool_results,
                            'response_text': response_text or '',
                        }):
```

The body (`3846-3852` / `5469-5475`) stays exactly where it is, unreflowed. **Do not** move
`_generate_ollama_tool_summary` into the adapter in this step — it is 82 lines with a
`_format_search_results_summary` dependency and is shared by `_handle_ollama_sequential_logic`.
One method per step.

**Semantic equivalence — and the one real risk.** The current predicate leads with
`self._is_ollama_provider()`. After the change, Ollama-treatment is decided by *dispatch*:
`OllamaAdapter` returns the predicate, `DefaultAdapter` returns `False`. **That is not identical
to `_is_ollama_provider()`** — `_detect_provider` (`llm.py:640-671`) maps by route prefix and
base-url hints, and `get_provider_adapter` (`adapters:311`) additionally matches
`"ollama" in name_lower`. The union is *wider*: e.g. `model="my-ollama-model"` with no ollama
base-url gets `OllamaAdapter` while `_is_ollama_provider()` is `False`.

**Therefore this step must add the exact-equivalence assertion, or it is not behaviour-preserving:**

`test_ollama_adapter_selection_matches_is_ollama_provider` — parametrized over 14
model/base_url combinations (`ollama/llama3`, `ollama/qwen3:0.6b`, `my-ollama-model`,
`ollama_chat/llama3`, `llama3`+`base_url=...:11434`, `llama3`+`OPENAI_BASE_URL=...:11434`,
`gpt-4o`, `claude-3-5-sonnet`, `gemini/gemini-2.0-flash`, `bedrock/anthropic.claude-3`,
`vertex_ai/gemini-1.5-pro`, `openrouter/anthropic/claude-3`, `""`, `None`), asserting
`isinstance(llm._provider_adapter, OllamaAdapter) == llm._is_ollama_provider()`.

**Run it on `main` first.** If any row fails, that row is a pre-existing divergence and **this
step is blocked** until order 02 reconciles the two functions — record the failing rows in
`00-ground-truth.md` and stop. Do not paper over it by keeping `_is_ollama_provider()` in the
condition alongside the adapter call; that would leave the adapter non-load-bearing, which is
the whole defect.

**Characterization tests first**, `src/praisonai/tests/unit/llm/test_llm_empty_response_compensation.py`:
- `test_empty_response_after_tools_yields_summary_sync` / `..._async` — mocked completion:
  iteration 0 returns a tool call, iteration 1 returns `content=""`. Assert the returned string
  equals the `_generate_ollama_tool_summary` output.
- `test_whitespace_only_response_counts_as_empty` — iteration 1 returns `"   \n "`. Pins the
  `.strip()` semantics; the adapter's `state.get('response_text','').strip()` and the inline
  `response_text.strip() == ""` agree **only if `response_text` is never `None`** — hence the
  `response_text or ''` in the replacement.
- `test_non_empty_response_after_tools_returns_model_text` — iteration 1 returns `"{\n\n\n}"`.
  Must return `'{\n\n\n}'`. **This is the §2.7 sync baseline; it must not improve in this step.**
- `test_default_adapter_never_takes_empty_response_branch` — `gpt-4o`; patch
  `_generate_ollama_tool_summary` with a `Mock` and assert `not called`. The non-Ollama identity
  assertion.
- `test_iteration_zero_never_takes_branch` — empty response at iteration 0 must fall through to
  the `3572` tool-usage prompt, not the summary.

All six against `main` first, then committed **with** the refactor (they cover both edited paths).

**Update `KNOWN_DEAD`** → `{"recover_tool_calls_from_text"}`.

**Rollback:** `git revert <sha>`.

### Step 06.5 — WIRE `recover_tool_calls_from_text`

**Branch:** `refactor/wire-recover-tool-calls-from-text`
Highest value, highest risk, therefore last. Inline at `llm.py:3468-3500`, **sync only**.

**Replacement for all 33 lines:**

```python
                    # Recover tool calls the provider emitted as response text.
                    if not tool_calls and response_text and formatted_tools:
                        recovered = self._provider_adapter.recover_tool_calls_from_text(
                            response_text, formatted_tools)
                        if recovered:
                            tool_calls = recovered
                            logging.debug(f"Recovered tool calls from response text: {tool_calls}")
```

**Four measured behavioural deltas, each argued inert:**

| Delta | Inline | Adapter | Resolution |
|---|---|---|---|
| `id` format | `f"tool_{iteration_count}"` / `f"tool_{i}_{idx}"` | `f"call_{name}_{idx}_{hash(text)%10000}"` | **Inert for Ollama.** The id never reaches the model: the assistant turn omits `tool_calls` entirely for Ollama (`3633-3638`) and the tool reply is `role:"user"` with no `tool_call_id` (`3760-3762`). Pin with `test_recovered_tool_call_id_never_reaches_messages`. |
| List with no `"name"` entries | `[]` | `None` | Equivalent at every consumer: `3504` (`if not tool_calls and ...`) and `3623` (`if tool_calls and ...`) treat them alike, as does the replacement's `if recovered:`. Pin with `test_list_without_name_keys_does_not_dispatch`. |
| Exceptions caught | `(JSONDecodeError, KeyError)` | `(JSONDecodeError, TypeError, KeyError)` | Adapter is strictly wider — can only stop a failure, never cause one. Note in the commit message. |
| Guard | `_is_ollama_provider() and ...` | dispatch | Same widening as 06.4. **Reuse `test_ollama_adapter_selection_matches_is_ollama_provider` as a hard precondition** — do not land 06.5 unless it is green. |
| Debug logging | two distinct messages | none in adapter | The replacement logs one message at the call site, so the "recovery happened" signal survives. The single-vs-multiple distinction is lost; state that in the commit message. |

**Non-Ollama identity.** `DefaultAdapter`, `AnthropicAdapter` and `GeminiAdapter` all inherit
`recover_tool_calls_from_text -> None`, so no non-Ollama provider can enter the branch.
Asserted by `test_no_text_recovery_for_default_adapter` — `gpt-4o`, mocked response whose
`content` is exactly `'{"name": "get_weather", "arguments": {"city": "Paris"}}'` and whose
`tool_calls` is `None`. Assert `execute_tool_fn` is never called and the returned string is that
JSON text verbatim. **This test must pass identically on `main` and after** — it is the single
most important assertion in this step, because it is the one an over-eager wiring would break.
Parametrize for `claude-3-5-sonnet` and `gemini/gemini-2.0-flash` too.

**Characterization tests first**, `src/praisonai/tests/unit/llm/test_llm_text_tool_call_recovery.py`:

| Test | Input `content` | Asserted |
|---|---|---|
| `test_recovers_single_json_tool_call` | `'{"name":"get_weather","arguments":{"city":"Paris"}}'` | called once with `("get_weather", {"city":"Paris"})` |
| `test_recovers_multiple_json_tool_calls` | `'[{"name":"a","arguments":{}},{"name":"b","arguments":{}}]'` | called twice, in order |
| `test_dict_without_name_key_does_not_dispatch` | `'{"arguments":{"city":"Paris"}}'` | not called; text returned verbatim |
| `test_list_without_name_keys_does_not_dispatch` | `'[{"arguments":{}}]'` | not called |
| `test_malformed_json_does_not_dispatch` | `'{"name": "get_weather"'` | not called; no exception escapes |
| `test_empty_text_does_not_dispatch` | `''` | not called |
| `test_no_tools_means_no_recovery` | valid JSON call, `tools=None` | not called |
| `test_native_tool_calls_take_precedence` | valid JSON text **and** a native `tool_calls` naming `other_tool` | `other_tool` runs; text not parsed |
| `test_xml_recovery_still_reachable_after_json_recovery_fails` | `'<tool_call>{"name":"get_weather","arguments":{"city":"Paris"}}</tool_call>'`, Qwen model | dispatches via the XML block at `3502-3558` |
| `test_recovered_tool_call_id_never_reaches_messages` | valid JSON call | no appended message contains `tool_call_id` or `tool_calls` |
| `test_arguments_are_json_encoded_string` | `'{"name":"a","arguments":{"n":1}}'` | `function.arguments` is the **string** `'{"n": 1}'`, not a dict — what `_parse_tool_call_arguments` expects |

`test_xml_recovery_still_reachable_after_json_recovery_fails` is the guard for a subtle
interaction: the inline list branch sets `tool_calls = []` *before* recovery, and the XML block
at `3504` re-checks `if not tool_calls`. The replacement never assigns a falsy value, so the XML
path stays reachable — but only this test proves it.

**Update `KNOWN_DEAD`** → `frozenset()`, and change `test_no_new_dead_adapter_methods` to assert
the set is empty. Leave the allowlist mechanism in place (empty) so a future addition has an
obvious, reviewable place to be justified.

**Verify live — mandatory for this step**, because `qwen3:0.6b` emits JSON-as-text reliably at
`temperature=0`:

```bash
git checkout origin/main
for i in 1 2 3; do <§2.7 script>; done > /tmp/before.txt 2>&1
git checkout refactor/wire-recover-tool-calls-from-text
for i in 1 2 3; do <§2.7 script>; done > /tmp/after.txt 2>&1
diff <(grep '^### sync'   /tmp/before.txt) <(grep '^### sync'   /tmp/after.txt)
diff <(grep '^### async'  /tmp/before.txt) <(grep '^### async'  /tmp/after.txt)
diff <(grep '^### stream' /tmp/before.txt) <(grep '^### stream' /tmp/after.txt)
```

Expected: empty diffs. `tool_calls=1` on sync in particular — a change to `tool_calls=0` means
recovery stopped firing (the adapter is not being reached); a change in `out` means the id or
the `[]`/`None` delta was not as inert as measured.

Also run the server-free adapter equivalence check:
```bash
python3 -c "
from praisonaiagents.llm.adapters import OllamaAdapter
a = OllamaAdapter()
for txt in ['{\"name\":\"w\",\"arguments\":{\"c\":\"P\"}}',
            '[{\"name\":\"a\",\"arguments\":{}},{\"name\":\"b\",\"arguments\":{}}]',
            '{\"arguments\":{}}', '[{\"arguments\":{}}]', '{\"name\":\"w\"', '']:
    r = a.recover_tool_calls_from_text(txt, [{'name':'w'}])
    print(repr(txt)[:40], '->', [(c['function']['name'], c['function']['arguments']) for c in (r or [])])
"
```

**Rollback:** `git revert <sha>`. The 33 inline lines come back intact; `KNOWN_DEAD` must be
restored to `{"recover_tool_calls_from_text"}` in the same revert.

### Step 06.6 — port `_validate_and_filter_ollama_arguments` to the stream path

**Branch:** `fix/stream-path-ollama-argument-filtering`

The one A2 gap that belongs in *this* order rather than a follow-up, because it is
**pre-dispatch, provider-shaped and streaming-safe**: it runs before `execute_tool_fn`, so
nothing has been yielded that would need retracting.

Present at `3690` (sync) and `5240` (async); absent from both stream branches. Insert after
`llm.py:4433` (streaming branch) and after `4639` (fallback branch), mirroring `5238-5240`:

```python
                            # Validate and filter arguments for Ollama provider
                            if is_ollama and tools:
                                arguments = self._validate_and_filter_ollama_arguments(function_name, arguments, tools)
```

One response path (twice), so §8's two-path rule does not apply — but both insertion points
need coverage: `test_stream_filters_ollama_arguments_streaming_branch` and
`..._fallback_branch`, in `src/praisonai/tests/unit/llm/test_llm_stream_ollama_parity.py`.

Drive the fallback branch with an Ollama model (which reports
`supports_streaming_with_tools() is False`, so `4304-4306` sends it there). Drive the streaming
branch with `gpt-4o` plus a monkeypatched `_provider_adapter` reporting Ollama — and assert in
the test that this is the only way to reach it, which documents that **the streaming branch is
unreachable for real Ollama today**.

**Non-Ollama:** the `if is_ollama and tools` guard makes it a no-op; assert with
`test_stream_does_not_filter_arguments_for_default_adapter` (patch with a `Mock`, assert
`not called` for `gpt-4o`).

**Verify live:** §2.7 script. The stream line must **still** read `tool_calls=10 out=''`.
**Do not fix that here** — it is the successor order's job (§5.5). Any improvement means you
changed more than one thing.

**Rollback:** `git revert <sha>`.

---

## 5. The async/stream gap — disposition per compensation

Every row of §2.6 gets one of: **(a)** part of an order-06 step, **(b)** a separate follow-up
order, **(c)** deliberately out of scope. No row is left unassigned.

### 5.1 `tool_result_mapping` — 8/0/0 → **(c) out of scope, and recommend deletion**

Do **not** port it. Read what it does (`llm.py:3682-3688`, `3724-3735`):

```python
3684:  for arg_name, arg_value in list(arguments.items()):
3685:      if isinstance(arg_value, str) and arg_value in tool_result_mapping:
3686:          # Replace function name with its result
3687:          arguments[arg_name] = tool_result_mapping[arg_value]
...
3729:  elif isinstance(tool_result, str):
3730:      import re
3731:      match = re.search(r'\b(\d+)\b', tool_result)
3732:      if match:
3733:          tool_result_mapping[function_name] = int(match.group(1))
```

It silently rewrites a user-supplied tool argument whenever that argument's *string value
happens to equal a previously-called function's name*, substituting the first integer found
anywhere in that function's string result. `get_weather` returning `"Paris: 21C sunny"`
registers `21`; a later call with `city="get_weather"` would receive `21`.

This is a **data-corruption hazard, not a compensation**. Porting it to async and stream would
triple the exposure and violate the ledger's closing obligation ("no order may add a fifth copy
of any compensation"). **Recommendation:** a separate order to remove it, gated on a
characterization test proving no example or test depends on it.

### 5.2 `max_tool_repairs` + `_validate_tool_call` + `TOOL_CALL_REPAIR_PROMPT` — 2/1/1 sync only

→ **(b) follow-up for async; (b) follow-up for stream's fallback branch only; (c) impossible in
the true streaming branch.**

*Async:* mechanically portable — same request/response shape, same `messages` list, same
`iteration_count` accounting. But it is *schema validation*, provider-independent, and not
adapter-shaped, so it is not A1 work. Separate order.

*Stream — the honest split:*
- **The non-streaming fallback branch (`4553-4667`) can have it.** This is where Ollama,
  Anthropic and Gemini with tools actually land (`4304-4306`), so in practice it covers every
  provider that would need repair. Nothing has been yielded at validation time when `content` is
  empty — and when `content` is non-empty it has already been yielded at `4614`, so
  repair-and-retry would produce a *duplicate* prose emission. Correct rule: validate before
  dispatch; on failure append the repair prompt and loop **without** re-yielding prose already sent.
- **The true streaming branch (`4308-4551`) cannot have repair-and-retry.** A tool call is
  assembled from deltas (`_process_tool_calls_from_stream`, `llm.py:6752`) and is complete only
  when the stream ends — by which time every content delta has already been `yield`ed to the
  caller's `for` loop. **You cannot un-yield.** What *is* possible while streaming: (i) refuse to
  dispatch an invalid call; (ii) yield additional chunks; (iii) raise. What is not possible:
  retract, rewrite, or replace anything already emitted.

  **Honest user-facing behaviour:** on a validation failure in the true streaming branch, do not
  silently drop the call (today's behaviour is worse — it drops it *and* yields nothing) and do
  not attempt a repair round. Raise `LLMResponseError` naming the tool and the validation error.
  A caller that wants repair should not be streaming; the SDK already knows how to express that
  choice — `_supports_streaming_tools()` — and the honest extension is for repair-requiring
  configurations to report `False` there, sending the turn to the fallback branch where repair
  is possible. Title that order: *"tool-call repair is a non-streaming capability; make the
  streaming gate say so."*

### 5.3 `force_tool_usage` / `_should_force_tool_usage` / `FORCE_TOOL_USAGE_PROMPT` — 1/0/0

→ **(b) immediate follow-up, elevated priority.** This should be order 06's direct successor.

`get_default_settings()` (live, `llm.py:690`) sets `force_tool_usage = 'auto'` for **every**
Ollama `LLM`, on all three paths. `_should_force_tool_usage` is consulted **only** at
`llm.py:3561`, inside `get_response`. So `Agent(llm="ollama/...", stream=True)` accepts the
setting, reports it on `self.force_tool_usage`, and never acts on it. **A setting accepted and
ignored is exactly what root `AGENTS.md` forbids.**

Portability: `_should_force_tool_usage` (`1768-1788`) is pure —
`(response_text, tool_calls, formatted_tools, iteration_count) -> bool` — and the action is one
`messages.append` plus `continue`. Trivial for async. For stream: fine in the fallback branch;
in the true streaming branch it is an *additional* request after prose was already yielded,
which is legal (yielding more is always possible) but changes the stream's shape. That order
must state which of the two it does.

### 5.4 `_validate_and_filter_ollama_arguments` — 1/1/0 → **(a) Step 06.6**

Pre-dispatch, streaming-safe, guarded by `is_ollama and tools`. Done in this order.

### 5.5 `_generate_ollama_tool_summary` + `_handle_ollama_sequential_logic` + `OLLAMA_SUMMARY_ITERATION_THRESHOLD` — 1/1/0

→ **(b) separate follow-up — and this is where the measured stream failure lives.**

The §2.7 stream result — 10 tool invocations, zero output — is caused by their absence: nothing
breaks the fallback `while fallback_iterations < max_fallback_iterations` loop (`4572`) when
Ollama keeps re-emitting a tool call with empty `content`, and nothing synthesizes an answer at
the end. The loop exhausts `max_iter`, logs at `4665-4667`, and falls off the end of the
generator having yielded nothing.

Streaming feasibility: **fully possible.** Yielding a synthesized summary as a final chunk is
additive — the impossibility in §5.2 is about *retracting*, not appending.

Why it is a separate order: it **changes the stream contract**. A turn that currently yields
nothing would begin yielding synthesized text the model never produced. That needs its own
characterization baseline and its own answer to the alternative. The two options, stated plainly
for that order to choose between:
- **Synthesize** (matches sync/async): consistent across paths; risks presenting
  `str(tool_result)` as if the model wrote it.
- **Raise** (`LLMResponseError("provider produced no answer after N tool iterations")`): honest,
  and consistent with `00-ground-truth.md` §2's rule that a fabricated answer is worse than an error.

**Recommendation for that order: raise on the stream path, keep synthesis on sync/async**, and
record the asymmetry as intentional — a streaming consumer has already rendered partial output
and a synthesized tail is indistinguishable from model text, whereas a sync caller gets one
return value it can inspect. But that is a product decision and must be made in its own order
with its own review, not smuggled in here.

### 5.6 `OLLAMA_TOOL_USAGE_PROMPT` — 1/1/0 → **(b) follow-up, bundled with §5.5**

Same shape (append a message, re-request), same branch, same tests. Bundle it.

### 5.7 `OLLAMA_FINAL_ANSWER_PROMPT` — 0/**1**/0 → **(b) follow-up; the gap runs against `get_response`**

`llm.py:5298-5303`, async only. The "sync compensates most" framing is wrong here, and per §2.7
this is the leading candidate for why sync returns `'{\n\n\n}'` while async returns the right
answer. Step 06.0 settles it.

The follow-up that adds it to sync is a **behaviour change** — sync output would go from
`'{\n\n\n}'` to `'Paris: 21C sunny'` — so it needs Step 06.4's characterization tests in place
first, with `test_non_empty_response_after_tools_returns_model_text` deliberately updated in
that commit. **That test failing is the signal that the fix landed.**

### 5.8 `_register_deferred_if_any` — 1/**0**/1 → **(b) follow-up; async is the odd one out**

Present in sync (`2918`) and stream (`4461`), missing from async. Deferred media follow-ups
registered by a tool are dropped on the async path. Not adapter-shaped, not Ollama-specific.

### 5.9 `_manage_context_in_loop` (1/1/0) and `_finalise_on_limit` (2/2/0) → **(b) follow-up**

`get_response_stream` performs no in-loop context management and no max-steps finalisation. Both
are provider-independent and streaming-compatible (context trimming happens before the request;
finalisation appends a final chunk). One order, both fixes, one test per branch.

### 5.10 `supports_streaming()` — live in async only → **(c) out of scope; do not "fix" this**

It looks like an asymmetry to close. It is not. `AnthropicAdapter.supports_streaming()` returns
`False` for a reason its own comment states:

```python
215:    def supports_streaming(self) -> bool:
216:        # litellm.acompletion with stream=True returns a ModelResponse (not async generator)
217:        # for Anthropic in the async path, causing 'async for requires __aiter__' error
218:        return False
```

The defect is **specific to `litellm.acompletion`**. Consulting it from `get_response` or
`get_response_stream` would disable Anthropic streaming entirely in the sync and generator
paths, **where it works** — a real regression for users, dressed as consistency. Leave the call
sites as they are. The honest cleanup is a rename (`supports_async_streaming`) or a docstring,
both public-surface changes needing their own order and a deprecation shim under I1.

---

## 6. The anti-regression test

Location: `src/praisonai/tests/unit/llm/test_llm_adapter_seam.py` — chosen because that
directory **is** run by CI and `src/praisonai-agents/tests/unit/` is not (§3.1 Trap A).

```python
"""Anti-regression: the provider adapter must stay load-bearing.

A1 (measured 2026-09-03 on origin/main @2591aa405): DefaultAdapter declared 17
methods and 11 of them had zero call sites anywhere in praisonaiagents, while
llm/llm.py carried 145 lines of hand-written Ollama dispatch doing the same
jobs. Nothing failed. This file is what makes that state fail.
"""

import ast
import pathlib

import pytest

# Methods known to have zero call sites, with the ledger decision for each.
# This set may only ever SHRINK. Removing a name is the last step of the work
# order that wires or deletes it. Adding a name requires a documented reason in
# 06-adapter-revival.md -- a new adapter method with no consumer is the exact
# defect this file exists to prevent (root AGENTS.md: no exports without a live
# consumer).
KNOWN_DEAD = frozenset({
    "extract_reasoning_tokens",          # DELETE  - no override, no divergence
    "format_tools",                      # DELETE  - inline behaviour is inverse
    "get_max_iteration_threshold",       # DELETE  - duplicates should_summarize_tools
    "get_streaming_adapter",             # DELETE  - pure speculative API
    "handle_empty_response_with_tools",  # WIRE    - step 06.4
    "inject_cache_control",              # DELETE  - stub, no impl anywhere
    "parse_tool_calls",                  # DELETE  - signature cannot express ModelResponse
    "post_tool_iteration",               # DELETE  - sets a flag nothing reads
    "recover_tool_calls_from_text",      # WIRE    - step 06.5
    "should_skip_streaming_with_tools",  # DELETE  - subsumed by supports_streaming_with_tools
    "supports_structured_output",        # DELETE  - model_capabilities already does this
})

# Attribute-call receivers that denote a provider adapter. Restricting to these
# is what stops OpenAIClient.format_tools (an unrelated same-named method) from
# being counted as a call site for DefaultAdapter.format_tools.
ADAPTER_RECEIVERS = frozenset({"_provider_adapter", "adapter", "provider_adapter"})


def _llm_package_root() -> pathlib.Path:
    import praisonaiagents.llm as llm_pkg
    return pathlib.Path(llm_pkg.__file__).parent


def _adapter_methods() -> frozenset:
    from praisonaiagents.llm.adapters import DefaultAdapter
    return frozenset(
        name for name, value in vars(DefaultAdapter).items()
        if callable(value) and not name.startswith("_")
    )


def _receiver_name(func: ast.Attribute):
    """Best-effort name of the object a method is called on."""
    value = func.value
    if isinstance(value, ast.Name):            # adapter.foo()
        return value.id
    if isinstance(value, ast.Attribute):       # self._provider_adapter.foo()
        return value.attr
    if isinstance(value, ast.Call):            # get_provider_adapter(p).foo()
        inner = value.func
        if isinstance(inner, ast.Name):
            return inner.id
        if isinstance(inner, ast.Attribute):
            return inner.attr
    return None


def _call_sites() -> dict:
    """Map adapter method name -> ['relative/path.py:lineno', ...].

    Scans every module under praisonaiagents/llm/ except the adapter module
    itself (where these names are definitions, not calls).
    """
    root = _llm_package_root()
    adapters_file = (root / "adapters" / "__init__.py").resolve()
    methods = _adapter_methods()
    found = {}
    for path in sorted(root.rglob("*.py")):
        if path.resolve() == adapters_file:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError) as exc:   # pragma: no cover
            pytest.fail(f"could not parse {path}: {exc}")
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            name = node.func.attr
            if name in methods and _receiver_name(node.func) in ADAPTER_RECEIVERS:
                found.setdefault(name, []).append(
                    f"{path.relative_to(root)}:{node.lineno}")
    return found


def test_every_adapter_method_has_a_call_site():
    """Every DefaultAdapter method is invoked on an adapter instance somewhere."""
    methods = _adapter_methods()
    called = _call_sites()
    dead = sorted(methods - set(called) - KNOWN_DEAD)
    assert not dead, (
        "Adapter method(s) with no call site and no entry in KNOWN_DEAD: "
        f"{dead}. Either wire them into llm/llm.py, delete them, or add them "
        "to KNOWN_DEAD with a justification in 06-adapter-revival.md. "
        "An adapter method that nothing calls is a lie about the extension point."
    )


def test_no_dead_name_is_actually_live():
    """KNOWN_DEAD may not name a method that now has a call site.

    Without this, KNOWN_DEAD rots into a permanent blanket exemption: a method
    gets wired, nobody removes it from the set, and the next dead method added
    beside it is never noticed.
    """
    called = _call_sites()
    stale = sorted(name for name in KNOWN_DEAD if name in called)
    assert not stale, (
        f"KNOWN_DEAD lists live method(s) {stale} -- called at "
        f"{ {n: called[n] for n in stale} }. Remove them from KNOWN_DEAD."
    )


def test_known_dead_names_all_exist():
    """KNOWN_DEAD may not name a method that no longer exists.

    Keeps the set honest after a deletion step: a stale entry would silently
    widen the exemption for a future method that happens to reuse the name.
    """
    methods = _adapter_methods()
    missing = sorted(KNOWN_DEAD - methods)
    assert not missing, (
        f"KNOWN_DEAD names non-existent method(s) {missing}. "
        "Remove them from KNOWN_DEAD in the same commit as the deletion."
    )


def test_protocol_and_default_adapter_agree():
    """Every method the protocol declares exists on DefaultAdapter.

    LLMProviderAdapterProtocol is @runtime_checkable, so isinstance() only
    checks name presence -- it cannot notice a protocol method that no adapter
    implements. This does.
    """
    from praisonaiagents.llm.protocols import LLMProviderAdapterProtocol
    declared = frozenset(
        name for name in getattr(LLMProviderAdapterProtocol, "__protocol_attrs__", ())
        if not name.startswith("_")
    ) or frozenset(
        name for name, value in vars(LLMProviderAdapterProtocol).items()
        if callable(value) and not name.startswith("_")
    )
    missing = sorted(declared - _adapter_methods())
    assert not missing, (
        f"Protocol declares {missing} but DefaultAdapter does not implement it."
    )
```

### 6.1 What this test cannot do — stated so nobody mistakes it for a ceiling

1. **It cannot detect an unreachable call site.** `should_skip_streaming_with_tools` is the
   proof: had `llm.py:3122` called it, this test would pass — while the branch stayed dead
   because `3117` short-circuits first. Reachability is semantic; this test measures syntax.
2. **It cannot detect a call site never *taken* at runtime** — behind `if False`, behind a config
   flag nobody sets, or in a `try` whose `except` swallows everything (which is how
   `_create_tool_message`'s absence hid for so long, per its own docstring at `6776-6786`).
3. **One call site is enough to satisfy it. This test does not detect A2 at all.** A method
   called only from `get_response` passes just as well as one called from all three. A2's guard
   is the per-path parity tests in Steps 06.3, 06.4 and 06.6, and there is no cheap general form.
4. **The receiver allowlist is a heuristic.** A call through an unusually-named local
   (`a = get_provider_adapter(p); a.foo()`) is invisible. Mitigation: `ADAPTER_RECEIVERS` covers
   every naming used in `llm/` today, and a new name is a reviewable one-line addition. Dropping
   the allowlist instead produces false *positives* — `openai_client.format_tools` would mask
   `DefaultAdapter.format_tools` — which is worse, because it hides dead code rather than
   over-reporting it.
5. **It scans `praisonaiagents/llm/` only.** An adapter method called from `agent/` or `memory/`
   would be reported dead. No such call exists today (verified repo-wide); widen the root if that
   changes.
6. **It runs only where CI runs it.** If order 04 or 05 later brings
   `src/praisonai-agents/tests/unit/` into CI, move it next to `test_adapter_registry.py` — but
   not before.

---

## 7. Handoffs — work this order deliberately does not do

| To | What | Why not here |
|---|---|---|
| **order 02** | Make `add_provider_adapter` reachable: have `_detect_provider` consult the adapter registry (e.g. `if has_provider_adapter(prefix): return prefix`) before falling back to `"openai"`, plus `test_registered_custom_adapter_is_selected`. Today a registered name can never be passed to `get_provider_adapter` — **the hook is a lie**. If order 02 declines, the correct disposition flips to **DELETE** under root `AGENTS.md`. | `_detect_provider` belongs to order 02. Related: `00-ground-truth.md` §5 shows `ollama_chat/`, `lm_studio/`, `vllm/` all resolving to `DefaultAdapter` — the same registry gap. |
| **order 02** | Reconcile `_is_ollama_provider()` with `isinstance(adapter, OllamaAdapter)`. Steps 06.4 and 06.5 replace the former with the latter and are **blocked** if `test_ollama_adapter_selection_matches_is_ollama_provider` fails on `main`. | Same ownership. |
| **orders 04 / 05** | `src/praisonai-agents/tests/unit/` — incl. `test_adapter_registry.py` (38 tests) and all 13 files in `tests/unit/llm/` — is run by **no** workflow. Add it to a shard. | `.github/workflows/**` is theirs. |
| **a new order** | `llm/streaming_protocol.py`: 387 lines, 4 adapter classes, 3 public functions, 11 Ollama references. After Step 06.2 deletes `DefaultAdapter.get_streaming_adapter`, its only production importer is gone and **the whole module is dead** (only `tests/test_architectural_fixes.py` — itself outside CI — imports it). Decide: delete, or wire as the streaming seam. | Deleting a 387-line module is not "one adapter method"; it needs its own risk assessment. Do not fold it into 06.2. |
| **a new order** | `OLLAMA_SUMMARY_ITERATION_THRESHOLD = 1` (`llm.py:273`) is applied to **all** providers at `3821` and `5446`: `elif tool_summary_text is None and iteration_count > self.OLLAMA_SUMMARY_ITERATION_THRESHOLD: continue`. For a non-Ollama provider at `iteration_count >= 2` this `continue` skips both the `max_iterations` safety check (`3826`) and the `response_text = ""` reset (`3837`). Latent, provider-independent, a behaviour change to fix. | Not adapter wiring; §1 row 9 explains why `get_max_iteration_threshold` is not the answer. |
| **follow-up orders** | §5.2, §5.3, §5.5, §5.6, §5.7, §5.8, §5.9 — one order each, in that priority order. **§5.3 first**: it is the only one where a live setting is silently ignored. | Each changes behaviour; order 06 is refactor-only. |

---

## 8. Hard constraints — and what each means concretely here

1. **Never edit two of the three response paths in one commit without a test covering both.**
   Steps 06.2, 06.5, 06.6 touch one path each — the rule is inert. Step 06.3 touches sync +
   async + the stream's formatter: it ships `test_tool_result_message_identical_across_paths`,
   parametrized over all three. Step 06.4 touches sync + async: it ships both
   `..._sync` and `..._async` in the same commit. Both, or split.

2. **No new abstraction layer.** `llm/adapters/` is the abstraction; this order makes it
   load-bearing. Do not add a quirk registry, a compensation table, a strategy object, a mixin,
   or a new module (ledger I7). Twelve of the twenty decisions are DELETE precisely because the
   temptation here is to build rather than remove. Step 06.3 is the only step that *adds* code to
   the adapter, and only by moving three identical copies into the method that already declares
   the job.

3. **Backward compatibility is mandatory (I1).** Nothing in `praisonaiagents.llm.adapters` is
   re-exported from `praisonaiagents.llm` or `praisonaiagents` (verified: no adapter name appears
   in either `__init__.py`'s lazy-import map), and none is documented under `docs/`. The Step
   06.2 deletions are therefore not public-surface removals in practice. `add_provider_adapter`
   is kept anyway, being the one name a third party would plausibly have found. If a reviewer
   disagrees about `list_provider_adapters` / `has_provider_adapter`, keep them and add them to
   `KNOWN_DEAD` with that reason — do not argue about it mid-step.

4. **`get_response` is 1,675 lines with 194 branch points.** Any diff inside `llm.py:2557-4231`
   must: quote at least three unmodified lines above and below the change; change **only** the
   lines named in this order — no reindentation of neighbours, no reflowing long lines, no
   comment tidy-ups, no `black`/`ruff --fix` over the file, no import reordering; keep the diff's
   line count within a few lines of the replacement's, so `git show --stat` is a truthful summary
   of scope; and be reviewed with `git diff -U10` before pushing. If the diff shows a hunk you
   did not intend, revert the file and redo the edit by hand.

5. **One adapter method per commit, one commit per branch, every step independently revertible.**

6. **Characterization test first, always.** Every step's tests must be written against
   `origin/main`, run, and observed green *before* the source edit. A test written after the
   change pins the change, not the behaviour. Where a step intentionally changes behaviour (only
   Step 06.3's non-serializable-result case), the test asserting the old behaviour must be marked
   `xfail(strict=True)` in the same commit, so the change is visible as a test-outcome diff
   rather than a silent edit.

7. **Update `README.md` §4 row 06 in the same commit as each step** — one line only, to avoid
   conflicts with concurrent orders.

---

## 9. Step summary

| Step | Branch | Item | Paths edited | Risk | Reverts to |
|---|---|---|---|---|---|
| 06.0 | — | — | none (throwaway probe) | none | n/a |
| 06.1 | `test/adapter-reachability-ratchet` | ratchet | none | none | 1 test file |
| 06.2 | `refactor/delete-dead-adapter-surface` | 9 methods + 2 module fns | sync ×1 (dead branch) | very low — zero call sites, proven | pure deletion |
| 06.3 | `refactor/wire-default-tool-result-message` | `format_tool_result_message` | sync, async, stream-formatter | low — default body has no consumers today | 3 inline copies |
| 06.4 | `refactor/wire-handle-empty-response-with-tools` | `handle_empty_response_with_tools` | sync, async | medium — guard widens from `_is_ollama_provider()` to adapter dispatch | 2 predicates |
| 06.5 | `refactor/wire-recover-tool-calls-from-text` | `recover_tool_calls_from_text` | sync | medium-high — 4 measured deltas, all argued inert | 33 inline lines |
| 06.6 | `fix/stream-path-ollama-argument-filtering` | A2 port | stream (both branches) | low — pre-dispatch, guarded | 2 insertions |

**End state:** `KNOWN_DEAD` empty, `DefaultAdapter` at 8 methods all with live call sites,
`llm.py` shorter by ~90 lines, and a CI-enforced test that makes A1 recurrence a red build.

A2 is **measured, dispositioned and partly closed — not solved.** §5 names the seven successor
orders and which of them is genuinely impossible while streaming.
