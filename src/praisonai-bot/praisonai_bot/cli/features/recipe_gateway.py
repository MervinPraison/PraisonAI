"""Recipe runner gateway — ``praisonai serve recipe`` implementation."""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


def run_recipe_gateway(
    *,
    host: str,
    port: int,
    recipe_name: str,
) -> int:
    """Launch a WebSocket gateway with a single recipe-backed agent.

    Returns a CLI exit code (0 success, 1 error, 2 validation).
    """
    if not recipe_name:
        return 2

    try:
        from praisonai_bot.gateway import WebSocketGateway
        from praisonaiagents.gateway.adapters.recipe_adapter import RecipeBotAdapter

        async def _run() -> None:
            gateway = WebSocketGateway(host=host, port=port)
            agent = RecipeBotAdapter(recipe_name=recipe_name)
            gateway.register_agent(agent)
            await gateway.start()

        asyncio.run(_run())
        return 0
    except ImportError as exc:
        logger.error("Missing dependency for recipe gateway: %s", exc)
        return 1
    except Exception as exc:
        logger.error("Recipe gateway failed: %s", exc)
        return 1
