"""YAML definitions for replay: their static graph, and running them recorded.

- :func:`static_graph` / :func:`static_mermaid` picture an ``agents.yaml`` or
  workflow YAML *before* it runs (``praisonai replay flow file.yaml``).
- :func:`run_yaml_recorded` runs one under :func:`praisonai.replay.record`,
  storing the YAML path in ``session_start`` so ``replay rerun`` can find the
  definition again (``praisonai replay view file.yaml``).
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple, Union

__all__ = [
    "is_yaml_path",
    "load_flow",
    "static_graph",
    "static_mermaid",
    "run_yaml_recorded",
    "yaml_kind",
    "yaml_meta",
    "yaml_wants_replay",
]

GRAPH_SCHEMA = "praisonai.graph/1"


def is_yaml_path(target: Union[str, Path, None]) -> bool:
    """True for an existing ``.yaml``/``.yml`` file."""
    if not target:
        return False
    path = Path(str(target)).expanduser()
    return path.suffix.lower() in (".yaml", ".yml") and path.is_file()


def yaml_meta(yaml_path: Union[str, Path]) -> Dict[str, Any]:
    """``session_start`` metadata that lets ``replay rerun`` find the definition."""
    resolved = str(Path(yaml_path).expanduser().resolve())
    return {"yaml_path": resolved, "agents_file": resolved}


def yaml_wants_replay(yaml_path: Optional[Union[str, Path]] = None, yaml_text: Optional[str] = None) -> bool:
    """True when the YAML sets ``save_replay: true`` at the top level."""
    try:
        import yaml

        if yaml_text is None:
            if not yaml_path or not Path(yaml_path).is_file():
                return False
            yaml_text = Path(yaml_path).read_text(encoding="utf-8")
        data = yaml.safe_load(yaml_text)
    except Exception:
        return False
    return isinstance(data, dict) and data.get("save_replay") is True


def yaml_kind(yaml_path: Union[str, Path]) -> str:
    """``"flow"`` when ``praisonai file.yaml`` would run it as a workflow, else ``"team"``.

    Same rule as ``AgentsGenerator._is_workflow_yaml``.
    """
    import yaml

    data = yaml.safe_load(Path(yaml_path).expanduser().read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return "team"
    is_flow = (
        data.get("process", "sequential") == "workflow"
        or ("steps" in data and "workflow" in data)
        or data.get("type") in {"job", "hybrid"}
    )
    return "flow" if is_flow else "team"


def load_flow(yaml_path: Union[str, Path]) -> Any:
    """Parse a YAML definition into an AgentFlow with the SDK's own parser (no run)."""
    from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser

    return YAMLWorkflowParser().parse_file(Path(yaml_path).expanduser())


def _core_diagram(name: str) -> Optional[Callable[..., Any]]:
    try:
        from praisonaiagents.workflows import diagram
    except Exception:
        return None
    fn = getattr(diagram, name, None)
    return fn if callable(fn) else None


def _fallback_graph(flow: Any) -> Dict[str, Any]:
    """A minimal ``praisonai.graph/1`` (linear steps) for SDKs without ``to_graph``."""
    nodes = [{"id": "start:begin", "kind": "start", "label": "Brief", "parent": None, "meta": {}}]
    edges = []
    seen: Dict[str, int] = {}
    prev = "start:begin"
    for step in getattr(flow, "steps", None) or []:
        name = getattr(step, "name", None) or getattr(step, "__name__", None) or type(step).__name__
        seen[name] = seen.get(name, 0) + 1
        node_id = f"step:{name}" if seen[name] == 1 else f"step:{name}#{seen[name]}"
        nodes.append({"id": node_id, "kind": "step", "label": str(name), "parent": None, "meta": {}})
        edges.append({"id": f"{prev}->{node_id}:next", "source": prev, "target": node_id, "kind": "next", "label": None})
        prev = node_id
    nodes.append({"id": "end:done", "kind": "end", "label": "Delivered", "parent": None, "meta": {}})
    edges.append({"id": f"{prev}->end:done:next", "source": prev, "target": "end:done", "kind": "next", "label": None})
    return {
        "schema": GRAPH_SCHEMA,
        "kind": "flow",
        "name": getattr(flow, "name", None) or "workflow",
        "process": "workflow",
        "nodes": nodes,
        "edges": edges,
    }


def static_graph(yaml_path: Union[str, Path]) -> Tuple[Dict[str, Any], Any]:
    """``(graph, flow)`` for a YAML definition, without running it.

    Uses ``praisonaiagents.workflows.diagram.to_graph`` when this SDK has it
    (schema ``praisonai.graph/1``); otherwise a linear fallback graph.
    """
    flow = load_flow(yaml_path)
    to_graph = _core_diagram("to_graph")
    if to_graph is not None:
        # A team YAML runs as an AgentTeam (task:/agent: node ids), so build the
        # same team the run builds; the flow view would give step: ids that
        # never match the run's events.
        if yaml_kind(yaml_path) == "team":
            team = _build_team_from_yaml(yaml_path)
            if team is not None:
                try:
                    graph = to_graph(team)
                    if isinstance(graph, dict):
                        return graph, flow
                except Exception:
                    pass
        try:
            graph = to_graph(flow)
            if isinstance(graph, dict):
                return graph, flow
        except Exception:
            pass
    return _fallback_graph(flow), flow


def _build_team_from_yaml(yaml_path: Union[str, Path]) -> Any:
    """The ``AgentTeam`` a ``praisonai file.yaml`` run would build, without running it.

    Uses the PraisonAI adapter's own builders so task and agent ids match the run.
    Returns ``None`` when the YAML can't be built offline (e.g. missing tools).
    """
    import yaml

    try:
        from praisonai.framework_adapters.praisonai_adapter import PraisonAIAdapter
        from praisonai_code.llm.config import build_config_list
    except Exception:
        return None
    try:
        config = yaml.safe_load(Path(yaml_path).expanduser().read_text(encoding="utf-8")) or {}
        adapter = PraisonAIAdapter()
        model = adapter._pick_model(build_config_list())
        agents, tasks = adapter._build_agents_and_tasks(
            config, config.get("topic", ""), {}, None, None, model
        )
        return adapter._build_team(config, agents, tasks, model)
    except Exception:
        return None


def static_mermaid(yaml_path: Union[str, Path]) -> str:
    """Mermaid for a YAML definition: ``graph_to_mermaid`` when available, else ``AgentFlow.to_mermaid()``."""
    graph, flow = static_graph(yaml_path)
    graph_to_mermaid = _core_diagram("graph_to_mermaid")
    if graph_to_mermaid is not None and graph.get("schema") == GRAPH_SCHEMA:
        try:
            return graph_to_mermaid(graph)
        except Exception:
            pass
    return flow.to_mermaid()


def run_yaml_recorded(
    yaml_path: Union[str, Path],
    *,
    run_id: Optional[str] = None,
    live: bool = False,
    plan: Any = None,
    on_seeded: Optional[Callable[[Any], None]] = None,
) -> Tuple[Any, Any]:
    """Run a YAML definition the way ``praisonai file.yaml`` does, recorded.

    Args:
        plan: a :class:`praisonai.replay.rerun.RerunPlan` to re-run from a node.
        on_seeded: called with what the plan restored (TraceStepCache or task keys).

    Returns:
        ``(recording, result)``.
    """
    from praisonai.agents_generator import AgentsGenerator
    from praisonai_code.llm.config import build_config_list

    from .recorder import record

    path = Path(yaml_path).expanduser().resolve()
    forked = plan.forked_from if plan is not None else None
    with record(run_id, live=live, meta=yaml_meta(path), _forked_from=forked) as rec:
        scope: Any = contextlib.nullcontext()
        if plan is not None:
            from .rerun import rerun_scope

            scope = rerun_scope(plan, on_seeded)
        with scope:
            with AgentsGenerator(str(path), "", build_config_list()) as generator:
                result = generator.generate_crew_and_kickoff()
    return rec, result
