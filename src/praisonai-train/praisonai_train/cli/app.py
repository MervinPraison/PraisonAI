"""Typer CLI for standalone ``praisonai-train``.

The train command group (``llm``, ``agents``, ``list``, ``show``, ``apply``)
is a single Typer app, so the standalone console script exposes it directly:
``praisonai-train llm dataset.json``, ``praisonai-train agents --input ...``.

Inside the full stack the same app is mounted as ``praisonai train`` via the
``_TRAIN_RESIDENT_COMMANDS`` routing in ``praisonai_code.cli.app``.
"""

from __future__ import annotations

from praisonai_train.cli.commands.train import app
from praisonai_train.cli.commands import data as _data  # noqa: F401  registers generate/validate
from praisonai_train.cli.commands import benchmark as _benchmark  # noqa: F401  registers benchmark

__all__ = ["app"]
