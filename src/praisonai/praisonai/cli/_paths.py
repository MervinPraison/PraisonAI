"""Backward-compatibility shim for :mod:`praisonai.cli._paths`."""

import sys as _sys

import praisonai_code.cli._paths as _impl

_sys.modules[__name__] = _impl
