"""
Base framework adapter protocol for PraisonAI wrapper.

Protocol and shared helpers live in praisonaiagents.frameworks; this module
re-exports them and adds wrapper-specific LLM resolution via PraisonAIModel.
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from typing import Any, Callable, Dict, List, Optional

from praisonaiagents.frameworks.base import BaseFrameworkAdapter as _CoreBaseFrameworkAdapter
from praisonaiagents.frameworks.protocols import FrameworkAdapterProtocol

# Backward-compatible alias used across the wrapper
FrameworkAdapter = FrameworkAdapterProtocol

logger = logging.getLogger(__name__)

# Extended YAML fields each backend actually consumes. Only ``framework:
# praisonai`` honours the full wrapper feature set (approval, guardrails,
# autonomy, ...); the other backends read a hand-picked subset. Anything a YAML
# declares that the target adapter does not read is silently dropped today, so
# warn the user rather than let a safety-relevant field (e.g. ``approval``) be
# ignored without any diagnostic.
_AUTOGEN_SUPPORTED = {"llm", "function_calling_llm"}
_ADAPTER_SUPPORTED_FIELDS: Dict[str, set] = {
    "crewai": {
        "allow_delegation", "max_iter", "max_rpm", "max_execution_time",
        "verbose", "cache", "system_template", "prompt_template",
        "response_template", "llm", "function_calling_llm",
    },
    "autogen": _AUTOGEN_SUPPORTED,
    "autogen_v2": _AUTOGEN_SUPPORTED,
    "autogen_v4": _AUTOGEN_SUPPORTED,
    "ag2": _AUTOGEN_SUPPORTED,
}

# Structural keys handled by the spec builder itself — never "unsupported".
_STRUCTURAL_FIELDS = {"tools", "tasks", "role", "goal", "backstory"}


def warn_unsupported_fields(adapter_name: str, spec_extras: Dict[str, Any]) -> None:
    """Warn once per agent when a backend ignores declared YAML fields.

    Non-breaking: pure visibility. ``framework: praisonai`` is treated as
    supporting everything, so no warning is emitted there.
    """
    if adapter_name not in _ADAPTER_SUPPORTED_FIELDS:
        return
    supported = _ADAPTER_SUPPORTED_FIELDS[adapter_name]
    declared = set(spec_extras.keys())
    unhandled = declared - supported - _STRUCTURAL_FIELDS
    if unhandled:
        logger.warning(
            "framework=%r ignores YAML field(s) %s for agent %r; "
            "these are only honoured by framework=praisonai.",
            adapter_name, sorted(unhandled), spec_extras.get("role"),
        )


class BaseFrameworkAdapter(_CoreBaseFrameworkAdapter):
    """Wrapper base adapter with PraisonAIModel LLM resolution for CrewAI etc."""

    # CLI runtime capabilities are opt-in. Adapters that do not implement
    # these contracts must fail before dispatch instead of silently ignoring
    # session or structured-stream flags.
    SUPPORTS_SESSION_CONTINUITY = False
    SUPPORTS_STREAM_BRIDGE = False

    def _resolve_llm(self, spec: Any, llm_config: Optional[List[Dict]]):
        """Build a provider model object from spec and shared llm_config."""
        from ..inc import PraisonAIModel

        # Delegate model-name precedence to core (single source of truth); core
        # returns the model string and discards base/key by design, so we derive
        # them locally and upgrade to a provider object.
        model = super()._resolve_llm(spec, llm_config)

        base = key = None
        if llm_config and len(llm_config) > 0:
            base = llm_config[0].get("base_url")
            key = llm_config[0].get("api_key")

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
