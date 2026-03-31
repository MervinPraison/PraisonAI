"""Cost persistence — saves agent cost_summary to disk after runs.

Writes JSON files to ``~/.praisonai/costs/`` for CLI dashboard consumption.
Zero overhead when not used (this module is never imported unless explicitly called).

Usage::

    from praisonaiagents.agent.cost_persistence import save_cost_report, load_cost_report

    save_cost_report(agent, session_name="my_run")
    report = load_cost_report("my_run")
"""

import json
import logging
from praisonaiagents._logging import get_logger
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = get_logger(__name__)

COST_DIR = Path.home() / ".praisonai" / "costs"

def save_cost_report(
    agent,
    session_name: Optional[str] = None,
) -> str:
    """Persist an agent's cost_summary to disk.

    Args:
        agent: Agent instance with cost_summary property.
        session_name: Optional session identifier. Auto-generated if None.

    Returns:
        Path to the saved JSON file.
    """
    COST_DIR.mkdir(parents=True, exist_ok=True)

    name = session_name or f"{agent.name}_{int(time.time())}"
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)

    summary = getattr(agent, "cost_summary", None)
    if summary is None:
        summary = {
            "tokens_in": 0,
            "tokens_out": 0,
            "cost": 0.0,
            "llm_calls": 0,
        }

    report = {
        "session": name,
        "agent_name": getattr(agent, "name", "unknown"),
        "timestamp": time.time(),
        "iso_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **summary,
    }

    filepath = COST_DIR / f"{safe_name}.json"
    with open(filepath, "w") as f:
        json.dump(report, f, indent=2)

    logger.info(f"[costs] Saved cost report to {filepath}")
    return str(filepath)

def load_cost_report(session_name: str) -> Optional[Dict[str, Any]]:
    """Load a cost report by session name.

    Args:
        session_name: Session identifier.

    Returns:
        Parsed JSON dict, or None if not found.
    """
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in session_name)
    filepath = COST_DIR / f"{safe_name}.json"
    if filepath.exists():
        with open(filepath) as f:
            return json.load(f)
    return None

def list_cost_reports(limit: int = 20) -> List[Dict[str, Any]]:
    """List recent cost reports, sorted by timestamp (newest first).

    Args:
        limit: Max number of reports to return.

    Returns:
        List of parsed JSON report dicts.
    """
    if not COST_DIR.exists():
        return []

    reports = []
    for fpath in sorted(COST_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            with open(fpath) as f:
                reports.append(json.load(f))
        except (json.JSONDecodeError, OSError):
            continue
        if len(reports) >= limit:
            break
    return reports

def format_cost_table(reports: List[Dict[str, Any]], as_json: bool = False) -> str:
    """Format cost reports for terminal display.

    Args:
        reports: List of report dicts from list_cost_reports().
        as_json: If True, returns JSON string instead of table.

    Returns:
        Formatted string for terminal output.
    """
    if as_json:
        return json.dumps(reports, indent=2)

    if not reports:
        return "No cost reports found."

    lines = []
    lines.append(f"{'Session':<30} {'Agent':<20} {'Cost ($)':<12} {'Tokens In':<12} {'Tokens Out':<12} {'LLM Calls':<10}")
    lines.append("-" * 96)
    for r in reports:
        lines.append(
            f"{r.get('session', '?'):<30} "
            f"{r.get('agent_name', '?'):<20} "
            f"${r.get('cost', 0):<11.4f} "
            f"{r.get('tokens_in', 0):<12} "
            f"{r.get('tokens_out', 0):<12} "
            f"{r.get('llm_calls', 0):<10}"
        )
    return "\n".join(lines)
