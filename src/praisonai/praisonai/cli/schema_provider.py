"""Backward-compatibility shim for :mod:`praisonai.cli.schema_provider`."""

import sys as _sys

import praisonai_code.cli.schema_provider as _impl

_sys.modules[__name__] = _impl
