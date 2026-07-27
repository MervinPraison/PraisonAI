"""Skip MCP wrapper unit tests cleanly when ``praisonai_mcp`` is unavailable.

These tests import the C12 backward-compat shim
(``praisonai.mcp_server`` -> ``praisonai_mcp.mcp_server``). When the sibling
``praisonai-mcp`` package is neither installed nor present as a monorepo
checkout, the shim raises ``ModuleNotFoundError`` at import time and pytest
reports a collection *error* rather than a skip. ``ensure_praisonai_mcp()``
first restores the monorepo dev layout; if the package is still missing we
ignore this directory so contributors running ``pip install -e src/praisonai``
without the sibling get a clean skip instead of a collection error.
"""

import importlib.util

from praisonai._bootstrap import ensure_praisonai_mcp

ensure_praisonai_mcp()

collect_ignore_glob: list[str] = []

if importlib.util.find_spec("praisonai_mcp") is None:
    collect_ignore_glob.append("*")
