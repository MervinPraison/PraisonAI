"""Backward-compatibility shim for :mod:`praisonai.cli.branding`."""

import sys as _sys

import praisonai_code.cli.branding as _impl

_sys.modules[__name__] = _impl
