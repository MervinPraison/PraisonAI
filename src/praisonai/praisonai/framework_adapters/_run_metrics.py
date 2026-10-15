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


class RunMetrics:
    """Collect per-agent wall time and LLM call counts for one team run.

    Timing chains onto ``team.on_task_start``/``on_task_complete``; call counts
    wrap the global token collector's ``track_tokens`` for the duration of the
    run and only count this team's agents (by id, or by name for id-less
    records), so they are neither capped by the recent-history buffer nor
    inflated by other teams. Call :meth:`close` when the run ends.
    """

    def __init__(self, team):
        from praisonaiagents.telemetry.token_collector import get_token_collector

        self.team = team
        self.latency: Dict[str, float] = {}
        self.calls: Dict[str, int] = {}
        self._started: Dict[int, tuple] = {}
        self._original_start = team.on_task_start
        self._original_complete = team.on_task_complete
        team.on_task_start = self._on_task_start
        team.on_task_complete = self._on_task_complete

        agents = team.agents or []
        self._ids = {getattr(a, "_approval_scope_id", None) for a in agents} - {None}
        self._names = {getattr(a, "name", None) for a in agents} - {None}
        self._collector = get_token_collector()
        self._prev_track = self._collector.__dict__.get("track_tokens")
        original_track = self._collector.track_tokens

        def track_tokens(model, agent, metrics, metadata=None, agent_id=None):
            if agent_id in self._ids or (agent_id is None and agent in self._names):
                self.calls[agent] = self.calls.get(agent, 0) + 1
            return original_track(model, agent, metrics, metadata=metadata, agent_id=agent_id)

        self._collector.track_tokens = track_tokens

    def _on_task_start(self, task, task_id):
        self._started[id(task)] = (_agent_name(task), time.perf_counter())
        if self._original_start:
            self._original_start(task, task_id)

    def _on_task_complete(self, task, task_output):
        self._stop(id(task))
        if self._original_complete:
            self._original_complete(task, task_output)

    def _stop(self, key) -> None:
        entry = self._started.pop(key, None)
        if entry is not None:
            name, t0 = entry
            self.latency[name] = self.latency.get(name, 0.0) + time.perf_counter() - t0

    def close(self) -> None:
        """Restore hooks and close timers of tasks that never completed (failed)."""
        for key in list(self._started):
            self._stop(key)
        if self._prev_track is None:
            self._collector.__dict__.pop("track_tokens", None)
        else:
            self._collector.track_tokens = self._prev_track
        self.team.on_task_start = self._original_start
        self.team.on_task_complete = self._original_complete

    def report(self, model: str) -> Dict[str, Any]:
        """Build ``{agents: [...], total: {...}, model}`` from the team's token usage."""
        summary = self.team.get_token_usage_summary()
        by_agent = summary.get("by_agent", {}) or {}
        names = [a.name for a in self.team.agents]
        names += [n for n in by_agent if n not in names]
        rows = []
        for name in names:
            usage = by_agent.get(name, {})
            rows.append({
                "name": name,
                "input_tokens": int(usage.get("input_tokens", 0)),
                "output_tokens": int(usage.get("output_tokens", 0)),
                "total_tokens": int(usage.get("total_tokens", 0)),
                "calls": self.calls.get(name, 0),
                "latency_s": round(self.latency.get(name, 0.0), 3),
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
