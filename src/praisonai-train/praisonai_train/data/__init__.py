"""Dataset tooling for praisonai-train: synthetic generation + quality control.

Protocol-driven and extendable: recipes and QC checks self-register (see
``registry``), and everything is YAML-configurable via the ``generate`` /
``validate`` CLI commands.
"""
from praisonai_train.data import checks as _checks  # noqa: F401  registers checks
from praisonai_train.data import recipes as _recipes  # noqa: F401  registers recipes
from praisonai_train.data.generate import generate_dataset
from praisonai_train.data.qc import filter_rows, score
from praisonai_train.data.registry import checks, recipes

__all__ = ["generate_dataset", "score", "filter_rows", "recipes", "checks"]
