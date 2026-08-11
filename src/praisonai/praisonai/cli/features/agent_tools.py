"""
Agent-Centric Tools for PraisonAI Interactive Mode (compatibility shim).

The canonical implementation now lives in
``praisonai_code.cli.features.agent_tools`` as part of the C0–C6 migration.
This module is a thin re-export so that both historical import spellings —

- ``from praisonai.cli.features.agent_tools import create_agent_centric_tools``
  (submodule import), and
- ``from praisonai.cli.features import create_agent_centric_tools``
  (attribute access delegated by ``cli/features/__init__.py``)

— resolve to the *same* single implementation, eliminating the earlier
duplication/drift (e.g. the ACP ``cwd`` forwarding fix).
"""

from praisonai_code.cli.features.agent_tools import (  # noqa: F401
    create_agent_centric_tools,
    get_tool_descriptions,
)

__all__ = [
    "create_agent_centric_tools",
    "get_tool_descriptions",
]
