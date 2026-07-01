"""Backward-compatibility shim for :mod:`praisonai.cli.unified_schema`."""

import sys as _sys

import praisonai_code.cli.unified_schema as _impl

_sys.modules[__name__] = _impl
