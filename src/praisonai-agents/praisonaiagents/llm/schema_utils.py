"""Shared schema utilities for LLM tool calling.

This module provides helpers for normalising tool/function schemas so they are
compatible with OpenAI-style function calling across the LLM, OpenAI client and
MCP code paths.

The canonical implementation of ``fix_array_schemas`` now lives in the core
``praisonaiagents.tools.schema`` module; it is re-exported here so existing
LLM/OpenAI-client/MCP imports continue to work unchanged.
"""

from ..tools.schema import fix_array_schemas

__all__ = ["fix_array_schemas"]
