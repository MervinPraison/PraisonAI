# praisonai-train Boundary Manifest (C10 — implemented)

> **Status:** Implemented in C10. PyPI package `praisonai-train` (0.0.1+). Wrapper shims preserve `praisonai.train.*`, `praisonai.train_vision`, `praisonai.upload_vision`, and `praisonai.cli.commands.train` imports.

## Five-package stack

```
praisonaiagents → praisonai-code + praisonai-bot + praisonai-train → praisonai (wrapper)
```

## Two training modes (both in `praisonai-train`)

| Mode | Entry | Heavy deps? |
|------|-------|-------------|
| LLM fine-tuning | `praisonai train llm` / `python -m praisonai_train.train.llm.trainer` | Yes — lazy; `pip install "praisonai-train[llm]"` or `praisonai_train/setup/setup_conda_env.sh` |
| Agent training | `praisonai train agents` (LLM-as-judge / `--human`) | No — only `praisonaiagents` |

## Owned by `praisonai-train` (`praisonai_train/`)

### Runtime

| Path | Notes |
|------|-------|
| `praisonai_train/train/llm/trainer.py` | Unsloth LLM fine-tuner (`TrainModel`); ML deps lazy |
| `praisonai_train/train/agents/*` | `AgentTrainer`, grader, models, hook, storage |
| `praisonai_train/train/_ollama.py` | Ollama model create/push helper |
| `praisonai_train/train_vision.py` | Vision-language fine-tuner (invoked as script) |
| `praisonai_train/upload_vision.py` | HF/Ollama upload for vision models |
| `praisonai_train/setup/*` | Conda training-env installer + `config.yaml` template |
| `praisonai_train/cli/commands/train.py` | Typer group: `llm`, `agents`, `list`, `show`, `apply` |
| `praisonai_train/cli/output/console.py` | Fallback output controller (delegates to code tier when co-installed) |
| `praisonai_train/_code_bridge.py` / `_wrapper_bridge.py` | Lazy cross-tier access (never PyPI deps) |

### Console script

`praisonai-train = praisonai_train.__main__:main` — standalone CLI exposes the train Typer group directly.

## Wrapper shims (backward compat)

| Shim | Target |
|------|--------|
| `praisonai/train/__init__.py` | `alias_package("praisonai.train", "praisonai_train.train")` |
| `praisonai/cli/commands/train.py` | `sys.modules[__name__] = praisonai_train.cli.commands.train` |
| `praisonai/train_vision.py` | `sys.modules[__name__] = praisonai_train.train_vision` |
| `praisonai/upload_vision.py` | `sys.modules[__name__] = praisonai_train.upload_vision` |
| `praisonai/setup/setup_conda_env.py` | re-export `praisonai_train.setup.setup_conda_env.main` (keeps `setup-conda-env` entry point) |
| `praisonai/train.py` | pre-existing script-only shadow module; resolves through the package shim |

## Stays in `praisonaiagents`

| Path | Notes |
|------|-------|
| `praisonaiagents.eval.grader` | `BaseLLMGrader`, `GradeResult` (used by train grader) |
| `praisonaiagents.storage.*` | Storage backends used by `TrainingStorage` |

## Stays in `praisonai-code`

- `praisonai_code/cli/app.py` — `_TRAIN_RESIDENT_COMMANDS = {"train"}` routing (loads `praisonai_train.cli.commands.train`; hidden when `train_package_available()` is false)
- `praisonai_code/_train_bridge.py` — lazy code→train access
- `praisonai_code/cli/legacy/praison_ai.py` — legacy `train` dispatch (prefers `praisonai_train`, falls back to wrapper shims)

## Stays in `praisonai` wrapper

- `praisonai/inc/config.py::generate_config` — legacy training-config generator (shared with `agents_generator` / `inbuilt_tools`; candidate for a later C10.x move)
- `praisonai` pyproject extra `train = ["praisonai-train[llm]"]`
- Wrapper base dep: `praisonai-train>=0.0.1`

## Install matrix

| Install | `praisonai train` | `praisonai-train` script | Notes |
|---------|-------------------|--------------------------|-------|
| `pip install praisonai` | ✅ (via routing) | ✅ | full stack |
| `pip install praisonai-code` only | hidden from `--help` | — | `train_package_available()` false |
| `pip install praisonai-train` only | — | ✅ | agent training works; `train llm` legacy dispatch needs praisonai-code |
| `pip install "praisonai[train]"` / `"praisonai-train[llm]"` | ✅ | ✅ | pulls ML stack for fine-tuning |

## Publish order

`praisonaiagents` → `praisonai-code` → `praisonai-bot` → `praisonai-train` → `praisonai` (wrapper pins `praisonai-train>=X`). See `src/praisonai/scripts/publish_all.py` and `.github/workflows/pypi-release.yml`.

## Gates

- `src/praisonai/tests/unit/test_c10_train_backward_compat.py` — module/class identity, lazy imports, routing
- `scripts/check_c10_train_imports.sh` — import-direction gate
- `src/praisonai-train/tests/unit/train/` — unit tests (run standalone with `PYTHONPATH=../praisonai-agents`)
- Standalone smoke in `.github/workflows/test-optimized.yml` (venv: agents + train only)
