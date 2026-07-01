"""Backward-compatibility shim for :mod:`praisonai.cli.app`.

The implementation moved to :mod:`praisonai_code.cli.app` (praisonai-code C5).
"""

import sys as _sys

import praisonai_code.cli.app as _impl

_sys.modules[__name__] = _impl
