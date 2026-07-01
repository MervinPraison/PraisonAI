"""Backward-compatibility shim for :mod:`praisonai.tool_resolver`.

The implementation moved to :mod:`praisonai_code.tool_resolver` (C7).
"""

import sys as _sys

from praisonai._bootstrap import ensure_praisonai_code

ensure_praisonai_code()

import praisonai_code.tool_resolver as _impl

_sys.modules[__name__] = _impl
