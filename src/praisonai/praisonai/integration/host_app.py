"""Backward-compatibility shim → :mod:`praisonai_bot.integration.host_app`."""
import sys as _sys

from praisonai._bootstrap import ensure_praisonai_bot

ensure_praisonai_bot()
import praisonai_bot.integration.host_app as _impl

_sys.modules[__name__] = _impl
