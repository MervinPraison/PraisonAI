"""Backward-compatibility shim for :mod:`praisonai._framework_availability`.

The implementation moved to :mod:`praisonai_code._framework_availability` (C7).
"""

import sys as _sys

from praisonai._bootstrap import ensure_praisonai_code

ensure_praisonai_code()

import praisonai_code._framework_availability as _impl

_sys.modules[__name__] = _impl
