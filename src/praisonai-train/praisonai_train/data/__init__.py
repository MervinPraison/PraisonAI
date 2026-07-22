"""Dataset tooling for praisonai-train: synthetic generation + quality control.

Protocol-driven and extendable: recipes and QC checks self-register (see
``registry``), and everything is YAML-configurable via the ``generate`` /
``validate`` CLI commands.
"""
from praisonai_train.data import checks as _checks  # noqa: F401  registers checks
from praisonai_train.data import recipes as _recipes  # noqa: F401  registers recipes
from praisonai_train.data.benchmark import BenchResult, benchmark_deployments
from praisonai_train.data.dedup import MinHashLSH, global_dedup, near_dedup
from praisonai_train.data.generate import azure_sponsorship_guard, generate_dataset
from praisonai_train.data.intent import translation_intent
from praisonai_train.data.qc import filter_rows, score
from praisonai_train.data.registry import checks, recipes

__all__ = [
    "BenchResult",
    "MinHashLSH",
    "azure_sponsorship_guard",
    "benchmark_deployments",
    "checks",
    "filter_rows",
    "generate_dataset",
    "global_dedup",
    "near_dedup",
    "recipes",
    "score",
    "translation_intent",
]
