"""PraisonAI ↔ PraisonAIUI integration layer (Pattern B/C host bootstrap)."""

from .host_app import (
    build_host_app,
    configure_host,
    create_host_app,
    is_legacy_host,
    setup_bridges,
)
from .gateway_host import run_integrated_gateway

__all__ = [
    "build_host_app",
    "configure_host",
    "create_host_app",
    "is_legacy_host",
    "setup_bridges",
    "run_integrated_gateway",
]
