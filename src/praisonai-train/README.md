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

Add a language/domain by registering a `Recipe`, or a new QC rule by registering a
`RowCheck` (see `praisonai_train/data/`), and they show up automatically.
