"""Backward-compatibility shim for :mod:`praisonai.cli.fallback_schema`."""

import sys as _sys

import praisonai_code.cli.fallback_schema as _impl

_sys.modules[__name__] = _impl
