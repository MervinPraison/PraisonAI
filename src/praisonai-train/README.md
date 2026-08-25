# PraisonAI Train

Training for [PraisonAI](https://github.com/mervinpraison/PraisonAI) — fine-tune LLMs and iteratively train agents, as a standalone package or as part of the full `praisonai` stack.

## What it does

| Command | What happens | Needs GPU/ML deps? |
|---------|--------------|--------------------|
| `praisonai-train agents --input "What is Python?"` | Runs your agent, grades the answer with an LLM judge, feeds suggestions back, repeats | No |
| `praisonai-train agents --input "Explain AI" --human` | Same loop, but **you** give the feedback | No |
| `praisonai-train llm dataset.json` | Fine-tunes an open model (Llama, Qwen, …) on your dataset with [Unsloth](https://github.com/unslothai/unsloth) | Yes |
| `praisonai-train list` / `show` / `apply` | Browse training sessions and apply the best iteration to an agent | No |

## Install

```bash
# Agent training only (lightweight)
pip install praisonai-train

# + LLM fine-tuning (heavy ML stack: torch, unsloth, trl, ...)
pip install "praisonai-train[llm]"

# Or as part of the full PraisonAI stack (same commands via `praisonai train ...`)
pip install "praisonai[train]"
```

GPU setups often prefer the conda installer, which pins CUDA-compatible versions:

```bash
setup-conda-env   # or: bash praisonai_train/setup/setup_conda_env.sh
```

## Quickstart: train an agent in 2 minutes

```bash
export OPENAI_API_KEY=sk-...

# Up to three improvement iterations, LLM-as-judge
praisonai-train agents --input "Explain quantum entanglement to a 10-year-old" --iterations 3

# See what happened
praisonai-train list
praisonai-train show <session-id>

# Apply the best iteration and chat with the improved agent
praisonai-train apply <session-id> --run "And what about Germany?"
```

> **Note:** `--iterations` sets the **maximum** number of training loops. In
> LLM-as-judge mode, training **stops early** when any iteration scores **≥ 9.5**
> (excellent), so easy prompts may finish in a single iteration. Pass
> `--no-early-stop` to force all iterations, or `--verbose` to see when it stops.

Python API:

```python
from praisonaiagents import Agent
from praisonai_train import AgentTrainer, TrainingScenario

agent = Agent(instructions="You are a helpful assistant.")
trainer = AgentTrainer(agent=agent, iterations=3)
trainer.add_scenario(TrainingScenario(id="demo", input_text="What is Python?"))
report = trainer.run()
report.print_summary()
```

## Quickstart: fine-tune an LLM

```bash
pip install "praisonai-train[llm]"

# dataset.json in ShareGPT or Alpaca format; config.yaml is generated if absent
praisonai-train llm dataset.json --model llama-3.1
```

Tuning knobs (LoRA rank, epochs, quantization, Ollama/HuggingFace export) live in `config.yaml` — see the template in `praisonai_train/setup/config.yaml`.

## How it fits the PraisonAI stack

```
praisonaiagents  (core SDK)
   ├── praisonai-code   (terminal CLI)
   ├── praisonai-bot    (bots & gateway)
   └── praisonai-train  (this package)
        └── praisonai   (wrapper: installs everything)
```

- Depends only on `praisonaiagents` — no circular deps, installs standalone.
- With the full stack installed, the same commands are available as `praisonai train ...`.
- Old import paths (`praisonai.train.agents`, `python -m praisonai.train.llm.trainer`) keep working via wrapper shims.

## Development

```bash
# From the monorepo root
cd src/praisonai-train
PYTHONPATH="../praisonai-agents:." python -m pytest tests/unit/train -q

# Import-direction gate (train must not import the wrapper)
bash ../../scripts/check_c10_train_imports.sh
```

Boundary details: `src/praisonai/tests/PRAISONAI_TRAIN_MANIFEST.md`.

## Dataset tooling (generate + validate)

Build and quality-check instruction datasets — protocol-driven and YAML-configurable.

```bash
# Synthesize from a teacher LLM (recipe + diversity axes, JSON mode, dedup, resumable offsets)
praisonai-train generate --config generate.yaml
praisonai-train generate -r tamil -d gpt-4o -n 1000 -o data/tamil.jsonl

# Quality-check / filter (dedup, boilerplate & refusal, script purity, diversity metrics)
praisonai-train validate data/tamil.jsonl --out data/clean.jsonl
```

**Script purity default is Tamil.** The QC filter drops outputs that fall below a
purity floor for a *target Unicode block*, and that block defaults to Tamil
(`script_range: [2944, 3071]  # U+0B80–U+0BFF`, see `praisonai_train/setup/validate.yaml`).
For any other language, set `script_range` in your config (e.g. `[65, 591]` for
Latin) — otherwise non-Tamil outputs are dropped as `low_script_purity`. Like
`generate` and `dedup`, `validate` rewrites `--out` atomically and leaves an
existing file intact when zero rows survive.

Add a language/domain by registering a `Recipe`, or a new QC rule by registering a
`RowCheck` (see `praisonai_train/data/`), and they show up automatically.

## Verify → export → train → re-verify (learn from real agent runs)

Beyond synthetic generation, you can fine-tune on the agent's *own* verified
behaviour. Given a trials report (K scored attempts per case with captured
trajectories), `from-trials` keeps the passing attempts and writes a
trainer-ready dataset — closing the loop from verification to data generation.

```bash
# 1) export the passing attempts as a ShareGPT dataset (+ provenance sidecar)
praisonai-train from-trials trials.json -o data/train.jsonl

# 2) fine-tune with the existing trainer, unchanged
praisonai-train llm data/train.jsonl

# 3) re-run the trials on the fine-tuned model and compare pass-rate to measure gain
```

```python
from praisonai_train.data import export_trials

summary = export_trials(
    report, "data/train.jsonl",
    only_passed=True,     # rejection sampling on the verifier (default)
    frontier_only=True,   # skip saturated / zero-pass cases (default)
)
print(summary)  # written / skipped_failed / skipped_tool_runs / skipped_no_text / ...
```

Selection defaults: unscored attempts are never candidates; `only_passed` keeps
verifier-passed attempts; `frontier_only` restricts to cases with
`0 < pass_rate < 1` (saturated cases add near-duplicates of mastered behaviour,
zero-pass cases have nothing to export); tool-using runs are excluded by default
(`--all`, `--include-saturated` relax these). A `{out}.jsonl.meta.json` sidecar
maps every line to its case id, attempt index and score, and emission order is
deterministic → reproducible files. Add `--qc` to run rows through the QC filter
(dedup, boilerplate/refusal, length, diversity) — the Tamil script-purity check is
skipped here since agent trajectories are English by construction. To re-enable a
script check for another language, pass `qc_cfg` to `export_trials` with a
`script_range` (and/or an explicit `script_drop`/`script_flag`); any of those keys
opts back into the check with the QC filter's own defaults. Use `--format alpaca`
for instruction/input/output.

> **Honest selection:** `only_passed` is *rejection sampling* — it amplifies
> behaviour the agent already produces and inherits any bias in the scorer/judge
> that decided a run "passed". It cannot teach behaviour the agent never
> exhibited; treat it as reinforcing verified wins, not as an oracle.
