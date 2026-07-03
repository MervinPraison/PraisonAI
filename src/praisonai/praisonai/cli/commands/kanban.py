"""Backward-compatibility shim for :mod:`praisonai.cli.commands.kanban`."""
import sys as _sys

from praisonai._bootstrap import ensure_praisonai_bot

ensure_praisonai_bot()
import praisonai_bot.cli.commands.kanban as _impl

_sys.modules[__name__] = _impl
