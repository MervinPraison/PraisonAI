"""Workflow YAML framework field validation."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional  # noqa: F401

logger = logging.getLogger(__name__)


def validate_workflow_framework(
    framework: Optional[str],
    *,
    source: str = "workflow YAML",
    registry: Any = None,
) -> None:
    """
    Warn then fail when a workflow file declares a framework whose adapter does
    not advertise workflow support.

    Instead of hardcoding ``framework == "praisonai"``, ask the adapter via its
    ``SUPPORTS_WORKFLOW`` capability flag. Third-party adapters registered via
    the ``praisonai.framework_adapters`` entry-point group can opt in by setting
    ``SUPPORTS_WORKFLOW = True``. The native ``praisonai`` adapter sets it, so
    behaviour is unchanged for existing configs.
    """
    if not framework:
        return

    # Consult the adapter's capability flag. If resolution fails for any reason,
    # fall back to the historical native-only behaviour.
    try:
        if registry is None:
            from .registry import get_default_registry

            registry = get_default_registry()
        adapter = registry.create(framework)
        if getattr(adapter, "SUPPORTS_WORKFLOW", False):
            return
    except Exception:
        if str(framework).lower() == "praisonai":
            return

    supported = ""
    try:
        from .registry import list_framework_choices
    except ImportError:
        # Only the registry module being unavailable is tolerated here; genuine
        # discovery/initialization errors must surface rather than be masked as
        # a simple unsupported-framework config mistake.
        list_framework_choices = None  # type: ignore[assignment]

    if list_framework_choices is not None:
        choices = [f for f in list_framework_choices(include_unavailable=True) if f != "praisonai"]
        if choices:
            supported = f" Available registered frameworks: {', '.join(sorted(choices))}."

    message = (
        f"framework='{framework}' in {source} is not supported for workflow execution. "
        "Native PraisonAI Workflow engine only supports framework='praisonai'. "
        "Use a non-workflow agents.yaml with a supported registered framework, "
        f"or set framework: praisonai.{supported}"
    )
    logger.warning(message)
    raise ValueError(message)


def framework_from_config(config: Dict[str, Any]) -> str:
    """Return normalised framework name from a parsed YAML config dict."""
    return str(config.get("framework") or "praisonai").lower()
