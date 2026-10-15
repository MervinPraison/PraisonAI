# Cross-framework benchmark

A reproducible harness that measures PraisonAI against other agent frameworks.
Every framework does the same work, against the same local mock LLM, and the
results are published whether PraisonAI wins or loses. The README's
`## ⚡ Performance` table is generated from these results by
[`scripts/proof_points.py`](../../scripts/proof_points.py); it is never typed by hand.

Nothing here is shipped in any package, and the harness adds no runtime dependency to any SDK.
`run.py` and the stub use only the standard library; each framework lives in its
own pinned [uv](https://docs.astral.sh/uv/) project.

```bash
python3 benchmarks/compare/run.py --frozen                     # everything, default sample counts
python3 benchmarks/compare/run.py --frozen --frameworks raw_openai,praisonai --scale 0.1   # smoke
python3 scripts/proof_points.py --write                         # results -> proof points + README
```

## Layout

| Path | Purpose |
|---|---|
| `run.py` | Orchestrator: syncs venvs, starts the stub, runs probes in interleaved rounds, writes `results/<date>.json` and `results/latest.json` |
| `stub/server.py` | OpenAI-compatible stub (`ThreadingHTTPServer`) that records every request |
| `contract.py` | The S4 contract (proof of identical work) |
| `stats.py` | median / p95 / IQR / bootstrap CI, ranking and the "fastest" rule |
| `loc.py` | `tokenize`-based line and token counter |
| `frameworks/<fw>/` | One uv project and lockfile per framework |
| `scenarios/imports.toml` | S1 import statements |
| `scenarios/agent1/<fw>.py` | Single agent: `make_tool()`, `build(tools)`, `ask(agent, prompt)` |
| `scenarios/team3/<fw>.py` | Three-agent pipeline: `build()`, `run(team)` |
| `probes/` | Scripts run inside each framework's venv, one fresh process per sample |
| `results/` | Dated results, `latest.json`, `proof_points.{json,md}` (raw samples go to `results/raw/`, which is git-ignored and uploaded as a CI artifact) |

Frameworks: `praisonai` (path dependency on this checkout's `main`), `praisonai_release`
(latest PyPI release; docs quote this one), `raw_openai` (baseline, never ranked),
`langgraph`, `crewai`, `agno`, `openai_agents`, `autogen`.

## Scenarios

Common settings: `gpt-4o-mini` against the stub, telemetry off, streaming off, and
no memory, retries or tracing unless the scenario says so.

| ID | Metric | Method |
|---|---|---|
| S1 | Cold import | Fresh interpreter per sample, time the statement from `imports.toml`; also `len(sys.modules)` and a `-X importtime` top 20 (artifact). First sample discarded. |
| S2 | Cold time to first response | Fresh interpreter: import, build one agent, one mocked call. Lazy imports cannot hide cost here, so S1 is never published without S2. |
| S3 | Instantiation | One agent with one tool (`get_weather`). Every tool is wrapped by `make_tool()` **outside** the timed region. 50 warm-up + 1000 iterations × 5 processes; the figure is the median of the per-process medians. PraisonAI's historical config (`Agent(name="Test", model="gpt-4o-mini", output="silent")`) is kept as `legacy_praisonai` for continuity. |
| S4 | Per-agent hand-off overhead | Researcher → Writer → Editor, no tools. A fresh team is built per run (`build_ms`, reported separately); only `run()` is timed. `overhead = (median(fw) − median(raw_openai)) / 3`. Request bytes per run are reported too. |
| S5 | Memory per agent | Fresh process; import, 20 warm-up builds, then build and retain K=200 S3 agents. tracemalloc retained bytes / K, and, in a separate process with tracing off, RSS Δ / K. |
| S6 | Lines of code | The S4 `team3/<fw>.py` files, `ruff format --line-length 88`, then physical code lines and tokens. Blank lines, comments, docstrings and lines tagged `# bench:config` (the shared endpoint config) are excluded. Only files that passed the contract are counted. |

**S4 contract** (checked by the stub after every run): exactly 3 chat requests,
all non-streaming; request *i*+1 carries the nonce from reply *i*; the final
output contains nonce 3. A framework that breaks it is reported as
**contract failed** with what was observed. It is never dropped silently and never ranked.

**Idiom rule (S4/S6):** use the shortest idiom in the framework's official docs
at the pinned version, and link that page in the file's header comment. Changes
to a scenario's style need PR review. Idioms: PraisonAI `AgentTeam` (sequential),
LangGraph 3-node `StateGraph`, CrewAI `Process.sequential`, Agno
`Workflow(steps=[…])` (a `Team` leader adds LLM calls), OpenAI Agents SDK chained
`Runner.run_sync` (its handoffs are LLM-driven), AutoGen
`RoundRobinGroupChat(max_turns=3)`.

## Mock LLM

`stub/server.py` is the only layer all frameworks share; each framework still runs its own
real client stack (HTTP, SDK, parsing). It serves:

- `POST /v1/chat/completions`, both JSON and SSE;
- `POST /v1/responses` (minimal);
- `GET /v1/models`.

It replies `Final Answer: NONCE-<n> done.`, putting the nonce after `Final Answer:`
because CrewAI's ReAct parser keeps only the text after that marker. If a request has
`tools` and no `role: "tool"` message, it returns one tool call. `GET /_stats` and
`POST /_reset` expose and clear what it recorded per request:

- path and byte count;
- the `stream` flag and the number of tools;
- the request keys;
- the hand-off check.

| Framework | Wiring |
|---|---|
| PraisonAI | `OPENAI_BASE_URL` (the default OpenAI path; `Agent(base_url=…)` would route through LiteLLM) |
| LangGraph | `ChatOpenAI(base_url=…)` |
| CrewAI | `LLM(model="openai/gpt-4o-mini", base_url=…)` |
| Agno | `OpenAIChat(id=…, base_url=…)` |
| OpenAI Agents SDK | `OpenAIChatCompletionsModel(openai_client=AsyncOpenAI(base_url=…))`, tracing disabled |
| AutoGen | `OpenAIChatCompletionClient(base_url=…)` |
| raw baseline | `OpenAI(base_url=…)` |

**Network isolation.** These layers stack:

1. Telemetry opt-out variables are set for every framework.
2. Proxies point at a closed port, as an egress trap.
3. Each probe installs an audit hook (`probes/_guard.py`) that blocks and records any
   non-loopback `socket.connect`.
4. In CI the run happens inside a loopback-only network namespace (`unshare --net`).

`run.py` exits non-zero if any probe attempted egress. The guard also appends each
attempt to a log file, so a probe that crashes or times out cannot hide one. With
`--strict` (the PR smoke run) it also fails when a framework, probe or contract fails.

## Statistics and publishing rules

- Frameworks run in seeded-random interleaved rounds, so runner drift hits everyone
  equally. On Linux the stub and the probes are pinned to two different CPUs the process
  may use (no pinning with fewer than two).
- GC stays on, and every framework runs in quiet mode.
- The canonical working directory is a fresh temp directory that is **not** a git repo,
  matching deployed apps (`--git-workdir` for the alternative).
- Each metric reports median, p95, IQR, min, max and n, plus a 95% bootstrap CI of the
  median (fixed seed).
- Ranking is by median. Equal medians share a rank.
- Ratios are relative to the **best** framework, never to PraisonAI.
- "Fastest", "lowest" and "fewest" are used only when the leader's CI does not
  overlap the runner-up's. Otherwise first place is "tied for first within noise".
  With fewer than two ranked frameworks there is no label.
- A framework that fails a scenario part-way is not ranked or published for that metric.
- S6 counts lines only after `ruff format`; without `ruff` S6 is not counted.
- Every published number carries the date, versions, machine or runner image, and n.
  The full ranking is shown for every metric, and contract failures are shown as such.
- Numbers are never compared across machines.
- Docs quote the released PraisonAI. Numbers from `main` appear only in the weekly PR summary.

## CI

[`.github/workflows/benchmark-compare.yml`](../../.github/workflows/benchmark-compare.yml):

- **Pull requests:** run the self-tests, `proof_points.py --check`, and a
  `raw_openai` + `praisonai` smoke run.
- **Weekly cron and manual dispatch:**
  1. `uv lock --upgrade` for every framework (unless `frozen`).
  2. The benchmark, inside the loopback-only namespace.
  3. Artifacts are uploaded (results and raw samples; 90 days).
  4. A PR on `bench/weekly` carries the dated results, the regenerated README block and
     the lockfile updates. It never pushes to `main`.
  5. A second PR updates the PraisonAIDocs snippet `docs/snippets/proof-points.mdx`.

## Tests

```bash
uv run --frozen --project benchmarks/compare/frameworks/raw_openai --with pytest pytest benchmarks/compare/tests -q
```
