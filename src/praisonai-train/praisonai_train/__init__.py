"""PraisonAI Train — LLM fine-tuning and agent training (Tier 2c).

Extracted from the ``praisonai`` wrapper (C10). Two training modes:

- **LLM fine-tuning** (``praisonai-train llm``): Unsloth-based fine-tuning of
  open models, driven by a ``config.yaml``. Heavy ML deps are lazy — install
  with ``pip install "praisonai-train[llm]"`` or the conda script in
  ``praisonai_train/setup/``.
- **Agent training** (``praisonai-train agents``): iterative LLM-as-judge or
  human-in-the-loop feedback loops. Needs only ``praisonaiagents``.

Old wrapper import paths (``praisonai.train.*``) keep working via shims.
"""

from __future__ import annotations

from praisonai_train._version import __version__

__all__ = [
    "__version__",
    "AgentTrainer",
    "TrainingScenario",
    "TrainModel",
    "apply_training",
    "get_training_profile",
]


def __getattr__(name: str):
    """Lazy top-level exports — never import ML deps at package import time."""
    if name in ("AgentTrainer", "TrainingScenario", "apply_training", "get_training_profile"):
        from praisonai_train.train import agents as _agents

        return getattr(_agents, name)
    if name == "TrainModel":
        from praisonai_train.train.llm import trainer as _trainer

        return _trainer.TrainModel
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
