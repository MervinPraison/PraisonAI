"""Connect editors and agents (Cursor, VS Code, Claude, Codex…) to PraisonAI.

``praisonai connect`` uses this package; PraisonAIUI's Connect page renders
:func:`export_catalog`.
"""

from .catalog import CLIENTS, Client, ServerSpec, export_catalog, get_client, local_spec

__all__ = ["CLIENTS", "Client", "ServerSpec", "export_catalog", "get_client", "local_spec"]
