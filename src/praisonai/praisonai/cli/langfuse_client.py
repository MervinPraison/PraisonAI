"""Backward-compatibility shim for :mod:`praisonai.cli.langfuse_client`."""

import sys as _sys

import praisonai_code.cli.langfuse_client as _impl

_sys.modules[__name__] = _impl
