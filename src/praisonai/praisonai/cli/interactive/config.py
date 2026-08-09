"""Backward-compatibility shim for :mod:`praisonai.cli.interactive.config`.

``InteractiveConfig``/``ApprovalMode`` are resident in ``praisonai-code``. This
shim guarantees module *identity* with ``praisonai_code.cli.interactive.config``
so ``isinstance`` checks and monkeypatching work across the old and new import
paths (the resident ``core`` imports ``.config`` = the code module).
"""

import sys as _sys

import praisonai_code.cli.interactive.config as _impl

_sys.modules[__name__] = _impl

_parent_name, _, _child_name = __name__.rpartition(".")
if _parent_name and _parent_name in _sys.modules:
    setattr(_sys.modules[_parent_name], _child_name, _impl)
