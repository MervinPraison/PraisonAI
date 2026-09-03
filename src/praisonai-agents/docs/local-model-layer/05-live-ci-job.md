# 05 — Live local-model CI job

**Branch:** `feat/ci-ollama-live-job`
**Depends on:** order `04` must merge first. Before it, `-m provider_ollama` selects 32 tests
across 5 files (25 of which are not Ollama tests) and this job is unbuildable.
**Owns:** `.github/workflows/test-optimized.yml`,
`src/praisonai/tests/integration/test_ollama_tool_calling_live.py`.
**Must not edit:** `test_gating.py` (order 04); the `smoke` / `main` / `openai-live` jobs; anything
in `test-core.yml`; `src/praisonai-agents/tests/test_ollama_{fix,async_fix}.py`.

---

## 1. The suite already exists — and is broken

The audit concluded "no ollama live job, and no live suite". The first half is right; **the second
is wrong**. `src/praisonai/tests/integration/test_ollama_tool_calling_live.py` is 230 lines,
7 tests, gated at lines 19–22 on `PRAISONAI_TEST_OLLAMA`. It has never run anywhere.

Measured against `main`, **it cannot run** — three `Agent()` kwargs are now rejected:

```
$ python -c "from praisonaiagents import Agent; Agent(name='C', llm='ollama/qwen3:0.6b', verbose=True)"
TypeError: Agent.__init__() got unexpected keyword argument(s): verbose
  verbose: verbosity moved into output=; use output='verbose' (or output=OutputConfig(verbose=True)).

$ ... Agent(..., force_tool_usage="always")   -> TypeError: unexpected keyword argument(s): force_tool_usage
$ ... Agent(..., max_tool_repairs=3)          -> TypeError: unexpected keyword argument(s): max_tool_repairs
```

All 7 tests use `verbose=True`; two also use the other two. **Every test errors on construction.**
The modern form, verified working:

```python
Agent(name="C",
      llm={"model": "ollama/qwen3:0.6b", "force_tool_usage": "always", "max_tool_repairs": 3},
      tools=[calculator])
# -> llm_instance.force_tool_usage == 'always', llm_instance.max_tool_repairs == 3
```

So this order is **"fix a dead test file and wire it up"**, not "write a live suite".

---

## 2. Model selection

Measured on a real Ollama 0.33.2 host:

```
$ ollama list
qwen3:0.6b   7df6b6e09427   522 MB
$ ollama show qwen3:0.6b
  parameters       751.63M      quantization  Q4_K_M      context length  40960
  Capabilities:    completion, tools, thinking
```

**Two corrections:** the blob is **522 MB**, not ~400 MB; and it is **not vision capable** —
`completion, tools, thinking` only. Tools + thinking is all this job needs.

**Reliability, measured end-to-end through `praisonaiagents.Agent`:**

| configuration | trials | tool invoked + correct answer | latency |
|---|---|---|---|
| default | 4 | **3/4** — one run returned `{}` with no tool call | 0.5–5.4 s |
| `force_tool_usage="always"`, `temperature=0` | 6 | **6/6** | 0.4–4.0 s |
| indirect prompt ("I know it's easy, but use the tool") | 1 | 0/1 — emitted `{"type": "calculator", ...}`, wrong key | 0.6 s |
| multi-step `(17+25)+(8+9)` | 2 | 1 hung past 90 s; 1 answered 42 instead of 59 | — |

**Conclusion: `qwen3:0.6b` is the right model, but only the forced, zero-temperature, single-call
prompt is CI-deterministic.**

Rejected alternatives: `qwen2.5:0.5b` (~400 MB, older tool calling, unmeasured — no reason to
prefer it over a verified model); `llama3.2:1b` (~1.3 GB, 2.5× the cache for no measured gain);
`smollm2:135m` (**no `tools` capability — disqualifying**); `olmo-3` (the file's current default,
~7B, far too large per run). Keep `olmo-3` as the *local* default so developer workflow is
unchanged; let CI override via env var.

**Cache:** `~/.ollama/models`, keyed `${{ runner.os }}-ollama-models-${{ env.OLLAMA_TEST_MODEL }}`.
**No `restore-keys`** — a partial restore of a *different* model's blobs is worse than a clean
pull, and a stale key would silently test the wrong model.

**Install:** pinned release tarball, not `curl https://ollama.com/install.sh | sh`. The install
script tracks latest, so the job would silently change what it tests, and it pulls GPU runtimes a
CPU-only runner never uses. Expect ~20–60 s tarball + ~30–90 s cold model pull, near-zero on a
cache hit — **the executing agent must confirm real timings on the first green run and write them
into a YAML comment.**

**Gating:** `if: github.event_name == 'schedule' || github.event.inputs.tier == 'extended' ||
github.event.inputs.tier == 'nightly'` — byte-identical to `extended-anthropic` (line 467),
`extended-google` (525), `extended-groq` (585), `extended-xai` (644), `extended-cohere` (703).
**It never runs on a pull request.**

---

## 3. One deliberate departure from the sibling jobs

Every existing live job ends `|| echo "... tests completed"`, so **it can never fail**. That is
defensible for key-dependent jobs — a rotated secret should not page anyone — but it is exactly
the "test that cannot fail" pattern this whole effort exists to remove, and **Ollama needs no
secret**: availability is fully under the job's control.

So the job has **two run steps**:
1. a **required** minimum-contract step with **no `|| echo`**;
2. an **informational** step for the measured-flaky remainder, keeping the sibling style.

**Do not merge them.**

---

## 4. Test-file changes

1. After `pytestmark`, add the model indirection:
   ```python
   # CI overrides this with a small, fast model; local runs keep olmo-3.
   OLLAMA_MODEL = "ollama/" + os.getenv("PRAISONAI_OLLAMA_TEST_MODEL", "olmo-3")
   ```
2. Replace all 7 hard-coded `llm="ollama/olmo-3"` with `llm=OLLAMA_MODEL`.
3. Remove `verbose=True` from all 7 `Agent(...)` calls. Where verbosity is wanted: `output="verbose"`.
4. Move `force_tool_usage="always"` and `max_tool_repairs=3` into an `llm` dict.
5. Add the CI-minimum test as a new first class — **the only assertion in the file with a measured
   6/6 pass rate**:

```python
class TestOllamaCIMinimum:
    """The minimum contract a local model must satisfy: a tool call round-trips.

    Deliberately narrow. Measured on qwen3:0.6b: this exact configuration
    (forced tool usage, temperature 0, single arithmetic step) passed 6/6.
    The default configuration passed 3/4 and multi-step prompts were worse --
    those live in TestOllamaToolCallingLive, which CI runs informationally.
    """

    def test_tool_call_round_trips(self, ollama_available):
        from praisonaiagents import Agent

        invocations = []

        def add(a: int, b: int) -> int:
            """Add two integers together.

            Args:
                a: First number to add
                b: Second number to add
            """
            invocations.append((a, b))
            return a + b

        agent = Agent(
            name="CI Calculator",
            llm={"model": OLLAMA_MODEL, "force_tool_usage": "always", "temperature": 0},
            tools=[add],
        )
        result = agent.chat("Compute 17 + 25. You MUST use the calculator tool.")

        # 1. the model actually called our function, with the right arguments
        assert invocations == [(17, 25)], f"tool was not invoked: {invocations!r}"
        # 2. the tool's return value made it back into the model's answer
        assert "42" in str(result), f"tool result did not round-trip: {result!r}"
```

Reuse the existing `ollama_available` fixture (lines 48–53) — it already probes
`http://localhost:11434/api/tags` and skips cleanly. Do not add a second probe.

### Why both assertions are needed

`qwen3:0.6b` answers `17 + 25 = 42` **correctly with no tools at all** (measured, 1.2 s,
`tools=[]`). So a bare `assert "42" in result` is satisfied by a model that ignores tools entirely.
The `invocations == [(17, 25)]` half is what proves the tool call was emitted, parsed and
dispatched with the right arguments; the `"42"` half proves the return value was fed back and
reached the final answer. Anything beyond this — multi-step chains, repair loops, resisting
distraction — is measured-flaky on a 0.6B model and belongs in the informational step.

---

## 5. The YAML

Insert after `extended-cohere`'s `Skip notice` step (ends line 760), before the `legacy-unit`
banner. Key fragments:

```yaml
  extended-ollama:
    if: github.event_name == 'schedule' || github.event.inputs.tier == 'extended' || github.event.inputs.tier == 'nightly'
    runs-on: ubuntu-latest
    timeout-minutes: 15
    env:
      # Bump deliberately; the cache key and what we test both follow this.
      OLLAMA_VERSION: v0.33.2
      OLLAMA_TEST_MODEL: qwen3:0.6b
    steps:
    - uses: actions/checkout@v4
      with:
        persist-credentials: false
    - name: Set up Python 3.11
      uses: actions/setup-python@v5
      with:
        python-version: '3.11'
    - name: Cache Ollama model blobs
      uses: actions/cache@v4
      with:
        path: ~/.ollama/models
        # No restore-keys: a partial hit from a different model would
        # silently test something other than OLLAMA_TEST_MODEL.
        key: ${{ runner.os }}-ollama-models-${{ env.OLLAMA_TEST_MODEL }}
    - name: Install Ollama
      shell: bash
      run: |
        set -euo pipefail
        curl -fsSL -o /tmp/ollama.tgz \
          "https://github.com/ollama/ollama/releases/download/${OLLAMA_VERSION}/ollama-linux-amd64.tgz"
        sudo tar -C /usr -xzf /tmp/ollama.tgz
        ollama --version
    - name: Start Ollama and pull model
      shell: bash
      run: |
        set -euo pipefail
        ollama serve > /tmp/ollama-serve.log 2>&1 &
        for i in $(seq 1 30); do
          if curl -sf http://127.0.0.1:11434/api/tags > /dev/null; then
            echo "Ollama is up after ${i}s"; break
          fi
          sleep 1
        done
        curl -sf http://127.0.0.1:11434/api/tags > /dev/null
        ollama pull "$OLLAMA_TEST_MODEL"
        ollama list
    - name: Install dependencies
      run: |
        pip install --upgrade pip
        pip install pytest pytest-asyncio pytest-timeout
    - uses: ./.github/actions/install-monorepo-packages
      with:
        agents-extras: ".[all]"
    - name: Run Ollama minimum contract (required)
      env:
        PRAISONAI_TEST_TIER: extended
        PRAISONAI_ALLOW_NETWORK: '1'
        PRAISONAI_LIVE_TESTS: '1'
        PRAISONAI_TEST_PROVIDERS: 'ollama'
        PRAISONAI_TEST_OLLAMA: '1'
        PRAISONAI_OLLAMA_TEST_MODEL: ${{ env.OLLAMA_TEST_MODEL }}
      shell: bash
      run: |
        set -euo pipefail
        cd src/praisonai
        # No "|| echo" here on purpose: no secret is involved, so a failure
        # here is a real regression in local-model tool calling.
        python -m pytest tests/integration/test_ollama_tool_calling_live.py::TestOllamaCIMinimum \
          -m "provider_ollama" -v --tb=short --timeout=120
    - name: Run remaining Ollama live tests (informational)
      if: always()
      env: { ...same... }
      run: |
        cd src/praisonai
        python -m pytest tests/integration/test_ollama_tool_calling_live.py \
          -m "provider_ollama" \
          --deselect tests/integration/test_ollama_tool_calling_live.py::TestOllamaCIMinimum \
          -v --tb=short --timeout=180 \
          || echo "Ollama exploratory tests completed (small models are non-deterministic)"
    - name: Ollama server log
      if: failure()
      run: tail -100 /tmp/ollama-serve.log
```

And in `test-summary` (line 838): extend `needs: [smoke, main, extended-ollama]` and add the
summary rows. `test-summary` is already `if: always()`, so a skipped `extended-ollama` on PRs
reports `skipped` rather than blocking.

---

## 6. Verification and acceptance

```bash
ollama pull qwen3:0.6b
cd src/praisonai && export PYTHONPATH=$(cd ../praisonai-agents && pwd)

# Must be 6/6 before this ships.
for i in $(seq 1 6); do
  PRAISONAI_TEST_OLLAMA=1 PRAISONAI_ALLOW_NETWORK=1 PRAISONAI_LIVE_TESTS=1 \
  PRAISONAI_TEST_PROVIDERS=ollama PRAISONAI_OLLAMA_TEST_MODEL=qwen3:0.6b \
    python -m pytest tests/integration/test_ollama_tool_calling_live.py::TestOllamaCIMinimum \
    -o addopts="" -q --timeout=120 2>&1 | tail -1
done

# The gate still holds with the env var absent:
python -m pytest tests/integration/test_ollama_tool_calling_live.py -o addopts="" -q --collect-only
# expect: collected, all skipped by the module pytestmark

# Nothing leaked onto the PR path:
grep -n "extended-ollama" -A3 .github/workflows/test-optimized.yml | grep "if:"
python -c "import yaml; yaml.safe_load(open('.github/workflows/test-optimized.yml')); print('yaml ok')"

# Then: gh workflow run "Optimized Test Suite" -f tier=extended
```

**Acceptance gate:** a manual `workflow_dispatch` with `tier=extended` shows `extended-ollama`
**green**, with "Run Ollama minimum contract (required)" reporting `1 passed` — **and** the same
workflow triggered by a pull request shows `extended-ollama` **skipped**.

**PR title:** `ci: add nightly live-Ollama job exercising a real local model`
