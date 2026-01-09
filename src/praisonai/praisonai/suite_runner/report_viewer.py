"""
Report Viewer for suite execution reports.

Provides CLI-friendly viewing of JSON/CSV reports with:
- Latest report auto-detection
- Failure tables with filtering
- Error grouping and deduplication
- ASCII table rendering (no external deps)

Used by both `praisonai examples report` and `praisonai docs report`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class ReportItem:
    """Normalized report item from JSON/CSV."""
    item_id: str
    suite: str
    group: str
    source_path: str
    block_index: int = 0
    status: str = "not_run"
    duration_seconds: float = 0.0
    exit_code: int = 0
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    error_signature: str = ""  # Normalized for grouping
    skip_reason: Optional[str] = None
    stdout_path: Optional[str] = None
    stderr_path: Optional[str] = None
    start_time: str = ""
    end_time: str = ""
    runnable_decision: str = ""
    
    @property
    def display_name(self) -> str:
        """Human-readable display name."""
        path = Path(self.source_path)
        if self.suite == "docs" and self.block_index > 0:
            return f"{path.name}:{self.block_index}"
        return path.name


@dataclass
class ReportMetadata:
    """Report metadata from JSON."""
    suite: str = ""
    source_path: str = ""
    timestamp: str = ""
    platform: str = ""
    python_version: str = ""
    python_executable: str = ""
    praisonai_version: str = ""
    git_commit: Optional[str] = None
    groups_run: List[str] = field(default_factory=list)
    totals: Dict[str, int] = field(default_factory=dict)


@dataclass
class ErrorGroup:
    """Group of items with similar errors."""
    signature: str
    error_type: str
    sample_message: str
    count: int = 0
    items: List[ReportItem] = field(default_factory=list)


@dataclass
class LoadedReport:
    """Complete loaded and normalized report."""
    metadata: ReportMetadata
    items: List[ReportItem]
    report_dir: Path
    
    @property
    def failures(self) -> List[ReportItem]:
        """Get failed/timeout/error items."""
        return [i for i in self.items if i.status in ("failed", "timeout", "error")]


# =============================================================================
# Error Signature Normalization
# =============================================================================

# Patterns to strip from error messages for grouping
_STRIP_PATTERNS = [
    # File paths
    (r'File "[^"]+[/\\][^"]+\.py"', 'File "...py"'),
    (r'/[^\s:]+\.py', '...py'),
    (r'[A-Z]:\\[^\s:]+\.py', '...py'),
    # Line numbers
    (r', line \d+', ', line N'),
    (r'line \d+', 'line N'),
    # Memory addresses
    (r'0x[0-9a-fA-F]+', '0x...'),
    # Request IDs, UUIDs
    (r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', 'UUID'),
    (r'req_[a-zA-Z0-9]+', 'req_...'),
    # Timestamps
    (r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[^\s]*', 'TIMESTAMP'),
    # Numbers in brackets
    (r'\[\d+\]', '[N]'),
    # Port numbers
    (r':\d{4,5}(?=/|$|\s)', ':PORT'),
    # Whitespace normalization
    (r'\s+', ' '),
]


def normalize_error_signature(error_type: Optional[str], error_message: Optional[str]) -> str:
    """
    Create normalized error signature for grouping.
    
    Strips variable parts (paths, line numbers, addresses, timestamps)
    to group similar errors together.
    """
    if not error_message and not error_type:
        return "unknown_error"
    
    # Start with error type
    sig_parts = []
    if error_type:
        sig_parts.append(error_type)
    
    if error_message:
        msg = error_message.strip()
        # Apply all normalization patterns
        for pattern, replacement in _STRIP_PATTERNS:
            msg = re.sub(pattern, replacement, msg)
        # Take first 100 chars of normalized message
        msg = msg[:100].strip()
        if msg:
            sig_parts.append(msg)
    
    return ": ".join(sig_parts) if sig_parts else "unknown_error"


# =============================================================================
# Report Discovery
# =============================================================================

def find_latest_report_dir(suite: str, base_dir: Optional[Path] = None) -> Optional[Path]:
    """
    Find the latest report directory for a suite.
    
    Args:
        suite: "examples" or "docs"
        base_dir: Base reports directory (default: ~/Downloads/reports/<suite>)
        
    Returns:
        Path to latest report directory, or None if not found.
    """
    if base_dir is None:
        base_dir = Path.home() / "Downloads" / "reports" / suite
    
    if not base_dir.exists():
        return None
    
    # Check if base_dir itself contains report.json (user passed specific run dir)
    if (base_dir / "report.json").exists():
        return base_dir
    
    # Find subdirectories with report.json
    candidates = []
    for subdir in base_dir.iterdir():
        if subdir.is_dir():
            # Check for report.json in subdir or in group subdirs
            if (subdir / "report.json").exists():
                candidates.append(subdir)
            else:
                # Check if this is a run dir with group subdirs
                for group_dir in subdir.iterdir():
                    if group_dir.is_dir() and (group_dir / "report.json").exists():
                        candidates.append(subdir)
                        break
    
    if not candidates:
        return None
    
    # Sort by mtime (newest first)
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def find_report_files(report_dir: Path) -> List[Path]:
    """
    Find all report.json files in a report directory.
    
    Handles both single-group and multi-group report structures.
    """
    report_files = []
    
    # Check for report.json directly in report_dir
    direct = report_dir / "report.json"
    if direct.exists():
        report_files.append(direct)
    
    # Check for group subdirectories
    for subdir in report_dir.iterdir():
        if subdir.is_dir():
            group_report = subdir / "report.json"
            if group_report.exists():
                report_files.append(group_report)
    
    return report_files


# =============================================================================
# Report Loading
# =============================================================================

def load_report(report_dir: Path) -> LoadedReport:
    """
    Load and normalize a report from a directory.
    
    Aggregates all group reports if multiple exist.
    
    Args:
        report_dir: Path to report run directory.
        
    Returns:
        LoadedReport with normalized items.
        
    Raises:
        FileNotFoundError: If no report.json found.
        ValueError: If report cannot be parsed.
    """
    report_files = find_report_files(report_dir)
    
    if not report_files:
        raise FileNotFoundError(f"No report.json found in {report_dir}")
    
    all_items: List[ReportItem] = []
    metadata = ReportMetadata()
    groups_seen = set()
    
    for report_file in report_files:
        try:
            data = json.loads(report_file.read_text(encoding='utf-8'))
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {report_file}: {e}")
        
        # Parse metadata from first report
        if not metadata.suite and "metadata" in data:
            meta = data["metadata"]
            metadata = ReportMetadata(
                suite=meta.get("suite", ""),
                source_path=meta.get("source_path", ""),
                timestamp=meta.get("timestamp", ""),
                platform=meta.get("platform", ""),
                python_version=meta.get("python_version", ""),
                python_executable=meta.get("python_executable", ""),
                praisonai_version=meta.get("praisonai_version", ""),
                git_commit=meta.get("git_commit"),
                groups_run=meta.get("groups_run", []),
                totals=meta.get("totals", {}),
            )
        
        # Parse results
        for r in data.get("results", []):
            error_sig = normalize_error_signature(
                r.get("error_type"),
                r.get("error_message")
            )
            
            item = ReportItem(
                item_id=r.get("item_id", ""),
                suite=r.get("suite", ""),
                group=r.get("group", ""),
                source_path=r.get("source_path", ""),
                block_index=r.get("block_index", 0),
                status=r.get("status", "not_run"),
                duration_seconds=r.get("duration_seconds", 0.0),
                exit_code=r.get("exit_code", 0),
                error_type=r.get("error_type"),
                error_message=r.get("error_message"),
                error_signature=error_sig,
                skip_reason=r.get("skip_reason"),
                stdout_path=r.get("stdout_path"),
                stderr_path=r.get("stderr_path"),
                start_time=r.get("start_time", ""),
                end_time=r.get("end_time", ""),
                runnable_decision=r.get("runnable_decision", ""),
            )
            all_items.append(item)
            groups_seen.add(item.group)
    
    # Update metadata with aggregated groups
    if groups_seen:
        metadata.groups_run = sorted(groups_seen)
    
    # Recalculate totals from all items
    totals = {"passed": 0, "failed": 0, "skipped": 0, "timeout": 0, "not_run": 0, "xfail": 0, "total": 0}
    for item in all_items:
        totals["total"] += 1
        if item.status in totals:
            totals[item.status] += 1
    metadata.totals = totals
    
    return LoadedReport(
        metadata=metadata,
        items=all_items,
        report_dir=report_dir,
    )


# =============================================================================
# Error Grouping
# =============================================================================

def group_errors(items: List[ReportItem]) -> List[ErrorGroup]:
    """
    Group items by error signature.
    
    Returns groups sorted by count (descending), then signature.
    """
    groups: Dict[str, ErrorGroup] = {}
    
    for item in items:
        if item.status not in ("failed", "timeout", "error"):
            continue
        
        sig = item.error_signature or "unknown_error"
        
        if sig not in groups:
            groups[sig] = ErrorGroup(
                signature=sig,
                error_type=item.error_type or "",
                sample_message=item.error_message or "",
            )
        
        groups[sig].count += 1
        groups[sig].items.append(item)
    
    # Sort by count desc, then signature asc
    sorted_groups = sorted(
        groups.values(),
        key=lambda g: (-g.count, g.signature)
    )
    
    return sorted_groups


# =============================================================================
# ASCII Table Rendering
# =============================================================================

def _truncate(text: str, max_len: int, ellipsis: str = "...") -> str:
    """Truncate text with ellipsis if too long."""
    if not text:
        return ""
    text = text.replace("\n", " ").replace("\r", "")
    if len(text) <= max_len:
        return text
    return text[:max_len - len(ellipsis)] + ellipsis


def _render_table(
    headers: List[str],
    rows: List[List[str]],
    col_widths: Optional[List[int]] = None,
    max_width: int = 120,
) -> str:
    """
    Render a simple ASCII table.
    
    Args:
        headers: Column headers.
        rows: List of row data (list of strings).
        col_widths: Optional fixed column widths.
        max_width: Maximum total table width.
        
    Returns:
        Formatted table string.
    """
    if not headers:
        return ""
    
    num_cols = len(headers)
    
    # Calculate column widths
    if col_widths is None:
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row[:num_cols]):
                col_widths[i] = max(col_widths[i], len(str(cell)))
    
    # Ensure we don't exceed max_width
    total_width = sum(col_widths) + (num_cols - 1) * 3 + 4  # separators + borders
    if total_width > max_width and col_widths:
        # Shrink largest columns proportionally
        excess = total_width - max_width
        while excess > 0 and max(col_widths) > 10:
            max_idx = col_widths.index(max(col_widths))
            col_widths[max_idx] -= 1
            excess -= 1
    
    lines = []
    
    # Header separator
    sep = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    lines.append(sep)
    
    # Header row
    header_cells = [
        f" {_truncate(h, w).ljust(w)} " for h, w in zip(headers, col_widths)
    ]
    lines.append("|" + "|".join(header_cells) + "|")
    lines.append(sep)
    
    # Data rows
    for row in rows:
        cells = []
        for i, w in enumerate(col_widths):
            cell = str(row[i]) if i < len(row) else ""
            cells.append(f" {_truncate(cell, w).ljust(w)} ")
        lines.append("|" + "|".join(cells) + "|")
    
    lines.append(sep)
    
    return "\n".join(lines)


# =============================================================================
# Report Rendering
# =============================================================================

STATUS_ICONS = {
    "passed": "✅",
    "failed": "❌",
    "skipped": "⏭️",
    "timeout": "⏱️",
    "not_run": "📝",
    "xfail": "⚠️",
    "error": "💥",
}


def render_overview(report: LoadedReport, wide: bool = False) -> str:
    """Render overview section with totals and metadata."""
    meta = report.metadata
    totals = meta.totals
    
    lines = [
        "",
        "=" * 60,
        f"  REPORT: {meta.suite.upper()} EXECUTION",
        "=" * 60,
        "",
        f"  Timestamp:    {meta.timestamp}",
        f"  Platform:     {meta.platform}",
        f"  Python:       {meta.python_version}",
        f"  PraisonAI:    {meta.praisonai_version}",
    ]
    
    if meta.git_commit:
        lines.append(f"  Git Commit:   {meta.git_commit}")
    
    if meta.groups_run:
        groups_str = ", ".join(meta.groups_run[:10])
        if len(meta.groups_run) > 10:
            groups_str += f" (+{len(meta.groups_run) - 10} more)"
        lines.append(f"  Groups:       {groups_str}")
    
    lines.append(f"  Report Dir:   {report.report_dir}")
    lines.append("")
    
    # Summary table
    lines.append("  SUMMARY")
    lines.append("  " + "-" * 40)
    
    total = totals.get("total", 0)
    for status in ["passed", "failed", "timeout", "skipped", "not_run", "xfail"]:
        count = totals.get(status, 0)
        icon = STATUS_ICONS.get(status, "?")
        pct = f"({count * 100 / total:.1f}%)" if total > 0 else ""
        lines.append(f"  {icon} {status.capitalize():12} {count:5}  {pct}")
    
    lines.append("  " + "-" * 40)
    lines.append(f"  {'Total':15} {total:5}")
    lines.append("")
    
    return "\n".join(lines)


def render_failures_table(
    report: LoadedReport,
    limit: int = 50,
    match_statuses: Optional[List[str]] = None,
    match_groups: Optional[List[str]] = None,
    contains: Optional[str] = None,
    wide: bool = False,
) -> str:
    """
    Render failures table.
    
    Args:
        report: Loaded report.
        limit: Max rows to show (0 = no limit).
        match_statuses: Filter by status(es).
        match_groups: Filter by group(s).
        contains: Filter by error message substring.
        wide: Show full error messages.
        
    Returns:
        Formatted table string.
    """
    # Default to failure statuses
    if match_statuses is None:
        match_statuses = ["failed", "timeout", "error"]
    
    # Filter items
    items = []
    for item in report.items:
        if item.status not in match_statuses:
            continue
        if match_groups and item.group not in match_groups:
            continue
        if contains:
            msg = (item.error_message or "").lower()
            if contains.lower() not in msg:
                continue
        items.append(item)
    
    if not items:
        return "\n  No matching failures found.\n"
    
    # Apply limit
    total_count = len(items)
    if limit > 0 and len(items) > limit:
        items = items[:limit]
    
    lines = [
        "",
        f"  FAILURES ({total_count} total, showing {len(items)})",
        "  " + "-" * 50,
        "",
    ]
    
    # Build table
    headers = ["Group", "Item", "Status", "Duration", "Error"]
    rows = []
    
    error_width = 60 if wide else 30
    
    for item in items:
        icon = STATUS_ICONS.get(item.status, "?")
        duration = f"{item.duration_seconds:.2f}s" if item.duration_seconds else "-"
        error = item.error_message or item.skip_reason or "-"
        
        rows.append([
            item.group,
            item.display_name,
            f"{icon} {item.status}",
            duration,
            _truncate(error, error_width) if not wide else error[:200],
        ])
    
    col_widths = [15, 30, 12, 10, error_width]
    lines.append(_render_table(headers, rows, col_widths if not wide else None))
    
    if limit > 0 and total_count > limit:
        lines.append(f"\n  ... and {total_count - limit} more (use --limit 0 to show all)")
    
    lines.append("")
    
    return "\n".join(lines)


def render_error_groups(
    report: LoadedReport,
    limit: int = 20,
    wide: bool = False,
    show_paths: bool = True,
) -> str:
    """
    Render error grouping section.
    
    Args:
        report: Loaded report.
        limit: Max groups to show (0 = no limit).
        wide: Show full error messages and all paths.
        show_paths: Show affected item paths.
        
    Returns:
        Formatted error groups string.
    """
    groups = group_errors(report.items)
    
    if not groups:
        return "\n  No errors to group.\n"
    
    total_groups = len(groups)
    if limit > 0 and len(groups) > limit:
        groups = groups[:limit]
    
    lines = [
        "",
        f"  ERROR GROUPS ({total_groups} unique errors)",
        "  " + "=" * 50,
        "",
    ]
    
    for i, grp in enumerate(groups, 1):
        lines.append(f"  [{i}] {grp.error_type or 'Error'} ({grp.count} occurrences)")
        lines.append("  " + "-" * 40)
        
        # Show signature/sample message
        if wide:
            msg = grp.sample_message or grp.signature
            lines.append(f"      {msg[:500]}")
        else:
            lines.append(f"      {_truncate(grp.signature, 80)}")
        
        # Show affected items
        if show_paths:
            lines.append("")
            lines.append("      Affected items:")
            
            items_to_show = grp.items if wide else grp.items[:5]
            for item in items_to_show:
                lines.append(f"        - {item.group}/{item.display_name}")
            
            if not wide and len(grp.items) > 5:
                lines.append(f"        ... and {len(grp.items) - 5} more")
        
        lines.append("")
    
    if limit > 0 and total_groups > limit:
        lines.append(f"  ... and {total_groups - limit} more error groups (use --limit 0 to show all)")
    
    lines.append("")
    
    return "\n".join(lines)


def render_artifacts(report: LoadedReport) -> str:
    """Render list of report artifacts."""
    lines = [
        "",
        "  REPORT ARTIFACTS",
        "  " + "-" * 40,
        f"  Directory: {report.report_dir}",
        "",
    ]
    
    # List files
    for f in sorted(report.report_dir.rglob("*")):
        if f.is_file():
            rel = f.relative_to(report.report_dir)
            size = f.stat().st_size
            size_str = f"{size:,} bytes" if size < 1024 else f"{size / 1024:.1f} KB"
            lines.append(f"    {rel}: {size_str}")
    
    lines.append("")
    
    return "\n".join(lines)


# =============================================================================
# Main View Function
# =============================================================================

def view_report(
    report_dir: Optional[Path] = None,
    suite: str = "examples",
    base_dir: Optional[Path] = None,
    limit: int = 50,
    show_errors: bool = True,
    wide: bool = False,
    show_paths: bool = True,
    match_statuses: Optional[List[str]] = None,
    match_groups: Optional[List[str]] = None,
    contains: Optional[str] = None,
    show_artifacts: bool = False,
    output_format: str = "table",
) -> Tuple[str, int]:
    """
    Main entry point for viewing a report.
    
    Args:
        report_dir: Explicit report directory (or None for auto-detect).
        suite: Suite name for auto-detection.
        base_dir: Base reports directory for auto-detection.
        limit: Max rows in tables.
        show_errors: Show error grouping section.
        wide: Wide output mode.
        show_paths: Show paths in error groups.
        match_statuses: Filter by status(es).
        match_groups: Filter by group(s).
        contains: Filter by error message substring.
        show_artifacts: Show artifact listing.
        output_format: "table" or "json".
        
    Returns:
        Tuple of (output_string, exit_code).
        Exit code is 0 if no failures, 1 if failures exist.
    """
    # Find report directory
    if report_dir is None:
        report_dir = find_latest_report_dir(suite, base_dir)
        if report_dir is None:
            return f"Error: No reports found for suite '{suite}'", 1
    
    if not report_dir.exists():
        return f"Error: Report directory not found: {report_dir}", 1
    
    # Load report
    try:
        report = load_report(report_dir)
    except FileNotFoundError as e:
        return f"Error: {e}", 1
    except ValueError as e:
        return f"Error: {e}", 1
    
    # JSON output
    if output_format == "json":
        output = {
            "metadata": {
                "suite": report.metadata.suite,
                "timestamp": report.metadata.timestamp,
                "totals": report.metadata.totals,
                "groups_run": report.metadata.groups_run,
            },
            "failures": [
                {
                    "item_id": i.item_id,
                    "group": i.group,
                    "display_name": i.display_name,
                    "status": i.status,
                    "error_type": i.error_type,
                    "error_message": i.error_message,
                }
                for i in report.failures
            ],
            "error_groups": [
                {
                    "signature": g.signature,
                    "error_type": g.error_type,
                    "count": g.count,
                    "items": [i.display_name for i in g.items],
                }
                for g in group_errors(report.items)
            ],
        }
        return json.dumps(output, indent=2), 0 if not report.failures else 1
    
    # Table output
    parts = []
    
    # Overview
    parts.append(render_overview(report, wide=wide))
    
    # Failures table
    parts.append(render_failures_table(
        report,
        limit=limit,
        match_statuses=match_statuses,
        match_groups=match_groups,
        contains=contains,
        wide=wide,
    ))
    
    # Error groups
    if show_errors:
        parts.append(render_error_groups(
            report,
            limit=limit,
            wide=wide,
            show_paths=show_paths,
        ))
    
    # Artifacts
    if show_artifacts:
        parts.append(render_artifacts(report))
    
    output = "\n".join(parts)
    exit_code = 0 if not report.failures else 1
    
    return output, exit_code
