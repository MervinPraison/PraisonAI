"""
Report Builder for docs code execution.

Generates JSON and Markdown reports from execution results.
"""

from __future__ import annotations

import json
import platform
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any


@dataclass
class SnippetResult:
    """Result of running a single code snippet."""
    
    doc_path: Path
    block_index: int
    language: str
    line_start: int
    line_end: int
    runnable_decision: str
    status: str  # passed, failed, skipped, timeout, not_run
    exit_code: int = 0
    duration_seconds: float = 0.0
    start_time: str = ""
    end_time: str = ""
    skip_reason: Optional[str] = None
    error_summary: Optional[str] = None
    stdout: str = ""
    stderr: str = ""
    stdout_path: Optional[str] = None
    stderr_path: Optional[str] = None
    code_hash: str = ""


class DocsReportBuilder:
    """Generates reports from docs execution results."""
    
    def __init__(self, output_dir: Path):
        """
        Initialize report builder.
        
        Args:
            output_dir: Directory to write reports to.
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_metadata(self, docs_path: Path) -> Dict[str, Any]:
        """Get run metadata."""
        # Get praisonai version
        try:
            from praisonai.version import __version__
            version = __version__
        except ImportError:
            version = "unknown"
        
        # Get git commit
        git_commit = None
        try:
            result = subprocess.run(
                ['git', 'rev-parse', '--short', 'HEAD'],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                git_commit = result.stdout.strip()
        except Exception:
            pass
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "platform": f"{platform.system()}-{platform.release()}-{platform.machine()}",
            "python_version": platform.python_version(),
            "praisonai_version": version,
            "git_commit": git_commit,
            "docs_path": str(docs_path),
        }
    
    def _calculate_totals(self, results: List[SnippetResult]) -> Dict[str, int]:
        """Calculate totals by status."""
        totals = {
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "timeout": 0,
            "not_run": 0,
        }
        for r in results:
            if r.status in totals:
                totals[r.status] += 1
        return totals
    
    def generate_json(
        self,
        results: List[SnippetResult],
        docs_path: Path,
        cli_args: Optional[List[str]] = None,
    ) -> Path:
        """
        Generate JSON report.
        
        Args:
            results: List of SnippetResult objects.
            docs_path: Path to docs directory.
            cli_args: CLI arguments used.
            
        Returns:
            Path to generated JSON file.
        """
        metadata = self._get_metadata(docs_path)
        metadata["totals"] = self._calculate_totals(results)
        metadata["cli_args"] = cli_args or []
        
        data = {
            "metadata": metadata,
            "snippets": [
                {
                    "doc_path": str(r.doc_path),
                    "block_index": r.block_index,
                    "language": r.language,
                    "line_start": r.line_start,
                    "line_end": r.line_end,
                    "runnable_decision": r.runnable_decision,
                    "status": r.status,
                    "exit_code": r.exit_code,
                    "duration_seconds": r.duration_seconds,
                    "start_time": r.start_time,
                    "end_time": r.end_time,
                    "skip_reason": r.skip_reason,
                    "error_summary": r.error_summary,
                    "stdout_path": r.stdout_path,
                    "stderr_path": r.stderr_path,
                    "code_hash": r.code_hash,
                }
                for r in results
            ],
        }
        
        json_path = self.output_dir / "report.json"
        json_path.write_text(json.dumps(data, indent=2), encoding='utf-8')
        return json_path
    
    def generate_markdown(
        self,
        results: List[SnippetResult],
        docs_path: Path,
    ) -> Path:
        """
        Generate Markdown report.
        
        Args:
            results: List of SnippetResult objects.
            docs_path: Path to docs directory.
            
        Returns:
            Path to generated Markdown file.
        """
        metadata = self._get_metadata(docs_path)
        totals = self._calculate_totals(results)
        total_count = sum(totals.values())
        
        lines = [
            "# Docs Code Execution Report",
            "",
            f"**Generated**: {metadata['timestamp']}",
            f"**Platform**: {metadata['platform']}",
            f"**Python**: {metadata['python_version']}",
            f"**PraisonAI**: {metadata['praisonai_version']}",
            f"**Docs Path**: `{docs_path}`",
        ]
        
        if metadata.get('git_commit'):
            lines.append(f"**Git Commit**: {metadata['git_commit']}")
        
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
            f"| **Total** | **{total_count}** |",
            "",
            "## Results",
            "",
            "| Doc | Block | Status | Duration | Reason |",
            "|-----|-------|--------|----------|--------|",
        ])
        
        status_icons = {
            "passed": "✅",
            "failed": "❌",
            "skipped": "⏭️",
            "timeout": "⏱️",
            "not_run": "📝",
        }
        
        for r in results:
            icon = status_icons.get(r.status, "?")
            duration = f"{r.duration_seconds:.2f}s" if r.duration_seconds else "-"
            reason = r.skip_reason or r.runnable_decision or "-"
            doc_name = Path(r.doc_path).name
            lines.append(
                f"| `{doc_name}` | {r.block_index} | {icon} {r.status} | {duration} | {reason[:30]} |"
            )
        
        # Add failures section
        failures = [r for r in results if r.status == "failed"]
        if failures:
            lines.extend([
                "",
                "## Failures",
                "",
            ])
            for r in failures:
                lines.extend([
                    f"### {Path(r.doc_path).name} - Block {r.block_index}",
                    "",
                    f"**Lines**: {r.line_start}-{r.line_end}",
                    f"**Exit Code**: {r.exit_code}",
                    "",
                ])
                if r.error_summary:
                    lines.extend([
                        "**Error**:",
                        "```",
                        r.error_summary,
                        "```",
                        "",
                    ])
        
        # Add not_run section
        not_run = [r for r in results if r.status == "not_run"]
        if not_run:
            lines.extend([
                "",
                "## Not Run (Partial Snippets)",
                "",
                "These blocks were not executed because they appear to be partial snippets:",
                "",
            ])
            for r in not_run:
                doc_name = Path(r.doc_path).name
                lines.append(f"- `{doc_name}` block {r.block_index}: {r.runnable_decision}")
        
        md_path = self.output_dir / "report.md"
        md_path.write_text('\n'.join(lines), encoding='utf-8')
        return md_path
    
    def save_logs(self, results: List[SnippetResult]) -> Path:
        """
        Save stdout/stderr logs for each result.
        
        Args:
            results: List of SnippetResult objects.
            
        Returns:
            Path to logs directory.
        """
        logs_dir = self.output_dir / "logs"
        logs_dir.mkdir(exist_ok=True)
        
        for r in results:
            doc_slug = Path(r.doc_path).stem.replace(" ", "_").replace("-", "_")
            slug = f"{doc_slug}__{r.block_index}"
            
            if r.stdout:
                stdout_path = logs_dir / f"{slug}.stdout.log"
                stdout_path.write_text(r.stdout, encoding='utf-8')
                r.stdout_path = f"logs/{slug}.stdout.log"
            
            if r.stderr:
                stderr_path = logs_dir / f"{slug}.stderr.log"
                stderr_path.write_text(r.stderr, encoding='utf-8')
                r.stderr_path = f"logs/{slug}.stderr.log"
        
        return logs_dir
