"""
Gateway status tool for PraisonAI Agents (Issue #3688).

A lightweight, read-only, agent-callable built-in that lets a running agent
inspect its own live self-state — e.g. answer "Are you busy right now?", "How
many conversations are active?", or "Did my earlier note to the ops channel go
out, or is delivery there degraded?".

The gateway already computes this state (per-turn run status, active-session
inventory, delivery/DLQ backlog, degraded owners) and serves it over HTTP/CLI,
but nothing exposed it *to the agent* as a tool. This mirrors ``send_message``:
the tool resolves the live source from the per-turn session context
(``register_gateway_status``), so it has no heavy third-party dependencies.
When no gateway is running (CLI / one-shot runs), it fails cleanly with an
explanatory message instead of raising.

Usage:
    from praisonaiagents import Agent
    from praisonaiagents.tools import gateway_status

    agent = Agent(
        name="assistant",
        instructions="You can inspect and report your own live gateway state.",
        tools=[gateway_status],
    )
    # During a task the model can do:
    #   gateway_status()
"""

from __future__ import annotations

import dataclasses
import json

from praisonaiagents._logging import get_logger

logger = get_logger(__name__)

_NO_GATEWAY_MSG = (
    "No active gateway: gateway_status is only available inside a running "
    "bot/gateway (e.g. Telegram, Slack, Discord). It is unavailable for "
    "CLI/one-shot runs."
)


def gateway_status() -> str:
    """Report the gateway's live self-state (read-only).

    Use this to answer questions about your own current condition — whether you
    are busy or idle, how many conversations are active, the delivery backlog,
    and whether any channel/route is degraded so you can proactively warn the
    user instead of silently under-delivering. Requires a running bot/gateway;
    it is unavailable for plain CLI/one-shot runs.

    Returns:
        A JSON object describing live state, e.g.::

            {"run": "busy", "queued": 2, "active_sessions": 7,
             "sessions_by_channel": {"telegram": 5, "slack": 2},
             "delivery": {"outbox_depth": 0, "dlq": 1,
                          "dead_targets": ["slack:C123"]},
             "degraded": [{"owner": "channel:telegram",
                           "reason": "credential_unavailable"}]}
    """
    try:
        from ..session.context import get_gateway_status

        source = get_gateway_status()
        if source is None:
            return _NO_GATEWAY_MSG

        status = source.snapshot()
        as_dict = getattr(status, "as_dict", None)
        if callable(as_dict):
            payload = as_dict()
        elif dataclasses.is_dataclass(status) and not isinstance(status, type):
            payload = dataclasses.asdict(status)
        else:
            payload = status
        return json.dumps(payload, default=str)
    except Exception as e:
        logger.error("gateway_status failed: %s", e, exc_info=True)
        return f"Error reading gateway status: {e}"


__all__ = ["gateway_status"]
