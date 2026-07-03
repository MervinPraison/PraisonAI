"""Backward-compatibility shim → :mod:`praisonai_bot.integration.gateway_host`."""
import sys as _sys

from praisonai._bootstrap import ensure_praisonai_bot

ensure_praisonai_bot()
import praisonai_bot.integration.gateway_host as _impl

_sys.modules[__name__] = _impl
