"""Backward-compatibility shim for :mod:`praisonai.cli.commands.bot`."""
import sys as _sys

from praisonai._bootstrap import ensure_praisonai_bot

ensure_praisonai_bot()
import praisonai_bot.cli.commands.bot as _impl

_sys.modules[__name__] = _impl
