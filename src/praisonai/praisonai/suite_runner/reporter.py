"""
Unified Report Builder for suite execution.

Generates JSON, Markdown, and CSV reports from execution results.
Used by both examples and docs runners.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import List

from .models import RunResult, RunReport


class SuiteReporter:
    """
    Generates reports from suite execution results.
    
    Supports JSON, Markdown, and CSV output formats.
    """
    
    def __init__(self, output_dir: Path):
        """
        Initialize reporter.
        
        Args:
            output_dir: Directory to write reports to.
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_json(self, report: RunReport) -> Path:
        """
        Generate JSON report.
        
        Args:
            report: RunReport with all results.
            
        Returns:
            Path to generated JSON file.
        """
        json_path = self.output_dir / "report.json"
        json_path.write_text(
            json.dumps(report.to_dict(), indent=2),
            encoding='utf-8'
        )
        return json_path
    
    def generate_markdown(self, report: RunReport) -> Path:
        """
        Generate Markdown report.
        
        Args:
            report: RunReport with all results.
            
        Returns:
            Path to generated Markdown file.
        """
        totals = report.totals
        total_count = sum(totals.values())
        
        suite_name = report.suite.title() if report.suite else "Suite"
        
        lines = [
            f"# {suite_name} Execution Report",
            "",
            f"**Generated**: {report.timestamp}",
            f"**Platform**: {report.platform_info}",
            f"**Python**: {report.python_version}",
            f"**Executable**: `{report.python_executable}`",
            f"**PraisonAI**: {report.praisonai_version}",
            f"**Source**: `{report.source_path}`",
        ]
        
        if report.git_commit:
            lines.append(f"**Git Commit**: {report.git_commit}")
        
        if report.groups_run:
            lines.append(f"**Groups**: {', '.join(report.groups_run)}")
        
        lines.extend([
            "",
            "## Summary",
            "",
            "| Status | Count |",
            "|--------|-------|",
            f"| ✅ Passed | {totals['passed']} |",
            f"| ❌ Failed | {totals['failed']} |",
            f"| ⏭️ Skipped | {totals['skipped']} |",
            f"| ⏱️ Timeout | {totals['timeout']} |",
            f"| 📝 Not Run | {totals['not_run']} |",
            f"| ⚠️ XFail | {totals['xfail']} |",
            f"| **Total** | **{total_count}** |",
            "",
            "## Results",
            "",
            "| Item | Group | Status | Duration | Reason |",
            "|------|-------|--------|----------|--------|",
        ])
        
        status_icons = {
            "passed": "✅",
            "failed": "❌",
            "skipped": "⏭️",
            "timeout": "⏱️",
            "not_run": "📝",
            "xfail": "⚠️",
        }
        
        for r in report.results:
            icon = status_icons.get(r.status, "?")
            duration = f"{r.duration_seconds:.2f}s" if r.duration_seconds else "-"
            reason = r.skip_reason or r.runnable_decision or r.error_message or "-"
            reason = reason[:40] + "..." if len(reason) > 40 else reason
            display = r.display_name
            lines.append(
                f"| `{display}` | {r.group} | {icon} {r.status} | {duration} | {reason} |"
            )
        
        # Add failures section
        failures = [r for r in report.results if r.status == "failed"]
        if failures:
            lines.extend([
                "",
                "## Failures",
                "",
            ])
            for r in failures:
                lines.extend([
                    f"### {r.display_name}",
                    "",
                    f"**Source**: `{r.source_path}`",
                    f"**Group**: {r.group}",
                    f"**Exit Code**: {r.exit_code}",
                ])
                if r.line_start:
                    lines.append(f"**Lines**: {r.line_start}-{r.line_end}")
                lines.append("")
                
                if r.error_type:
                    lines.append(f"**Error Type**: `{r.error_type}`")
                if r.error_message:
                    lines.extend([
                        "**Error**:",
                        "```",
                        r.error_message[:500],
                        "```",
                        "",
                    ])
                if r.stderr_path:
                    lines.append(f"**Logs**: `{r.stderr_path}`")
                lines.append("")
        
        # Add not_run section (brief)
        not_run = [r for r in report.results if r.status == "not_run"]
        if not_run:
            lines.extend([
                "",
                f"## Not Run ({len(not_run)} items)",
                "",
                "Partial snippets or items that were not executed:",
                "",
            ])
            for r in not_run[:20]:  # Limit to first 20
                lines.append(f"- `{r.display_name}`: {r.runnable_decision}")
            if len(not_run) > 20:
                lines.append(f"- ... and {len(not_run) - 20} more")
        
        md_path = self.output_dir / "report.md"
        md_path.write_text('\n'.join(lines), encoding='utf-8')
        return md_path
    
    def generate_csv(self, report: RunReport) -> Path:
        """
        Generate CSV report.
        
        One row per item for easy scanning and filtering.
        
        Args:
            report: RunReport with all results.
            
        Returns:
            Path to generated CSV file.
        """
        csv_path = self.output_dir / "report.csv"
        
        fieldnames = [
            "suite",
            "group",
            "item_id",
            "source_path",
            "block_index",
            "language",
            "line_start",
            "line_end",
            "runnable_decision",
            "status",
            "duration_seconds",
            "exit_code",
            "error_type",
            "error_message",
            "skip_reason",
            "stdout_log_path",
            "stderr_log_path",
            "started_at",
            "finished_at",
            "python_executable",
            "cwd",
            "env_requirements",
            "code_hash",
        ]
        
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for r in report.results:
                writer.writerow({
                    "suite": r.suite,
                    "group": r.group,
                    "item_id": r.item_id,
                    "source_path": str(r.source_path),
                    "block_index": r.block_index,
                    "language": r.language,
                    "line_start": r.line_start,
                    "line_end": r.line_end,
                    "runnable_decision": r.runnable_decision,
                    "status": r.status,
                    "duration_seconds": r.duration_seconds,
                    "exit_code": r.exit_code,
                    "error_type": r.error_type or "",
                    "error_message": (r.error_message or "")[:500],  # Limit length
                    "skip_reason": r.skip_reason or "",
                    "stdout_log_path": r.stdout_path or "",
                    "stderr_log_path": r.stderr_path or "",
                    "started_at": r.start_time,
                    "finished_at": r.end_time,
                    "python_executable": r.python_executable,
                    "cwd": r.cwd,
                    "env_requirements": r.env_requirements,
                    "code_hash": r.code_hash,
                })
        
        return csv_path
    
    def save_logs(self, results: List[RunResult]) -> Path:
        """
        Save stdout/stderr logs for each result.
        
        Args:
            results: List of RunResult objects.
            
        Returns:
            Path to logs directory.
        """
        logs_dir = self.output_dir / "logs"
        logs_dir.mkdir(exist_ok=True)
        
        for r in results:
            # Create safe filename
            if r.suite == "docs":
                slug = f"{r.source_path.stem}__{r.block_index}"
            else:
                slug = r.source_path.stem
            
            # Sanitize slug
            slug = slug.replace(" ", "_").replace("-", "_").replace("/", "__")
            
            if r.stdout:
                stdout_path = logs_dir / f"{slug}.stdout.log"
                stdout_path.write_text(r.stdout, encoding='utf-8')
                r.stdout_path = f"logs/{slug}.stdout.log"
            
            if r.stderr:
                stderr_path = logs_dir / f"{slug}.stderr.log"
                stderr_path.write_text(r.stderr, encoding='utf-8')
                r.stderr_path = f"logs/{slug}.stderr.log"
        
        return logs_dir
    
    def generate_all(self, report: RunReport) -> dict:
        """
        Generate all report formats.
        
        Args:
            report: RunReport with all results.
            
        Returns:
            Dict with paths to generated files.
        """
        self.save_logs(report.results)
        
        return {
            "json": self.generate_json(report),
            "markdown": self.generate_markdown(report),
            "csv": self.generate_csv(report),
            "logs": self.output_dir / "logs",
        }
