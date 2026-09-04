# Ground truth

Every claim here was measured, not estimated. Each carries **how** it was obtained so it can
be re-checked cheaply. Measured 2026-09-03 against `origin/main` at `2591aa405`, with a live
Ollama 0.33.2 (`b79067b0`) on `127.0.0.1:11434`.

If a work order contradicts something here, re-measure before acting. Numbers drift.

> **Capabilities are per-model, not per-server.** An early draft of this file attributed the
> 9B model's capability list to `qwen3:0.6b`. Re-verified 2026-09-03: `qwen3:0.6b` is
> `["completion","tools","thinking"]` — **no vision**. Always name the model when quoting a
> capability set.

---

## 1. Runtime facts, verified live

| Fact | Value | How to re-verify |
|---|---|---|
| Ollama liveness probe | `GET /` returns `200` with body `Ollama is running` | `curl -sI 127.0.0.1:11434/` |
| Ollama version probe | `{"version":"0.33.2"}` | `curl -s 127.0.0.1:11434/api/version` |
| Capability probe works | `qwen3:0.6b` → `["completion","tools","thinking"]` (the 9B tamil model, separately, → `[...,"vision"]`) | `curl -s :11434/api/show -d '{"model":"qwen3:0.6b"}' \| jq .capabilities` |
| Unknown `options` keys are silently dropped | `{"totally_bogus_key":123}` → HTTP 200, no warning | send it to `/api/chat`; response is a normal completion |
| Tool-param schema keywords are stripped | `minLength`, `format`, `default`, `additionalProperties` all absent from the rendered prompt | `/api/chat` with `_debug_render_only: true` and those keys set |
| `parameters.type` must be a bare string | `"type": ["object","null"]` → **HTTP 400** `cannot unmarshal array into Go struct field ToolFunctionParameters...type of type string` | send that tool definition to `/api/chat` |
| **`format` + `tools` are mutually destructive** | Tool call silently suppressed; model fabricates. Same request without `format` calls the tool correctly. | see §2 below |

### Installed on this machine

`ollama` (0.33.2), `llama-server` (b7620, Homebrew), `mlx_lm.server`, `hf` CLI.
**Not** installed: `lms` (LM Studio), `vllm`.
Ports open at time of measurement: `11434` only.

---

## 2. The reproduction that matters most

`format` (JSON schema) plus `tools`, sent to Ollama, produces a **confident fabrication** with
an HTTP 200 and no warning. The JSON grammar makes the tool-call tag unemittable, so the
model cannot call the tool and answers from nothing instead.

```
POST /api/chat   model=qwen3:0.6b   think=false
prompt: "What is the weather in Paris? Use the tool."
tools:  [get_weather(city: string)]

WITH format + tools                     -> HTTP 200
  message.tool_calls : null
  message.content    : {"answer": "The weather in Paris is sunny with a temperature of 15C."}

TOOLS ONLY (format removed)             -> HTTP 200
  message.tool_calls : [{"function": {"name": "get_weather",
                                      "arguments": {"city": "Paris"}}}]
  message.content    : ""
```

Consequence for design: this combination must **raise**, not be silently repaired. A
fabricated answer that looks correct is worse than an error.

---

## 3. Codebase measurements

All obtained by script over `praisonaiagents/` at `2591aa405`.

### Scale

| Metric | Value |
|---|---|
| Python files / lines | 595 / 238,936 |
| Files over 2,000 lines | 13 |
| `agent/agent.py` | 7,701 |
| `llm/llm.py` | 7,160 |
| `agent/chat_mixin.py` | 6,151 |
| `llm/openai_client.py` | 2,691 |
| `llm/adapters/__init__.py` | 340 |

### `LLM` class cohesion

95 methods, 6,779 lines. Three largest methods total 3,087 lines — 43% of the file.

| Lines | Location | Method | Branch/loop/try nodes |
|---|---|---|---|
| 1,675 | `llm.py:2557` | `get_response` | **194** |
| 969 | `llm.py:4706` | `get_response_async` | 115 |
| 443 | `llm.py:4233` | `get_response_stream` | 56 |
| 249 | `llm.py:5966` | `_build_completion_params` | 52 |
| 199 | `llm.py:413` | `__init__` | 10 |

### Adapter call sites — the A1 finding

`DefaultAdapter` declares **17 methods** (an earlier draft said 18; the 18th item,
`add_provider_adapter`, is a module-level function). Eleven methods have **zero** call sites
anywhere, and with the three module functions that is 12 dead items. Note also that
`LLMProviderAdapterProtocol` declares only **16** — it omits `get_streaming_adapter`, so that
method is not part of the protocol it claims to implement.

```
supports_streaming                        2
format_tool_result_message                1   (llm.py:1712)
get_default_settings                      1   (llm.py:690)
should_summarize_tools                    1
supports_prompt_caching                   1
supports_streaming_with_tools             1
--- zero call sites ---
recover_tool_calls_from_text              0   (inline copy at llm.py:3468-3500)
parse_tool_calls                          0
handle_empty_response_with_tools          0
post_tool_iteration                       0
format_tools                              0
get_streaming_adapter                     0
get_max_iteration_threshold               0
should_skip_streaming_with_tools          0
supports_structured_output                0
inject_cache_control                      0
extract_reasoning_tokens                  0
add_provider_adapter                      0   (public registration hook)
```

Ollama references (case-insensitive): `llm/llm.py` **145**, `llm/adapters/__init__.py` 19,
`llm/streaming_protocol.py` 11, `tools/call_executor.py` 6.

### Compensation coverage across the three response paths — the A2 finding

```
                                        get_response   _async   _stream
                                             1675 L     969 L     443 L
tool_result_mapping  (value fix-up)          8          0         0
max_tool_repairs     (repair loop)           2          0         0
force_tool_usage     (prompt inject)         1          0         0
_validate_and_filter_ollama_arguments        1          1         0
_generate_ollama_tool_summary                1          1         0
_handle_ollama_sequential_logic              1          1         0
_format_ollama_tool_result_message           1          1         1*  (indirect)
```

`get_response_stream` has none of the seven — except `_format_ollama_tool_result_message`,
which it reaches indirectly via `_create_tool_message` (`llm.py:6791`), so that row overstated
the gap. A fuller re-measurement found **16** divergent compensations, not 7; three of them run
*against* the sync path. The full matrix is in `06-adapter-revival.md` §2.6. `difflib` similarity of `get_response` against
`get_response_async` is **22.3%**, while the file's other four sync/async pairs are 76–91% —
so those two have diverged, not merely duplicated.

### Import graph — the I6 constraint

65 subpackages, 212 directed edges, **26 mutually-importing pairs**. Heaviest:

```
agent   <-> tools       53 + 1        llm/ imports: tools 10, streaming 7,
agent   <-> approval    28 + 1                      agent 4, telemetry 2,
agent   <-> config      25 + 1                      auth 2, compaction 2,
agent   <-> llm         19 + 4                      context 1, thinking 1
llm     <-> tools       10 + 1
context <-> llm          2 + 1        15 subpackages import llm/
```

### Reachability — the A3 finding

21 modules call a provider SDK directly, bypassing both clients: 23 `litellm.completion/acompletion`,
7 `litellm.embedding/aembedding`, 16 `chat.completions.create`, 3 bare `OpenAI()`.

These nine contain **zero** occurrences of `api_base` or `base_url`, so there is no parameter
to set — "run everything locally" is currently unachievable, not merely unconfigured:

```
memory/memory.py          workflows/workflows.py     eval/judge.py
eval/grader.py            eval/accuracy.py           context/compressor.py
context/optimizer.py      lite/__init__.py           telemetry/performance_monitor.py
```

Worst single case, `memory/memory.py:2186-2192`:

```python
from openai import OpenAI
client = OpenAI()                    # no base_url, no api_key
response = client.chat.completions.create(
    model=llm or "gpt-4o-mini", ...
```

Hardcoded defaults in code (excluding docstrings): **105** `"gpt-4o-mini"`, **17**
`"text-embedding-3-small"`. Sixteen of the 105 are the identical line
`self.llm if hasattr(self,'llm') else "gpt-4o-mini"` in `agent/context_agent.py`.

### Stringly-typed provider identity — the A6 finding

**77 occurrences of 23 distinct string predicates** across `src/`. The same provider is
tested inconsistently, which is precisely how D3 and D4 arose:

```
 9  startswith("anthropic/")     gemini tested 3 ways:   gpt tested 4 ways:
 8  startswith("ollama/")          startswith("gemini")    startswith('gpt-')
 7  "ollama" in                    startswith("gemini/")   startswith("gpt-")
 6  startswith("gemini")           startswith('gemini-')   startswith("gpt")
 5  startswith("openai/")                                  "gpt" in
 5  startswith("claude")
 3  ":11434" in
```

### Accretion history — why boundaries matter here

| File | First | Now | Commits | Ever shrank |
|---|---|---|---|---|
| `llm/llm.py` | 1,212 (Jan 2025) | 7,160 | 251 | never, in 18 sampled months |
| `agent/agent.py` | 1,251 (Jan 2025) | 7,701 | 472 | once — the split below |
| `agent/chat_mixin.py` | created Apr 2026 | 6,151 | 150 | — |

On **2026-04-01** `agent.py` was split 8,915 → 5,030 by extracting `chat_mixin.py`. Five
months later the two halves total **13,852 lines — 55% above the pre-split file**, growing
~33 lines/day. Moving code did not create a boundary. This is the argument for I6 being a
*test* rather than a convention.

---

## 4. Dependency facts

| Package | Version present | Status |
|---|---|---|
| `httpx` | 0.28.1 | **hard transitive dep** of required `openai>=2.0.0` (`httpx<1,>=0.23.0`) |
| `aiohttp` | 3.14.1 | direct required core dep |
| `openai` | 2.44.0 | direct required core dep |
| `litellm` | 1.90.2 | optional (`llm`, `memory` extras) |

`pyproject.toml` declares **17 optional extras** — `a2ui, api, all, auth, autonomy, crawl,
dakera, graph, knowledge, llm, mcp, memory, mongodb, os, sandbox, search, telemetry` — and
**none of them is local**. `import praisonaiagents` measures 0.04 s, so imports are lazy and
cheap; discovery latency is the only startup cost to manage.

**Conclusion (superseded).** This section originally concluded `local/` should use `httpx`.
That was reversed by the normative decision in `07-local-package-spec.md` §3: `httpx` is present
only as an **undeclared transitive** edge (`openai -> httpx`), so building the dependency sink on
it means a future `openai` release dropping `httpx` would silently break `local/`. The client is
therefore stdlib `urllib.request`, and the boundary test forbids `httpx`/`requests`/`aiohttp`.
The measurement above stands; only the recommendation drawn from it was wrong.

---

## 5. litellm prefix resolution vs ours

litellm 1.90.2 resolves all of these; PraisonAI's `_detect_provider` recognises only `ollama/`:

```
ollama/llama3.2       -> ollama   OllamaAdapter    repairs=2
ollama_chat/llama3.2  -> openai   DefaultAdapter   repairs=0     <- litellm's RECOMMENDED prefix
lm_studio/qwen        -> openai   DefaultAdapter   repairs=0
vllm/x                -> openai   DefaultAdapter   repairs=0
hosted_vllm/x         -> openai   DefaultAdapter   repairs=0
huggingface/x         -> openai   DefaultAdapter   repairs=0
```

---

## 6. Known-bad environment note

`mervinpraison/praisonai-qwen3.5-9b-tamil-en2ta:latest` does **not load** on Ollama 0.33.2:
`Failed to load CLIP model from ...sha256-11540ddc21b3...`, HTTP 500. The vision projector
blob is the failing piece. Use `qwen3:0.6b` for local verification instead. Unrelated to this
work, but it will waste an agent's time if not known.


---

## 7. The three response paths disagree — measured, not inferred

Live Ollama, `temperature=0`, identical prompt and tool, two trials, reproducible
(script in `06-adapter-revival.md` §2.7):

```
sync    calls=2   'Paris: 21C sunny. Paris: 21C sunny.'
async   calls=1   'Paris: 21C sunny'
stream  calls=10  ''
```

> **Corrected 2026-09-03.** An earlier draft recorded the sync path returning
> `'{\n\n\n}'` with one tool call. That did not reproduce; the figures above did,
> across two trials. The finding is unchanged — the paths disagree and the stream
> path is broken — but the `'{\n\n\n}'` sample should not be cited.

Three facts follow, and they reframe the work:

1. **The best-compensated path produces the worst answer.** `get_response` carries 16 of the 18
   compensations and calls the tool twice, returning a doubled answer;
   `get_response_async` carries 8 and returns the correct answer once. More compensation is
   not the goal — *the same* compensation is.
2. **The stream path is not under-compensated, it is broken.** It burns all 10 iterations of
   `max_iter`, invokes the tool **ten times** for a one-tool question, and yields nothing. That
   is a cost and side-effect amplifier, not a formatting defect.
3. Leading hypothesis for the sync/async split: `OLLAMA_FINAL_ANSWER_PROMPT` (`llm.py:5302`,
   async only). **Still a hypothesis, not a measurement** — it was not settled during order 06,
   because the corrected baseline changed what needs explaining.

## 8. Two test-infrastructure traps

- **`src/praisonai-agents/tests/` is almost entirely outside CI.** The only tests any workflow
  runs from it are `tests/smoke/test_subscription_auth.py` and
  `tests/unit/auth/test_agent_auth_wiring.py`. `tests/unit/test_adapter_registry.py` (38 tests)
  and all 13 files in `tests/unit/llm/` run **nowhere**. Put new tests in
  `src/praisonai/tests/unit/llm/`, which is run.
- **`test_ollama_tool_reliability.py` tests a copy, not the product.** Its `MockLLM`
  re-implements `_is_ollama_provider`, `_apply_ollama_defaults`, `_validate_tool_call`,
  `_should_force_tool_usage` and both prompt templates. It cannot fail in response to any change
  in `llm.py`. Do not treat it as a safety net.


## 9. Test-gating facts (order 04)

- **`not network`, not `provider_ollama`, is what deselects the mocked base_url suite.** The gating
  plugin implies `network` from *any* provider marker (`test_gating.py:235-238`) and every CI
  expression contains `not network`. Editing the workflows' `-m` strings accomplishes nothing.
- `tests/unit/**` is **exempt** from provider auto-detection (`test_gating.py:215`,
  `test_type != 'unit'`). That is why `tests/unit/llm/test_ollama_tool_reliability.py` runs in CI
  while the integration file does not — and why live tests placed under `tests/unit/` need an
  **explicit** marker.
- `-m provider_ollama` currently selects **32 tests across 5 files**; only 7 are Ollama tests.
- **4 of the 7 tests in `test_base_url_api_base_fix.py` fail when actually executed** —
  `LLMResponseError: 'str' object has no attribute 'choices'`. The mock returns a dict; the
  tool-calling loop needs an object with `.choices`.
- **`tests/test_double_api_fix.py` makes a real network call when forced to run.** `llm.py` routes
  `gpt-4o-mini` through `litellm.responses` (`llm.py:6434`), not `litellm.completion`, so its patch
  no longer intercepts (verified: 401 from `api.openai.com/v1/responses`). It is currently masked
  by an unconditional auto-skip — **anyone who "fixes" the skip without fixing the mock gets live
  billed calls.**
- **`network_guard.py` disables itself** for anything under `/integration/`, `/e2e/`, `/live/`
  (lines 103-105) and for any `provider_*`-marked test (96-100). The suite's network blocker does
  not cover the tests most likely to make network calls.
- **A live Ollama suite already exists** and has never run:
  `tests/integration/test_ollama_tool_calling_live.py`, 230 lines, 7 tests, gated on
  `PRAISONAI_TEST_OLLAMA`. It is broken against `main` — all 7 pass `verbose=True` to `Agent()`,
  and two pass `force_tool_usage=` / `max_tool_repairs=`; all three now raise `TypeError`.
- **`qwen3:0.6b` is 522 MB** (not ~400 MB) and reports `completion, tools, thinking` — **no
  vision**. Reliability through `Agent`: default 3/4; `force_tool_usage="always"` + `temperature=0`
  **6/6**; multi-step arithmetic 0/2 (one hung past 90 s).
