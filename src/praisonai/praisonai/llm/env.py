"""Backward-compatibility shim for :mod:`praisonai.llm.env`.

The implementation moved to :mod:`praisonai_code.llm.env` (C7).
"""

import sys as _sys

from praisonai._bootstrap import ensure_praisonai_code

ensure_praisonai_code()

import praisonai_code.llm.env as _impl

_sys.modules[__name__] = _impl
