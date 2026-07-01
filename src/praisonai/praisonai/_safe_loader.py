"""Backward-compatibility shim for :mod:`praisonai._safe_loader`.

The implementation moved to :mod:`praisonai_code._safe_loader` (C7).
"""

import sys as _sys

from praisonai._bootstrap import ensure_praisonai_code

ensure_praisonai_code()

import praisonai_code._safe_loader as _impl

_sys.modules[__name__] = _impl
