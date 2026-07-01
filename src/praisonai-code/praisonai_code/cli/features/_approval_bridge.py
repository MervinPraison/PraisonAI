"""Bridge to wrapper-only approval feature (optional ``pip install praisonai``)."""

from __future__ import annotations

from typing import Any


def resolve_approval_config(*args: Any, **kwargs: Any) -> Any:
    """Resolve approval config via the wrapper approval feature."""
    from praisonai_code._wrapper_bridge import import_wrapper_module

    mod = import_wrapper_module("praisonai.cli.features.approval")
    return mod.resolve_approval_config(*args, **kwargs)


def resolve_approval_backend(*args: Any, **kwargs: Any) -> Any:
    """Resolve approval backend via the wrapper approval feature."""
    from praisonai_code._wrapper_bridge import import_wrapper_module

    mod = import_wrapper_module("praisonai.cli.features.approval")
    return mod.resolve_approval_backend(*args, **kwargs)
