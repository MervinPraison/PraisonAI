"""Pytest configuration for praisonai-bot package tests."""

from __future__ import annotations

import sys
from pathlib import Path

_BOT_ROOT = Path(__file__).resolve().parents[1]
_MONOREPO_SRC = _BOT_ROOT.parent

for _pkg in ("praisonai-agents", "praisonai-code", "praisonai-bot"):
    _path = str(_MONOREPO_SRC / _pkg)
    if _path not in sys.path:
        sys.path.insert(0, _path)
