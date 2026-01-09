"""
Unified Suite Executor.

Main orchestrator that runs items from any source (examples or docs)
using the shared runner and reporter.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional, Callable

from .models import RunItem, RunResult, RunReport
from .runner import ScriptRunner
from .reporter import SuiteReporter


class SuiteExecutor:
    """
    Unified executor for running code suites.
    
    Works with any source (examples, docs) that provides RunItems.
    """
    
    def __init__(
        self,
        suite: str,
        source_path: Path,
        timeout: int = 60,
        fail_fast: bool = False,
        stream_output: bool = True,
        max_items: Optional[int] = None,
        require_env: Optional[List[str]] = None,
        env_overrides: Optional[dict] = None,
        report_dir: Optional[Path] = None,
        generate_json: bool = True,
        generate_md: bool = True,
        generate_csv: bool = True,
        python_executable: Optional[str] = None,
        pythonpath_additions: Optional[List[str]] = None,
        groups: Optional[List[str]] = None,
    ):
        """
        Initialize executor.
        
        Args:
            suite: Suite name ("examples" or "docs").
            source_path: Path to source directory.
            timeout: Per-item timeout in seconds.
            fail_fast: Stop on first failure.
            stream_output: Stream output to terminal.
            max_items: Maximum items to process.
            require_env: Global required env vars.
            env_overrides: Environment variable overrides.
            report_dir: Directory for reports.
            generate_json: Generate JSON report.
            generate_md: Generate Markdown report.
            generate_csv: Generate CSV report.
            python_executable: Python interpreter to use.
            pythonpath_additions: Paths to add to PYTHONPATH.
            groups: Specific groups to run.
        """
        self.suite = suite
        self.source_path = Path(source_path).resolve()
        self.timeout = timeout
        self.fail_fast = fail_fast
        self.stream_output = stream_output
        self.max_items = max_items
        self.require_env = require_env or []
        self.env_overrides = env_overrides or {}
        self.report_dir = Path(report_dir) if report_dir else None
        self.generate_json = generate_json
        self.generate_md = generate_md
        self.generate_csv = generate_csv
        self.python_executable = python_executable or sys.executable
        self.pythonpath_additions = pythonpath_additions or []
        self.groups = groups
    
    def run(
        self,
        items: List[RunItem],
        on_item_start: Optional[Callable[[RunItem, int, int], None]] = None,
        on_item_end: Optional[Callable[[RunResult, int, int], None]] = None,
        on_output: Optional[Callable[[str, str], None]] = None,
    ) -> RunReport:
        """
        Run all items and return report.
        
        Args:
            items: List of RunItems to execute.
            on_item_start: Callback when starting an item.
            on_item_end: Callback when item completes.
            on_output: Callback for streaming output.
            
        Returns:
            RunReport with all results.
        """
        # Apply max_items limit
        if self.max_items and len(items) > self.max_items:
            items = items[:self.max_items]
        
        # Check global required env
        import os
        for key in self.require_env:
            if not os.environ.get(key):
                # Return empty report with error
                return RunReport(
                    results=[],
                    suite=self.suite,
                    source_path=self.source_path,
                    cli_args=[f"--require-env={key} (missing)"],
                    groups_run=self.groups or [],
                )
        
        # Create runner
        runner = ScriptRunner(
            timeout=self.timeout,
            capture_output=True,
            stream_output=self.stream_output,
            env_overrides=self.env_overrides,
            pythonpath_additions=self.pythonpath_additions,
            python_executable=self.python_executable,
        )
        
        results: List[RunResult] = []
        total = len(items)
        
        for idx, item in enumerate(items, 1):
            if on_item_start:
                on_item_start(item, idx, total)
            
            # Handle non-runnable items
            if not item.runnable:
                result = RunResult(
                    item_id=item.item_id,
                    suite=item.suite,
                    group=item.group,
                    source_path=item.source_path,
                    block_index=item.block_index,
                    language=item.language,
                    line_start=item.line_start,
                    line_end=item.line_end,
                    runnable_decision=item.runnable_decision,
                    status="skipped" if item.skip else "not_run",
                    skip_reason=item.skip_reason or item.runnable_decision,
                    code_hash=item.code_hash,
                )
                results.append(result)
                
                if on_item_end:
                    on_item_end(result, idx, total)
                continue
            
            # Check required env from item
            if item.require_env:
                missing = runner.check_required_env(item.require_env)
                if missing:
                    result = RunResult(
                        item_id=item.item_id,
                        suite=item.suite,
                        group=item.group,
                        source_path=item.source_path,
                        block_index=item.block_index,
                        language=item.language,
                        line_start=item.line_start,
                        line_end=item.line_end,
                        runnable_decision=item.runnable_decision,
                        status="skipped",
                        skip_reason=f"Missing env: {missing}",
                        env_requirements=",".join(item.require_env),
                        code_hash=item.code_hash,
                    )
                    results.append(result)
                    
                    if on_item_end:
                        on_item_end(result, idx, total)
                    continue
            
            # Execute
            result = runner.run(
                item,
                on_output=on_output if self.stream_output else None,
            )
            results.append(result)
            
            if on_item_end:
                on_item_end(result, idx, total)
            
            # Check fail-fast
            if self.fail_fast and result.status == "failed":
                # Mark remaining as skipped
                for remaining_item in items[idx:]:
                    results.append(RunResult(
                        item_id=remaining_item.item_id,
                        suite=remaining_item.suite,
                        group=remaining_item.group,
                        source_path=remaining_item.source_path,
                        block_index=remaining_item.block_index,
                        language=remaining_item.language,
                        runnable_decision=remaining_item.runnable_decision,
                        status="skipped",
                        skip_reason="Skipped due to --fail-fast",
                        code_hash=remaining_item.code_hash,
                    ))
                break
        
        # Create report
        report = RunReport(
            results=results,
            suite=self.suite,
            source_path=self.source_path,
            groups_run=self.groups or [],
        )
        
        # Generate reports if configured
        if self.report_dir:
            reporter = SuiteReporter(self.report_dir)
            reporter.save_logs(results)
            
            if self.generate_json:
                reporter.generate_json(report)
            
            if self.generate_md:
                reporter.generate_markdown(report)
            
            if self.generate_csv:
                reporter.generate_csv(report)
            
            report.report_path = self.report_dir
        
        return report
