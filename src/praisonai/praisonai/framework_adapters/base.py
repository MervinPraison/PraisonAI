"""
Base framework adapter protocol for PraisonAI wrapper.

Protocol and shared helpers live in praisonaiagents.frameworks; this module
re-exports them and adds wrapper-specific LLM resolution via PraisonAIModel.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable, Dict, List, Optional

from praisonaiagents.frameworks.base import BaseFrameworkAdapter as _CoreBaseFrameworkAdapter
from praisonaiagents.frameworks.protocols import FrameworkAdapterProtocol

# Backward-compatible alias used across the wrapper
FrameworkAdapter = FrameworkAdapterProtocol


class BaseFrameworkAdapter(_CoreBaseFrameworkAdapter):
    """Wrapper base adapter with PraisonAIModel LLM resolution for CrewAI etc."""

    def _resolve_llm(self, spec: Any, llm_config: Optional[List[Dict]]):
        """Build a provider model object from spec and shared llm_config."""
        from ..inc import PraisonAIModel

        base = llm_config[0].get("base_url") if (llm_config and len(llm_config) > 0) else None
        key = llm_config[0].get("api_key") if (llm_config and len(llm_config) > 0) else None

        if isinstance(spec, str) and spec.strip():
            model = spec.strip()
        elif isinstance(spec, dict) and spec.get("model"):
            model = spec["model"]
        else:
            import os
            model = os.environ.get("MODEL_NAME") or self.DEFAULT_MODEL

        return PraisonAIModel(model=model, base_url=base, api_key=key).get_model()


@contextmanager
def scoped_telemetry_disable(telemetry_class):
    """
    Context manager to temporarily disable telemetry methods.

    Replaces import-time monkey patching with scoped patching
    that is automatically restored after use.
    """
    if not telemetry_class:
        yield
        return

    originals = {}
    noop = lambda *args, **kwargs: None

    for attr_name in dir(telemetry_class):
        attr = getattr(telemetry_class, attr_name)
        if callable(attr) and not attr_name.startswith("__"):
            originals[attr_name] = attr
            setattr(telemetry_class, attr_name, noop)

    try:
        yield
    finally:
        for attr_name, original_method in originals.items():
            setattr(telemetry_class, attr_name, original_method)
