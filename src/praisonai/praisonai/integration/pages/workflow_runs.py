"""Optional L3 page — workflow runs table."""

from __future__ import annotations

import praisonaiui as aiui


@aiui.page("workflow-runs", title="Workflow Runs", icon="🔄")
async def workflow_runs_page():
    """Dashboard page listing recent workflow runs."""
    try:
        from praisonai.integration.bridges.workflows_service import run_workflow
    except ImportError:
        return {"runs": [], "note": "Workflow bridge unavailable"}

    return {"runs": [], "service": "WorkflowRunService", "status": "ready"}
