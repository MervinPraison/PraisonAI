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
    ``SUPPORTS_WORKFLOW`` capability flag through ``adapter_capability``. Third-
    party adapters registered via the ``praisonai.framework_adapters`` entry-
    point group can opt in by setting ``SUPPORTS_WORKFLOW = True``. The native
    ``praisonai`` adapter sets it, so behaviour is unchanged for existing
    configs. A transient resolution failure no longer silently demotes a
    third-party adapter to the native-only name check.
    """
    if not framework:
        return

    from .registry import adapter_capability

    # Consult the adapter's capability flag (memoised). ``True`` means supported;
    # ``False``/``None`` fall through to the guidance below.
    if adapter_capability(framework, "SUPPORTS_WORKFLOW", registry=registry) is True:
        return

    # Discover the set of frameworks whose adapters advertise workflow support,
    # so the guidance reflects capability flags rather than assuming praisonai
    # is the only valid choice.
    supported = ""
    workflow_frameworks: list[str] = []
    try:
        from .registry import list_framework_choices
    except ImportError:
        # Only the registry module being unavailable is tolerated here; genuine
        # discovery/initialization errors must surface rather than be masked as
        # a simple unsupported-framework config mistake.
        list_framework_choices = None  # type: ignore[assignment]

    if list_framework_choices is not None:
        for name in list_framework_choices(include_unavailable=True):
            if adapter_capability(name, "SUPPORTS_WORKFLOW", registry=registry) is True:
                workflow_frameworks.append(name)
        if workflow_frameworks:
            supported = (
                f" Frameworks supporting workflow execution: "
                f"{', '.join(sorted(set(workflow_frameworks)))}."
            )

    message = (
        f"framework='{framework}' in {source} is not supported for workflow execution. "
        "The workflow engine requires an adapter whose SUPPORTS_WORKFLOW flag is set "
        "(the native 'praisonai' adapter does). "
        "Use a non-workflow agents.yaml with a supported registered framework, "
        f"or set framework: praisonai.{supported}"
    )
    logger.warning(message)
    raise ValueError(message)


def framework_from_config(config: Dict[str, Any]) -> str:
    """Return normalised framework name from a parsed YAML config dict."""
    return str(config.get("framework") or "praisonai").lower()
