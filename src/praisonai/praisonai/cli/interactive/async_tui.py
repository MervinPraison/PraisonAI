"""Backward-compatibility shim for :mod:`praisonai.cli.interactive.async_tui`.

The async split-pane TUI now lives resident in ``praisonai-code`` (C8
repatriation), so ``pip install praisonai-code`` alone yields a full
interactive ``chat``/``code`` session. This shim preserves the old
``praisonai.cli.interactive.async_tui`` import path for back-compat.
"""

import sys as _sys

import praisonai_code.cli.interactive.async_tui as _impl

_sys.modules[__name__] = _impl

_parent_name, _, _child_name = __name__.rpartition(".")
if _parent_name and _parent_name in _sys.modules:
    setattr(_sys.modules[_parent_name], _child_name, _impl)
