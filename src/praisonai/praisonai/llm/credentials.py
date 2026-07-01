"""Backward-compatibility shim for :mod:`praisonai.llm.credentials`.

The implementation moved to :mod:`praisonai_code.llm.credentials` (C7).
"""

import sys as _sys

from praisonai._bootstrap import ensure_praisonai_code

ensure_praisonai_code()

import praisonai_code.llm.credentials as _impl

_sys.modules[__name__] = _impl
