"""Backward-compatibility shim for :mod:`praisonai.cli.config_loader`."""

import sys as _sys

import praisonai_code.cli.config_loader as _impl

_sys.modules[__name__] = _impl
