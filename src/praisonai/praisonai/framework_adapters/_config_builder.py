"""Canonical YAML -> intermediate AgentSpec/TaskSpec converter.

The YAML -> framework-object normalization is a wrapper-level concern, not an
adapter concern. Hoisting it here keeps the per-adapter ``run()`` methods thin
translators and gives every framework the *same* defaults for the *same* YAML
(no more silent default-vs-raise divergence across adapters). New YAML fields
are added to ``AgentSpec`` / ``TaskSpec`` once instead of in N adapters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List


@dataclass
class TaskSpec:
    """Framework-agnostic description of a single task."""

    name: str
    description: str
    expected_output: str = "Task completed successfully."
    tools: List[Any] = field(default_factory=list)
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentSpec:
    """Framework-agnostic description of a single agent and its tasks."""

    key: str
    role: str
    goal: str
    backstory: str
    tools: List[Any] = field(default_factory=list)
    tasks: List[TaskSpec] = field(default_factory=list)
    extras: Dict[str, Any] = field(default_factory=dict)


def _resolve_tools(names, tools_dict: Dict[str, Callable]) -> List[Any]:
    """Resolve tool name references against ``tools_dict``.

    Already-callable entries pass through unchanged so YAML that embeds tool
    objects directly keeps working.
    """
    resolved: List[Any] = []
    for item in names or []:
        if isinstance(item, str):
            if tools_dict and item in tools_dict:
                resolved.append(tools_dict[item])
        elif callable(item):
            resolved.append(item)
    return resolved


def build_agent_specs(
    config: Dict[str, Any],
    topic: str,
    tools_dict: Dict[str, Callable],
    format_template: Callable[..., str],
) -> List[AgentSpec]:
    """Single canonical YAML -> AgentSpec/TaskSpec converter.

    Uses the inherited safe ``_format_template`` (passed as ``format_template``)
    exactly once per field so JSON-like braces are preserved consistently across
    every framework.
    """
    specs: List[AgentSpec] = []
    tools_dict = tools_dict or {}

    for key, details in (config.get("roles") or {}).items():
        details = details or {}

        tasks: List[TaskSpec] = []
        for task_name, td in (details.get("tasks") or {}).items():
            td = td or {}
            tasks.append(
                TaskSpec(
                    name=task_name,
                    description=format_template(td.get("description", ""), topic=topic),
                    expected_output=format_template(
                        td.get("expected_output", "Task completed successfully."),
                        topic=topic,
                    ),
                    tools=_resolve_tools(td.get("tools", []), tools_dict),
                    extras=td,
                )
            )

        specs.append(
            AgentSpec(
                key=key,
                role=format_template(details.get("role", key), topic=topic),
                goal=format_template(details.get("goal", ""), topic=topic),
                backstory=format_template(details.get("backstory", ""), topic=topic),
                tools=_resolve_tools(details.get("tools", []), tools_dict),
                tasks=tasks,
                extras=details,
            )
        )

    return specs
