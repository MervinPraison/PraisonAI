"""Workflow YAML framework field validation."""

from __future__ import annotations

from typing import Any, Dict, Optional


def validate_workflow_framework(
    framework: Optional[str],
    *,
    source: str = "workflow YAML",
) -> None:
    """
    Fail fast when a workflow file declares a non-native framework.

    Multi-framework workflow dispatch is not implemented; only agents.yaml
    via AgentsGenerator supports framework != praisonai today.
    """
    if not framework or str(framework).lower() == "praisonai":
        return

    raise ValueError(
        f"framework='{framework}' in {source} is not supported for workflow execution. "
        "Native PraisonAI Workflow engine only supports framework='praisonai'. "
        "Use agents.yaml with framework: crewai|autogen, or set framework: praisonai."
    )


def framework_from_config(config: Dict[str, Any]) -> str:
    """Return normalised framework name from a parsed YAML config dict."""
    return str(config.get("framework") or "praisonai").lower()
