"""
UI Integrations for PraisonAI Agents

This module provides UI protocol integrations for exposing PraisonAI Agents
via various frontend protocols.

Available integrations:
- agui: AG-UI (Agent-User Interface) protocol for CopilotKit and compatible frontends
"""

from praisonaiagents.ui.agui import AGUI

__all__ = ["AGUI"]
