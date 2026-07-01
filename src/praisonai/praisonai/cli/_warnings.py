"""Backward-compatibility shim for :mod:`praisonai.cli._warnings`."""

import sys as _sys

import praisonai_code.cli._warnings as _impl

_sys.modules[__name__] = _impl
