"""Backward-compatibility shim for :mod:`praisonai.cli.schedule_cli`."""

import sys as _sys

import praisonai_code.cli.schedule_cli as _impl

_sys.modules[__name__] = _impl
