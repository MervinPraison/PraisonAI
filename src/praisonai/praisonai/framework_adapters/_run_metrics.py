"""Per-agent usage report for YAML team runs (``--metrics`` / ``--metrics-json``).

Imported lazily by the PraisonAI adapter only when one of the flags is set, so
runs without them pay no import cost.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict


def _agent_name(task) -> str:
    agent = getattr(task, "agent", None)
    return getattr(agent, "name", None) or "unknown"


def attach_latency_timer(team) -> Dict[str, float]:
    """Chain timing onto ``team.on_task_start``/``on_task_complete``.

    Returns a dict of agent name -> accumulated wall time in seconds that fills
    in as tasks complete.
    """
    latency: Dict[str, float] = {}
    started: Dict[int, float] = {}
    original_start = team.on_task_start
    original_complete = team.on_task_complete

    def on_task_start(task, task_id):
        started[id(task)] = time.perf_counter()
        if original_start:
            original_start(task, task_id)

    def on_task_complete(task, task_output):
        t0 = started.pop(id(task), None)
        if t0 is not None:
            name = _agent_name(task)
            latency[name] = latency.get(name, 0.0) + time.perf_counter() - t0
        if original_complete:
            original_complete(task, task_output)

    team.on_task_start = on_task_start
    team.on_task_complete = on_task_complete
    return latency


def build_report(team, latency: Dict[str, float], model: str) -> Dict[str, Any]:
    """Build ``{agents: [...], total: {...}, model}`` from the team's token usage."""
    from praisonaiagents.telemetry.token_collector import get_token_collector

    summary = team.get_token_usage_summary()
    by_agent = summary.get("by_agent", {}) or {}
    calls: Dict[str, int] = {}
    collector = get_token_collector()
    for interaction in collector.get_recent_interactions(limit=collector._max_recent):
        name = interaction.get("agent")
        if name in by_agent:
            calls[name] = calls.get(name, 0) + 1

    names = [a.name for a in team.agents]
    names += [n for n in by_agent if n not in names]
    rows = []
    for name in names:
        usage = by_agent.get(name, {})
        rows.append({
            "name": name,
            "input_tokens": int(usage.get("input_tokens", 0)),
            "output_tokens": int(usage.get("output_tokens", 0)),
            "total_tokens": int(usage.get("total_tokens", 0)),
            "calls": calls.get(name, 0),
            "latency_s": round(latency.get(name, 0.0), 3),
        })
    total = {
        key: sum(row[key] for row in rows)
        for key in ("input_tokens", "output_tokens", "total_tokens", "calls")
    }
    total["latency_s"] = round(sum(row["latency_s"] for row in rows), 3)
    models = list(summary.get("by_model", {}) or {})
    return {"agents": rows, "total": total, "model": ", ".join(models) or model}


def print_table(report: Dict[str, Any]) -> None:
    from rich.console import Console
    from rich.table import Table

    table = Table(title=f"Agent Metrics (model: {report['model']})")
    for col in ("Agent", "Input", "Output", "Total", "Calls", "Time (s)"):
        table.add_column(col, justify="left" if col == "Agent" else "right")

    def _add(name, row, **kwargs):
        table.add_row(
            name, f"{row['input_tokens']:,}", f"{row['output_tokens']:,}",
            f"{row['total_tokens']:,}", str(row["calls"]), f"{row['latency_s']:.2f}",
            **kwargs,
        )

    for row in report["agents"]:
        _add(row["name"], row)
    _add("TOTAL", report["total"], style="bold")
    Console().print(table)


def print_json(report: Dict[str, Any]) -> None:
    print(json.dumps(report, indent=2))
