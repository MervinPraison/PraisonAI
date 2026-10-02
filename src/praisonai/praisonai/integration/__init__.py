"""PraisonAI ↔ PraisonAIUI integration layer (Pattern B/C host bootstrap)."""

from .host_app import (
    build_host_app,
    configure_host,
    create_host_app,
    is_legacy_host,
    setup_bridges,
)

__all__ = [
    "build_host_app",
    "configure_host",
    "create_host_app",
    "is_legacy_host",
    "setup_bridges",
    "run_integrated_gateway",
]


def __getattr__(name):
    if name == "run_integrated_gateway":
        from .gateway_host import run_integrated_gateway

        return run_integrated_gateway
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
