"""Pattern C — integrated AIUIGateway launcher."""

from __future__ import annotations

from typing import Any, Optional


async def run_integrated_gateway(
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
