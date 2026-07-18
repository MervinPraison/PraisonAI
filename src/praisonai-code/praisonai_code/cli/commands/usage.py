"""
Usage command for PraisonAI CLI (Issue #3155).

Zero-config local spend/usage reporting. Reads the already-persisted
per-session ``total_tokens``/``cost`` from the local session store(s) and
aggregates them by day, model or project — no external observability
platform, no network egress, no configuration required.

    praisonai usage                 # last 30 days, grouped by day
    praisonai usage --by model      # grouped by model
    praisonai usage --by project    # grouped by project
    praisonai usage --days 7        # only the last week
    praisonai usage --json          # machine-readable output
"""

from typing import Any, Callable, Dict, List, Optional, Tuple

import typer

from ..output.console import get_output_controller

app = typer.Typer(help="Local token/cost usage reporting")

# Bound the per-store scan so realistic stores are never silently truncated
# while keeping memory usage predictable for pathological session dirs.
_STORE_SCAN_LIMIT = 100_000


def _parse_updated_at(value: Optional[str]):
    """Parse an ISO ``updated_at`` string into a datetime (best-effort)."""
    if not value:
        return None
    from datetime import datetime

    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _rows_from_sessions(
    sessions: List[Dict[str, Any]], project_label: str
) -> List[Dict[str, Any]]:
    """Flatten raw session records into usage rows tagged with ``project_label``."""
    rows: List[Dict[str, Any]] = []
    for s in sessions:
        rows.append(
            {
                "updated_at": s.get("updated_at"),
                "model": s.get("model") or "unknown",
                "project": project_label,
                "total_tokens": int(s.get("total_tokens") or 0),
                "cost": float(s.get("cost") or 0.0),
            }
        )
    return rows


def _collect_rows(
    project: Optional[str],
    on_error: Optional[Callable[[str], None]] = None,
) -> List[Dict[str, Any]]:
    """Read session records from the local store(s) as flat usage rows.

    When ``project`` is given, only that project's scoped store is read;
    otherwise the current-project store and the global default store are read
    **separately** so each row keeps its originating project identity (a blanket
    label would collapse ``--by project`` into a single bucket).

    Store-read failures are reported via ``on_error`` (rather than silently
    yielding an empty report) so a missing/damaged store is distinguishable from
    genuinely empty usage.
    """
    from ..state.project_sessions import (
        _get_default_store,
        get_project_session_store,
    )

    def _report(message: str) -> None:
        if on_error is not None:
            on_error(message)

    rows: List[Dict[str, Any]] = []

    if project:
        try:
            store = get_project_session_store(project_id=project)
            sessions = store.list_sessions(limit=_STORE_SCAN_LIMIT) or []
        except Exception as exc:  # noqa: BLE001 - surfaced to the user below
            _report(f"could not read project store {project!r}: {exc}")
            return rows
        rows.extend(_rows_from_sessions(sessions, project))
        return rows

    # No explicit project: read the current-project store and the global
    # default store independently, preserving each store's project identity and
    # de-duplicating shared session ids (mirrors ``list_project_sessions``).
    seen_ids: set = set()
    for label, resolve in (
        ("current", lambda: get_project_session_store()),
        ("global", _get_default_store),
    ):
        try:
            store = resolve()
        except Exception as exc:  # noqa: BLE001
            _report(f"could not open {label} session store: {exc}")
            continue
        if store is None:
            continue
        try:
            sessions = store.list_sessions(limit=_STORE_SCAN_LIMIT) or []
        except Exception as exc:  # noqa: BLE001
            _report(f"could not read {label} session store: {exc}")
            continue
        fresh = []
        for s in sessions:
            sid = s.get("session_id") or s.get("id")
            if sid and sid in seen_ids:
                continue
            if sid:
                seen_ids.add(sid)
            fresh.append(s)
        rows.extend(_rows_from_sessions(fresh, label))
    return rows


def _within_days(rows: List[Dict[str, Any]], days: int) -> List[Dict[str, Any]]:
    """Keep rows updated within the last ``days`` (0/negative = no filter)."""
    if days <= 0:
        return rows
    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    kept: List[Dict[str, Any]] = []
    for row in rows:
        dt = _parse_updated_at(row.get("updated_at"))
        if dt is None:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt >= cutoff:
            kept.append(row)
    return kept


def _group(rows: List[Dict[str, Any]], by: str) -> List[Tuple[str, int, float]]:
    """Group rows by the requested dimension, summing tokens and cost."""
    buckets: Dict[str, Dict[str, float]] = {}
    for row in rows:
        if by == "model":
            key = row.get("model") or "unknown"
        elif by == "project":
            key = row.get("project") or "current"
        else:  # day
            dt = _parse_updated_at(row.get("updated_at"))
            key = dt.strftime("%Y-%m-%d") if dt else "unknown"
        bucket = buckets.setdefault(key, {"total_tokens": 0.0, "cost": 0.0})
        bucket["total_tokens"] += row.get("total_tokens") or 0
        bucket["cost"] += row.get("cost") or 0.0

    grouped = [
        (key, int(vals["total_tokens"]), round(vals["cost"], 6))
        for key, vals in buckets.items()
    ]
    # Day: chronological; model/project: highest spend first.
    if by == "day":
        grouped.sort(key=lambda r: r[0])
    else:
        grouped.sort(key=lambda r: r[1], reverse=True)
    return grouped


@app.command()
def usage(
    days: int = typer.Option(
        30, "--days", "-d", help="Only include sessions updated in the last N days (0 = all)"
    ),
    by: str = typer.Option(
        "day", "--by", "-b", help="Group by: day, model, or project"
    ),
    project: Optional[str] = typer.Option(
        None, "--project", "-p", help="Restrict to a specific project ID"
    ),
    json_: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON"
    ),
):
    """Report aggregate token/cost usage from the local session store."""
    output = get_output_controller()

    by = (by or "day").lower()
    if by not in ("day", "model", "project"):
        output.print_error("--by must be one of: day, model, project")
        raise typer.Exit(1)

    errors: List[str] = []
    rows = _within_days(_collect_rows(project, on_error=errors.append), days)
    grouped = _group(rows, by)

    total_tokens = sum(r[1] for r in grouped)
    total_cost = round(sum(r[2] for r in grouped), 6)

    if json_ or output.is_json_mode:
        output.print_json(
            {
                "by": by,
                "days": days,
                "project": project,
                "rows": [
                    {"key": k, "total_tokens": t, "cost": c} for k, t, c in grouped
                ],
                "total_tokens": total_tokens,
                "cost": total_cost,
                "errors": errors,
            }
        )
        return

    for message in errors:
        output.print_warning(f"Usage may be incomplete: {message}")

    if not grouped:
        if not errors:
            output.print_info("No usage recorded yet")
        return

    header = {"day": "Day", "model": "Model", "project": "Project"}[by]
    headers = [header, "Tokens", "Cost"]
    table_rows = [
        [k, f"{t:,}" if t else "-", f"${c:.4f}" if c else "-"]
        for k, t, c in grouped
    ]
    table_rows.append(["Total", f"{total_tokens:,}", f"${total_cost:.4f}"])

    output.print_table(headers, table_rows, title="Usage")
