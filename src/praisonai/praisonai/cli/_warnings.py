"""Backward-compatibility shim for :mod:`praisonai.cli._warnings`."""

import sys as _sys

import praisonai_code.cli._warnings as _impl

_sys.modules[__name__] = _impl

_parent_name, _, _child_name = __name__.rpartition(".")
if _parent_name and _parent_name in _sys.modules:
    setattr(_sys.modules[_parent_name], _child_name, _impl)
