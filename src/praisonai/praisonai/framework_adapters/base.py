"""
Base framework adapter protocol for PraisonAI wrapper.

Protocol and shared helpers live in praisonaiagents.frameworks; this module
re-exports them and adds wrapper-specific LLM resolution via PraisonAIModel.
"""

from __future__ import annotations

import threading
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


# Guards the legacy class-level patch path (below). Only used as a fallback when
# a per-instance telemetry object is not available. Reference-counting ensures
# concurrent CrewAI runs do not restore each other's "originals" prematurely.
_CLASS_PATCH_LOCK = threading.Lock()
_CLASS_PATCH_STATE: Dict[int, Dict[str, Any]] = {}

_UNSET = object()


def _noop(*args, **kwargs):
    return None


@contextmanager
def _scoped_instance_disable(telemetry_instance):
    """Shadow inherited telemetry methods on a single instance.

    Race-free by construction: instance attributes are per-object, so concurrent
    runs each patch their own Crew's telemetry instance and the class is never
    mutated.
    """
    saved: Dict[str, Any] = {}

    for name in dir(type(telemetry_instance)):
        if name.startswith("__"):
            continue
        attr = getattr(type(telemetry_instance), name, None)
        if callable(attr):
            saved[name] = telemetry_instance.__dict__.get(name, _UNSET)
            setattr(telemetry_instance, name, _noop)

    try:
        yield
    finally:
        for name, prev in saved.items():
            if prev is _UNSET:
                telemetry_instance.__dict__.pop(name, None)
            else:
                setattr(telemetry_instance, name, prev)


@contextmanager
def _scoped_class_disable(telemetry_class):
    """Fallback: patch the class under a lock with reference counting.

    Used only when a per-instance telemetry object is unavailable. The lock and
    refcount ensure the real methods captured on the *first* enter are the ones
    restored on the *last* exit, eliminating the "originals-of-originals" race.
    """
    key = id(telemetry_class)
    with _CLASS_PATCH_LOCK:
        state = _CLASS_PATCH_STATE.get(key)
        if state is None:
            originals: Dict[str, Any] = {}
            for attr_name in dir(telemetry_class):
                if attr_name.startswith("__"):
                    continue
                attr = getattr(telemetry_class, attr_name)
                if callable(attr):
                    originals[attr_name] = attr
                    setattr(telemetry_class, attr_name, _noop)
            state = {"originals": originals, "count": 0}
            _CLASS_PATCH_STATE[key] = state
        state["count"] += 1

    try:
        yield
    finally:
        with _CLASS_PATCH_LOCK:
            state = _CLASS_PATCH_STATE.get(key)
            if state is not None:
                state["count"] -= 1
                if state["count"] <= 0:
                    for attr_name, original_method in state["originals"].items():
                        setattr(telemetry_class, attr_name, original_method)
                    _CLASS_PATCH_STATE.pop(key, None)


@contextmanager
def scoped_telemetry_disable(telemetry):
    """
    Context manager to temporarily disable telemetry methods.

    Accepts either a telemetry *instance* (preferred — race-free per-instance
    shadowing) or a telemetry *class* (legacy fallback — locked + reference
    counted so concurrent runs cannot corrupt the class).
    """
    if not telemetry:
        yield
        return

    if isinstance(telemetry, type):
        with _scoped_class_disable(telemetry):
            yield
    else:
        with _scoped_instance_disable(telemetry):
            yield
