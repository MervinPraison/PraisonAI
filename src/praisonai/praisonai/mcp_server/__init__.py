"""C12 shim: MCP server implementation moved to ``praisonai_mcp.mcp_server``."""

from praisonai._bootstrap import ensure_praisonai_mcp

ensure_praisonai_mcp()

from praisonai.cli._shim import alias_package

alias_package("praisonai.mcp_server", "praisonai_mcp.mcp_server")
