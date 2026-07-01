"""Backward-compatibility shim for :mod:`praisonai.tool_registry`.

The implementation moved to :mod:`praisonai_code.tool_registry` (C7).
"""

import sys as _sys

from praisonai._bootstrap import ensure_praisonai_code

ensure_praisonai_code()

import praisonai_code.tool_registry as _impl

_sys.modules[__name__] = _impl
