# 04 — D7: provider markers are assigned per file, so mocked tests are gated as if live

**Branch:** `fix/gating-per-test-provider-markers`
**Measured:** clean worktree at `origin/main` (`2591aa405`), working tree clean.
**Owns:** `src/praisonai/tests/_pytest_plugins/test_gating.py`, both `pytest.ini` files,
`src/praisonai/tests/conftest.py`, `tests/integration/test_base_url_api_base_fix.py`,
`tests/unit/cli/test_test_command.py`.
**Must not edit:** any `praisonaiagents/` source; `.github/workflows/**` (order 05).

> **The audit's stated root cause was wrong, and the correction changes the fix.**
> `provider_ollama` is a red herring. **`not network` deselects all 7 tests on its own**, because
> the plugin implies `network` from *any* provider marker and the file also matches
> `provider_openai`. **Removing `not provider_ollama` from the workflows would change nothing.**
> The fix must be marker-side, not workflow-side. This is why order 04 touches no YAML.

---

## 1. Corrections to the audit

| # | Claim | Verdict |
|---|---|---|
| 1 | 4 CI marker expressions carry `not provider_ollama` | **True but incomplete** — there is a 5th, non-CI location: `src/praisonai-code/praisonai_code/cli/commands/test.py:67` (`praisonai test --tier main`). |
| 2 | 7 tests, all deselected | **Exactly true** (`collected 7 items / 7 deselected / 0 selected`). **Stated cause is wrong** — see the callout above. |
| 3 | The file never inspects `litellm.completion` kwargs | **True** (only `mock_completion.assert_called()`). **And worse: 4 of the 7 tests fail outright when executed.** They are not merely toothless, they are broken. |
| 4 | `test_double_api_fix.py`: 0 asserts, 34 prints | **True. And worse:** all 3 tests are auto-`skip`ped in every configuration, and when forced to run its `patch('litellm.completion')` no longer intercepts — `llm.py` routes `gpt-4o-mini` through `litellm.responses`, so it makes a **real network call** (verified: 401 from `api.openai.com/v1/responses`). |
| 5 | `test_ollama_tool_reliability.py` asserts against MockLLM | **True.** 541 lines, MockLLM at 23–197, 28 tests, all pass. **Quantified:** 2 of the 8 re-implemented methods (`_apply_ollama_defaults`, `_try_parse_tool_call_json`) **do not exist on the real `LLM` at all.** |
| 6 | agents-side ollama tests gated only by `OLLAMA_HOST` | **True**, and `test_ollama_fix_openai` is gated only by `OPENAI_API_KEY` — a live **billed** call on a plain `pytest`. Mitigating: no CI workflow runs these two files. |
| 7 | No ollama live job | **True for CI**, but the audit **missed that the suite already exists**: `tests/integration/test_ollama_tool_calling_live.py`, 230 lines, 7 tests, gated on `PRAISONAI_TEST_OLLAMA=1`. It is **broken against current `main`**. See order 05. |

---

## 2. Reproduce before the fix

```bash
cd src/praisonai && export PYTHONPATH=$(cd ../praisonai-agents && pwd)
CI_M="not slow and not network and not local_service and not provider_anthropic and not provider_google and not provider_ollama and not provider_grok_xai and not provider_groq and not provider_cohere"
```

**R1 — 100% deselected:**
```bash
python -m pytest tests/integration/test_base_url_api_base_fix.py -m "$CI_M" --collect-only -q --disable-warnings
# collected 7 items / 7 deselected / 0 selected
```

**R2 — `provider_ollama` is a red herring.** Rerun R1 with `and not provider_ollama` **removed**:
still `7 deselected / 0 selected`. `not network` does it alone.

**R3 — the whole file is tagged.** With a marker-dump plugin, all seven items carry the identical
set `['integration', 'network', 'provider_ollama', 'provider_openai', 'skip']` — including the six
that never mention Ollama.

**R4 — 4 of 7 fail when actually executed:**
```bash
PRAISONAI_ALLOW_NETWORK=1 PRAISONAI_TEST_PROVIDERS=all OPENAI_API_KEY=sk-fake-offline \
  python -m pytest tests/integration/test_base_url_api_base_fix.py -o addopts="" -q --tb=no -rA
# 4 failed, 3 passed
```
All four fail with `LLMResponseError: ... 'str' object has no attribute 'choices'`. The three that
pass are the three that never call `get_response()`.

**R5 — `-m provider_ollama` selects 4× more than it should:**
```
   7 tests/integration/test_base_url_api_base_fix.py
   7 tests/integration/test_ollama_tool_calling_live.py
  11 tests/integration/test_rag_integration.py
   4 tests/integration/test_setup_integration.py
   3 tests/test_double_api_fix.py
```
**32 selected; only 7 are Ollama tests.** This is why order 04 is a hard prerequisite for order 05 —
`-m provider_ollama` is currently not a usable selector.

---

## 3. Root cause

`test_gating.py:153-166` scans the **entire file**:

```python
153  def _detect_providers_in_file(filepath: Path) -> Set[str]:
154      """Detect which providers are referenced in a test file."""
...
161      content = _get_file_content(filepath)
162      detected = set()
163      for marker, pattern in PROVIDER_PATTERNS.items():
164          if pattern.search(content):
165              detected.add(marker)
166      return detected
```

Line 28 is `'provider_ollama': re.compile(r'\b(ollama)\b', re.IGNORECASE)`. One occurrence inside
`test_ollama_environment_variable_compatibility` tags all seven items (applied at lines 213–230).

Note line 215: `if item.fspath and test_type != 'unit'` — **`tests/unit/**` is exempt**, which is
why `tests/unit/llm/test_ollama_tool_reliability.py` runs in CI while the integration file does not.

**The second mechanism, which the audit missed**, is lines 235–238:

```python
235          # 3. Add network marker if any provider marker is present
236          provider_markers = {m for m in existing_markers if m.startswith('provider_')}
237          if provider_markers and 'network' not in existing_markers:
238              item.add_marker(pytest.mark.network)
```

A mocked test that merely *mentions* `openai` gets `network`, and every CI expression contains
`not network`. Lines 262–267 then convert it into a runtime skip.

**Sub-defect 3.** Lines 59, 145, 177, 234 are all bare `mock_completion.assert_called()`. Nothing
reads `call_args`. Measured: `LLM(model='openai/mistral', base_url='http://localhost:4000',
api_key='sk-test').get_response("test", stream=False)` calls `litellm.completion` with
`base_url='http://localhost:4000'` and `api_base=None`. **So the file's title is stale** — the real
invariant is *`base_url` survives into the call*, not "maps to `api_base`".

---

## 4. The change

**Design decision: AST per-test marking, not file splitting.**

- *Split the file* — cost cheap, **benefit zero** (measured, R2): the six non-Ollama tests still
  match `provider_openai`, still get `network`, still get deselected. It also leaves `-m
  provider_ollama` selecting 32 tests and fixes nothing for the other 14 mixed-provider files.
  **Rejected.**
- *AST per-test marking* — one change in one plugin, fixes the class of problem, and is the
  prerequisite for order 05's selector to mean anything. **Recommended.**

### Sub-change 1 — per-test provider detection via AST

Keep `_detect_providers_in_file` (it now serves only the `network` marker) and add:

```python
def _detect_providers_in_text(text: str) -> Set[str]:
    """Return every provider marker whose pattern appears in ``text``."""
    detected = set()
    for marker, pattern in PROVIDER_PATTERNS.items():
        if pattern.search(text):
            detected.add(marker)
    return detected


def _build_per_test_provider_map(filepath: Path) -> Optional[Dict[tuple, Set[str]]]:
    """Map ``(class_name, func_name)`` -> provider markers for one test file.

    The text considered for a test is that test's own source segment plus its
    decorators -- not the whole file. Returns ``None`` if the file cannot be
    parsed, so callers fall back to whole-file rather than under-marking.
    """
    key = str(filepath)
    if key in _file_provider_cache:
        return _file_provider_cache[key]
    result: Optional[Dict[tuple, Set[str]]] = None
    try:
        source = _get_file_content(filepath)
        tree = ast.parse(source)
        result = {}

        def _visit(node, class_name=None):
            for child in getattr(node, 'body', ()):
                if isinstance(child, ast.ClassDef):
                    _visit(child, child.name)
                elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    segment = ast.get_source_segment(source, child) or ""
                    for decorator in child.decorator_list:
                        segment += "\n" + (ast.get_source_segment(source, decorator) or "")
                    result[(class_name, child.name)] = _detect_providers_in_text(segment)

        _visit(tree)
    except (SyntaxError, ValueError, RecursionError):
        result = None
    _file_provider_cache[key] = result
    return result


def _detect_providers_for_item(item) -> Set[str]:
    """Provider markers for a single collected item (per test, not per file)."""
    filepath = Path(item.fspath)
    if _is_excluded_path(str(filepath)):
        return set()
    per_test = _build_per_test_provider_map(filepath)
    if per_test is None:
        return _detect_providers_in_file(filepath)
    parts = item.nodeid.split("::")[1:]
    if not parts:
        return _detect_providers_in_file(filepath)
    func = parts[-1].split("[")[0]
    cls = parts[-2] if len(parts) >= 2 else None
    if (cls, func) in per_test:
        return set(per_test[(cls, func)])
    if (None, func) in per_test:
        return set(per_test[(None, func)])
    # Dynamically generated item we cannot locate in the AST: stay conservative.
    return _detect_providers_in_file(filepath)
```

Add `import ast`, a `_file_provider_cache: Dict[str, Optional[Dict[tuple, Set[str]]]] = {}` next to
`_file_content_cache` (line 46), and clear it in `pytest_configure` (186) and
`pytest_sessionfinish` (294).

### Sub-change 2 — `offline` opt-out, and pin `network` to the file

Replace lines 213–230 with a version that (a) honours an explicit `offline` marker, (b) calls
`_detect_providers_for_item`, and (c) **keeps `network` whole-file derived**:

```python
                offline = 'offline' in existing_markers
                if not offline:
                    detected_providers = _detect_providers_for_item(item)
                    for marker, pattern in PROVIDER_PATTERNS.items():
                        if pattern.search(item.nodeid):
                            detected_providers.add(marker)
                    for provider in detected_providers:
                        if provider not in existing_markers:
                            item.add_marker(getattr(pytest.mark, provider))
                    # The `network` marker stays WHOLE-FILE derived. Narrowing
                    # the provider markers must not, by itself, un-deselect a
                    # test that is really live -- only `offline` does that.
                    if _detect_providers_in_file(filepath) and 'network' not in existing_markers:
                        item.add_marker(pytest.mark.network)
```

**Why `network` stays file-derived — this is the whole backward-compatibility story and is not
optional.** Measured: if per-test narrowing were also allowed to narrow `network`, **48 currently-
deselected integration tests would newly select, 25 of them with no `skipif` — they would actually
execute**, across nine files including `test_rag_live.py` and `test_model_routing_real.py`, in a
suite where the network guard is disabled for everything under `/integration/`
(`network_guard.py:103-105`). Pinning `network` to the file makes sub-change 1 provably
**selection-neutral** under every existing `-m` expression, while still making `-m provider_ollama`
mean what it says.

Register the marker in both `pytest.ini` files and `tests/conftest.py`:
```
    offline: Fully mocked - opt out of provider/network auto-marking
```

### Sub-change 3 — opt the file in, and make it guard its bug

Add `pytestmark = pytest.mark.offline` plus a response factory:

```python
def make_completion_response(text="Test response"):
    """A litellm.completion stand-in the LLM tool-calling loop can consume.

    A bare dict is NOT sufficient: the loop reads ``.choices[0].message`` and a
    dict raises ``'str' object has no attribute 'choices'``.
    """
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = text
    resp.choices[0].message.tool_calls = None
    resp.choices[0].finish_reason = "stop"
    return resp
```

For each of the four broken tests: replace the dict `return_value` with
`make_completion_response(...)`, pass `stream=False` to `get_response`, and replace
`mock_completion.assert_called()` with a real kwarg assertion:

```python
        kwargs = mock_completion.call_args.kwargs
        assert kwargs['base_url'] == 'http://localhost:4000'
        assert kwargs['api_key'] == 'sk-test'
        assert kwargs['model'] == 'openai/mistral'
```

- `test_koboldcpp_specific_scenario` → `kwargs['base_url'] == "http://127.0.0.1:5001/v1"`
- `test_litellm_documentation_example_compatibility` → `kwargs['base_url'] == "http://0.0.0.0:4000"`
- `test_ollama_environment_variable_compatibility` → `kwargs['model'] == 'ollama/llama2'` **and**
  `'base_url' not in kwargs` (none was configured; the env path must not inject one)

All four were run standalone against `main` and pass. Leave the three currently-passing tests alone.

Update the stale module docstring ("maps base_url to api_base" → "base_url must reach litellm") but
**do not rename the test functions** — the nodeids are referenced in issue discussion, and renaming
would change what the nodeid scan at plugin lines 224–226 sees.

---

## 5. Backward-compatibility contract

Baseline, measured (`tests/integration/`, CI ignores applied): **290 collected, 187 selected,
103 deselected** under the CI marker expression.

> Caveat for the executing agent: a cold first invocation on a fresh interpreter has been observed
> to report `157/260`, apparently an optional-dependency import warming effect. **Run it twice**;
> `187/290/103` is stable from the second run on. Take your own baseline before touching anything.

**Tests whose selection status changes: exactly 7**, all in `test_base_url_api_base_fix.py`, all
deselected → selected. Post-fix expectation: **194/290 (96 deselected)**. Nothing else moves in
either direction — that is what the file-derived `network` guarantees.

Intended change under `-m provider_ollama` (32 → 9):

| file | before | after |
|---|---|---|
| `test_ollama_tool_calling_live.py` | 7 | 7 |
| `test_base_url_api_base_fix.py` | 7 | 0 (`offline`) |
| `test_rag_integration.py` | 11 | 1 |
| `test_setup_integration.py` | 4 | 0 |
| `test_double_api_fix.py` | 3 | 1 |

**The risk, stated plainly.** Un-deselecting tests turns CI red if any fail. **They do: 4 of the 7
fail today** (R4). This is not hypothetical.

**Mitigation — mandatory, not optional: land the gating fix and the four repairs in the same PR.**
Do not merge sub-changes 1+2 with the `pytestmark` but without the repairs. **Quarantining with
`xfail` is explicitly rejected** — the repairs are ~10 lines each, verified working, and an `xfail`
here would recreate the exact defect being fixed (a test that names a bug and does not guard it).

**Escape hatch.** If the 7 prove flaky in CI for a reason not reproducible locally, revert
**sub-change 3 only**. Selection returns to 187/290/103 and the plugin improvements stay.

---

## 6. Tests to add

In `tests/unit/cli/test_test_command.py` (the existing home of gating-plugin tests, and already in
`EXCLUDED_PATHS`, so these cannot be auto-marked by the thing they test), add
`class TestProviderMarkerGranularity` with:

- `test_ollama_does_not_leak_to_sibling_tests` — **THE meta-test.** If this fails, D7 has regressed.
- `test_openai_does_not_leak_to_sibling_tests`
- `test_plain_test_gets_no_provider_markers`
- `test_decorators_are_scanned` — a `@pytest.mark.parametrize("m", ["ollama/llama2"])` must mark it
- `test_unparseable_file_falls_back_to_whole_file` — conservative over-marking on a parse failure
- `test_network_marker_remains_whole_file_derived` — pins the decision that keeps this change
  selection-neutral for the 96 still-deselected tests
- `test_offline_marker_is_registered` — both `pytest.ini` files, or every use warns

No new dependency: `ast`, `tmp_path` and `configparser` are stdlib/pytest builtins.

---

## 7. Verification and acceptance

```bash
# 1. The 7 are now selected
python -m pytest tests/integration/test_base_url_api_base_fix.py -m "$CI_M" --collect-only -q
# expect: 7 selected, 0 deselected

# 2. They pass offline, with no keys and no services
env -u OPENAI_API_KEY -u ANTHROPIC_API_KEY -u OLLAMA_HOST \
  python -m pytest tests/integration/test_base_url_api_base_fix.py -m "$CI_M" -o addopts="" -q
# expect: 7 passed

# 3. Selection neutral everywhere else
python -m pytest tests/integration/ $IG -o addopts="" -q --collect-only -m "$CI_M" | tail -1
# expect: 194/290 tests collected (96 deselected)

# 4. `-m provider_ollama` now means Ollama  -> 7 + 1 + 1, not 32
# 5. Meta-tests pass
# 6. The three CI shards reproduced verbatim do not regress
# 7. The two pytest.ini marker tables stay in sync
```

**Acceptance gate:** `tests/integration/` collects **194/290 (96 deselected)** — exactly seven more
than baseline, all seven from `test_base_url_api_base_fix.py` — **and passes with
`OPENAI_API_KEY`, `ANTHROPIC_API_KEY` and `OLLAMA_HOST` all unset and no Ollama server running.**

**PR title:** `fix(tests): mark provider tests per test function, not per file`

---

## 8. Filed for separate PRs

- **`tests/test_double_api_fix.py`'s mock no longer intercepts.** `llm.py` routes `gpt-4o-mini`
  through `litellm.responses` (`llm.py:6434`), not `litellm.completion`. Forced to run, it makes a
  **real OpenAI request** (verified: 401 for `https://api.openai.com/v1/responses`). Today it is
  masked by an unconditional auto-`skip` — **anyone who "fixes" the skip without fixing the mock
  gets live billed calls.**
- **`network_guard.py` disables itself for `/integration/`, `/e2e/`, `/live/`** (lines 103–105) and
  for any `provider_*`-marked test (96–100). The suite's network blocker does not cover the tests
  most likely to make network calls.
