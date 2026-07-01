"""Backward-compatibility shim for :mod:`praisonai.cli.main`.

The implementation moved to :mod:`praisonai_code.cli.main` (praisonai-code C5).
"""

import runpy
import sys as _sys

from praisonai._bootstrap import ensure_praisonai_code

ensure_praisonai_code()

import praisonai_code.cli.main as _impl

_sys.modules[__name__] = _impl

if __name__ == "__main__":
    runpy.run_module("praisonai_code.cli.main", run_name="__main__")
