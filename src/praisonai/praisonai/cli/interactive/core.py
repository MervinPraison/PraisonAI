"""Backward-compatibility shim for :mod:`praisonai.cli.interactive.core`.

The InteractiveCore implementation now lives resident in ``praisonai-code``
(C8 repatriation). This shim preserves the old ``praisonai.cli.interactive.core``
import path so existing callers and tests keep working.
"""

import sys as _sys

import praisonai_code.cli.interactive.core as _impl

_sys.modules[__name__] = _impl

_parent_name, _, _child_name = __name__.rpartition(".")
if _parent_name and _parent_name in _sys.modules:
    setattr(_sys.modules[_parent_name], _child_name, _impl)
