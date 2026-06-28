"""Workflow YAML framework field validation."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def validate_workflow_framework(
    framework: Optional[str],
    *,
    source: str = "workflow YAML",
) -> None:
    """
    Warn then fail when a workflow file declares a non-native framework.

    Multi-framework workflow dispatch is not implemented; only agents.yaml
    via AgentsGenerator supports framework != praisonai today.
    """
    if not framework or str(framework).lower() == "praisonai":
        return

    supported = ""
    try:
        from .registry import list_framework_choices

        choices = [f for f in list_framework_choices(include_unavailable=True) if f != "praisonai"]
        if choices:
            supported = f" Available registered frameworks: {', '.join(sorted(choices))}."
    except Exception:
        pass

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
