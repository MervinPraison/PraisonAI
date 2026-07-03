"""Optional L3 page — bot / channel health."""

from __future__ import annotations

import praisonaiui as aiui


@aiui.page("bot-health", title="Bot Health", icon="🤖")
async def bot_health_page():
    """Dashboard page for channel and gateway status."""
    status = {"gateway": "unknown", "channels": []}
    try:
        from praisonaiui.features._gateway_ref import get_gateway

        gw = get_gateway()
        if gw is not None:
            status["gateway"] = "running"
            status["agents"] = gw.list_agents() if hasattr(gw, "list_agents") else []
    except ImportError:
        pass
    return status
