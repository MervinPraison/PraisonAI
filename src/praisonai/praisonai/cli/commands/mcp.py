"""C12 shim: implementation moved to ``praisonai_mcp.cli.commands.mcp``."""

import sys as _sys

from praisonai._bootstrap import ensure_praisonai_mcp

ensure_praisonai_mcp()

import praisonai_mcp.cli.commands.mcp as _impl

_sys.modules[__name__] = _impl
