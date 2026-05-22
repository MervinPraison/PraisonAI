"""Run praisonaiagents AgentFlow workflows with run tracking."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


def load_workflow_yaml(path: str) -> Dict[str, Any]:
    """Load workflow definition from a YAML file."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("Workflow YAML must be a mapping")
    return data


def run_workflow(
    workflow_id: str,
    *,
    input_text: str = "",
    workflow_config: Optional[Dict[str, Any]] = None,
    yaml_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute a workflow and return a serialisable run record."""
    run_id = uuid.uuid4().hex[:12]
    config = dict(workflow_config or {})
    if yaml_path:
        loaded = load_workflow_yaml(yaml_path)
        config = {**loaded, **config}

    steps = config.get("steps") or []
    if not steps:
        return {
            "id": run_id,
            "workflow_id": workflow_id,
            "status": "failed",
            "input": {"text": input_text},
            "error": "Workflow has no steps",
        }

    try:
        from praisonaiagents import Agent, AgentFlow

        flow_steps = []
        for i, step in enumerate(steps):
            if isinstance(step, str):
                flow_steps.append(
                    Agent(
                        name=f"step_{i + 1}",
                        instructions=step,
                        llm=config.get("model", "gpt-4o-mini"),
                    )
                )
            else:
                flow_steps.append(step)

        flow = AgentFlow(steps=flow_steps, name=config.get("name", "Workflow"))
        result = flow.run(input_text)
        return {
            "id": run_id,
            "workflow_id": workflow_id,
            "status": "completed",
            "input": {"text": input_text},
            "output": result if isinstance(result, dict) else {"result": str(result)},
        }
    except Exception as exc:
        return {
            "id": run_id,
            "workflow_id": workflow_id,
            "status": "failed",
            "input": {"text": input_text},
            "error": str(exc),
        }
