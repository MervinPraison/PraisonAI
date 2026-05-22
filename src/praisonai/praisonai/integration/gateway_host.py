"""Pattern C — integrated AIUIGateway launcher."""

from __future__ import annotations

import asyncio
from typing import Any, Optional


async def _run_integrated_gateway_async(
    *,
    port: int = 8080,
    host: str = "127.0.0.1",
    static_dir: Optional[str] = None,
    ui_config: Optional[dict[str, Any]] = None,
    **configure_kwargs: Any,
) -> None:
    """Start ``AIUIGateway`` after ``configure_host()`` (Pattern B/C parity)."""
    from praisonai.integration.host_app import configure_host
    from praisonaiui.integration import AIUIGateway

    configure_host(**configure_kwargs)
    gateway = AIUIGateway(
        host=host,
        port=port,
        static_dir=static_dir,
        ui_config=ui_config or {},
    )
    await gateway.start()


def run_integrated_gateway(
    *,
    port: int = 8080,
    host: str = "127.0.0.1",
    static_dir: Optional[str] = None,
    ui_config: Optional[dict[str, Any]] = None,
    **configure_kwargs: Any,
) -> None:
    """Sync wrapper for integrated gateway (for CLI usage)."""
    asyncio.run(_run_integrated_gateway_async(
        port=port,
        host=host,
        static_dir=static_dir,
        ui_config=ui_config,
        **configure_kwargs
    ))


# Alias for backward compatibility
async def run_integrated_gateway_async(**kwargs) -> None:
    """Async version (for direct usage)."""
    await _run_integrated_gateway_async(**kwargs)
