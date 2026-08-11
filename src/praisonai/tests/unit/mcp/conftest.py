"""Skip MCP wrapper unit tests cleanly when ``praisonai_mcp`` is unavailable.

These tests import the C12 backward-compat shim
(``praisonai.mcp_server`` -> ``praisonai_mcp.mcp_server``). When the sibling
``praisonai-mcp`` package is neither installed nor present as a monorepo
checkout, the shim raises ``ModuleNotFoundError`` at import time and pytest
reports a collection *error* rather than a skip. ``ensure_praisonai_mcp()``
first restores the monorepo dev layout; if the shim's required
``praisonai_mcp.mcp_server`` module is still missing we ignore this directory so
contributors running ``pip install -e src/praisonai`` without the sibling get a
clean skip instead of a collection error.
"""

import importlib.util

from praisonai._bootstrap import ensure_praisonai_mcp

ensure_praisonai_mcp()


def _mcp_available() -> bool:
    """Return True only if the shim's required MCP module can be resolved.

    The tests import ``praisonai.mcp_server.*``, which the C12 shim resolves to
    ``praisonai_mcp.mcp_server``. A partial/incompatible install can expose the
    top-level ``praisonai_mcp`` package while lacking that submodule, so we probe
    the submodule the shim actually needs rather than just the top-level package.
    ``find_spec`` raises ``ModuleNotFoundError`` when the parent package is
    absent and may raise ``ValueError`` for a discoverable-but-broken parent
    (mirroring ``praisonai._bootstrap``); treat both as "not importable".
    """
    try:
        return importlib.util.find_spec("praisonai_mcp.mcp_server") is not None
    except (ImportError, ValueError):
        return False


_MCP_AVAILABLE = _mcp_available()

collect_ignore_glob: list[str] = [] if _MCP_AVAILABLE else ["*"]


def pytest_report_header() -> str | None:
    """Tell contributors why MCP wrapper tests were skipped, if applicable."""
    if not _MCP_AVAILABLE:
        return (
            "praisonai-mcp: not available - skipping MCP wrapper tests "
            "(install `pip install -e src/praisonai-mcp` or use a monorepo checkout)"
        )
    return None
