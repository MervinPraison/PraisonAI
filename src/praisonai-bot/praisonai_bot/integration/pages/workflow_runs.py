"""Optional L3 page — workflow runs table.

Lists the runs recorded by aiui's workflows feature (``POST
/api/workflows/{id}/run``, executed through the package's workflow backend)
as aiui components: status chips, totals and a runs table, newest first, with
explicit empty and error states.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import praisonaiui as aiui
from praisonaiui import ui

from ._blocks import clip

# run["status"] -> (label, badge variant)
_RUN_STATUS = {
    "completed": ("Completed", "default"),
    "succeeded": ("Completed", "default"),
    "success": ("Completed", "default"),
    "running": ("Running", "secondary"),
    "pending": ("Pending", "secondary"),
    "queued": ("Pending", "secondary"),
    "failed": ("Failed", "destructive"),
    "error": ("Failed", "destructive"),
    "cancelled": ("Cancelled", "outline"),
}

MAX_ROWS = 100


def run_status(run: Dict[str, Any]) -> Tuple[str, str]:
    return _RUN_STATUS.get(str(run.get("status", "")).lower(), ("Unknown", "outline"))


def _input_text(run: Dict[str, Any]) -> Any:
    data = run.get("input")
    if isinstance(data, dict):
        return data.get("text") or data.get("message") or (data or None)
    return data


def _outcome(run: Dict[str, Any]) -> Any:
    if run.get("error"):
        return run["error"]
    out = run.get("output")
    if isinstance(out, dict):
        for key in ("output", "result", "text"):
            if isinstance(out.get(key), str):
                return out[key]
    return out


def build_workflow_runs(
    runs: Optional[Sequence[Dict[str, Any]]],
    *,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    """The page as an ``aiui.layout``; ``runs=None`` means no runs store."""
    if error is not None:
        return ui.layout([
            ui.alert("The workflow runs could not be read.", variant="error",
                     title="Workflow runs unavailable"),
            ui.caption(clip(error, 300)),
        ])
    if runs is None:
        return ui.layout([
            ui.alert("This UI has no workflows feature, so no runs are recorded.",
                     variant="warning", title="Workflows not enabled"),
            ui.empty("Enable aiui's workflows feature to record and list runs here."),
        ])
    if not runs:
        return ui.layout([
            ui.stat_group([{"label": "Runs", "value": 0}]),
            ui.empty("No workflow runs yet. Run a workflow from the Workflows page "
                     "or POST /api/workflows/{id}/run."),
        ])

    statuses = [run_status(r) for r in runs]
    totals: Dict[str, int] = {}
    for label, _ in statuses:
        totals[label] = totals.get(label, 0) + 1
    blocks: List[Dict[str, Any]] = [
        ui.stat_group([
            {"label": "Runs", "value": len(runs)},
            {"label": "Completed", "value": totals.get("Completed", 0)},
            {"label": "Failed", "value": totals.get("Failed", 0)},
            {"label": "In progress", "value": totals.get("Running", 0) + totals.get("Pending", 0)},
        ]),
    ]
    for label, variant in sorted({s for s in statuses}, key=lambda s: s[0]):
        blocks.append(ui.badge(f"{label}: {totals[label]}", variant=variant))

    newest_first = list(zip(runs, statuses))[::-1][:MAX_ROWS]
    blocks.append(ui.table(
        headers=["Run", "Workflow", "Status", "Input", "Result / error"],
        rows=[
            [clip(r.get("id"), 24), clip(r.get("workflow_id"), 60), label,
             clip(_input_text(r)), clip(_outcome(r))]
            for r, (label, _) in newest_first
        ],
    ))
    if len(runs) > MAX_ROWS:
        blocks.append(ui.caption(f"Showing the newest {MAX_ROWS} of {len(runs)} runs."))
    return ui.layout(blocks)


def recorded_runs() -> Optional[List[Dict[str, Any]]]:
    """Runs recorded by aiui's workflows feature, oldest first; None without it."""
    try:
        from praisonaiui.features import get_feature
        from praisonaiui.features import workflows as wf_feature
    except ImportError:
        return None
    if get_feature("workflows") is None:
        return None
    store = getattr(wf_feature, "_runs", None)
    if not isinstance(store, dict):
        return None
    return [r for r in list(store.values()) if isinstance(r, dict)]


@aiui.page("workflow-runs", title="Workflow Runs", icon="🔄")
async def workflow_runs_page():
    """Dashboard page listing recent workflow runs."""
    try:
        runs = recorded_runs()
    except Exception as exc:  # noqa: BLE001 - shown as the page's error state
        return build_workflow_runs(None, error=f"{type(exc).__name__}: {exc}")
    return build_workflow_runs(runs)
