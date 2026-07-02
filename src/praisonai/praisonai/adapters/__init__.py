"""Wrapper-side adapters for C8.5 CLI protocols."""

from __future__ import annotations

from typing import Any, Optional


class ServeHandlerAdapter:
    """Adapter wrapping ``praisonai.cli.features.serve.handle_serve_command``."""

    def handle(self, args: list[str]) -> int:
        from praisonai.cli.features.serve import handle_serve_command
        return int(handle_serve_command(args) or 0)


def get_template_store() -> Optional[Any]:
    """Return template store when wrapper templates feature is available."""
    try:
        from praisonai.cli.features import templates as templates_mod
        return templates_mod
    except ImportError:
        return None
