"""
Examples Execution System for PraisonAI.

Discovers and runs Python examples, captures output, and generates reports.
Designed for zero performance impact when not invoked (lazy-loaded).

Usage:
    praisonai examples run                    # Run all examples
    praisonai examples run --path ./examples  # Custom path
    praisonai examples list                   # List discovered examples
"""

from __future__ import annotations

import fnmatch
import json
import os
import platform
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Callable


# Directive parsing regex
DIRECTIVE_PATTERN = re.compile(r'^#\s*praisonai:\s*(\w+)=(.+)$', re.MULTILINE)
INPUT_PATTERN = re.compile(r'\binput\s*\(')


@dataclass
class ExampleMetadata:
    """Metadata parsed from example file comment directives."""
    
    path: Path
    skip: bool = False
    skip_reason: Optional[str] = None
    timeout: Optional[int] = None
    require_env: List[str] = field(default_factory=list)
    xfail: Optional[str] = None
    is_interactive: bool = False
    
    @classmethod
    def from_file(cls, path: Path, max_lines: int = 30) -> "ExampleMetadata":
        """Parse metadata from file's first N lines."""
        meta = cls(path=path)
        
        try:
            content = path.read_text(encoding='utf-8', errors='ignore')
            lines = content.split('\n')[:max_lines]
            header = '\n'.join(lines)
            
            # Parse directives
            for match in DIRECTIVE_PATTERN.finditer(header):
                key, value = match.group(1), match.group(2).strip()
                
                if key == 'skip':
                    meta.skip = value.lower() in ('true', '1', 'yes')
                    if meta.skip:
                        meta.skip_reason = "skip=true directive"
                elif key == 'timeout':
                    try:
                        meta.timeout = int(value)
                    except ValueError:
                        pass
                elif key == 'require_env':
                    meta.require_env = [k.strip() for k in value.split(',') if k.strip()]
                elif key == 'xfail':
                    meta.xfail = value
            
            # Detect interactive input() calls
            if INPUT_PATTERN.search(content):
                meta.is_interactive = True
                
        except Exception:
            pass
        
        return meta


@dataclass
class ExampleResult:
    """Result of running a single example."""
    
    path: Path
    slug: str
    status: str  # passed, failed, skipped, timeout, xfail
    exit_code: int = 0
    duration_seconds: float = 0.0
    start_time: str = ""
    end_time: str = ""
    skip_reason: Optional[str] = None
    error_summary: Optional[str] = None
    stderr_tail: Optional[str] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    stdout_path: Optional[str] = None
    stderr_path: Optional[str] = None


@dataclass
class RunReport:
    """Complete run report with all results."""
    
    examples: List[ExampleResult]
    cli_args: List[str]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    platform_info: str = field(default_factory=lambda: f"{platform.system()}-{platform.release()}-{platform.machine()}")
    python_version: str = field(default_factory=lambda: platform.python_version())
    praisonai_version: str = ""
    git_commit: Optional[str] = None
    
    def __post_init__(self):
        # Get praisonai version
        try:
            from praisonai.version import __version__
            self.praisonai_version = __version__
        except ImportError:
            self.praisonai_version = "unknown"
        
        # Get git commit if available
        if self.git_commit is None:
            try:
                result = subprocess.run(
                    ['git', 'rev-parse', '--short', 'HEAD'],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    self.git_commit = result.stdout.strip()
            except Exception:
                pass
    
    @property
    def totals(self) -> dict:
        """Calculate totals by status."""
        counts = {"passed": 0, "failed": 0, "skipped": 0, "timeout": 0, "xfail": 0}
        for ex in self.examples:
            if ex.status in counts:
                counts[ex.status] += 1
        return counts


class ExampleDiscovery:
    """Discovers example Python files in a directory."""
    
    # Directories to always ignore
    IGNORE_DIRS = {
        '__pycache__', '.git', '.svn', '.hg',
        'venv', '.venv', 'env', '.env',
        'node_modules', '.tox', '.pytest_cache',
        '.mypy_cache', '.ruff_cache', 'dist', 'build',
        'egg-info', '.eggs',
    }
    
    def __init__(
        self,
        root: Path,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
    ):
        self.root = Path(root).resolve()
        self.include_patterns = include_patterns or []
        self.exclude_patterns = exclude_patterns or []
    
    def discover(self) -> List[Path]:
        """Discover all example Python files, sorted deterministically."""
        examples = []
        
        for path in self.root.rglob('*.py'):
            # Skip files starting with underscore
            if path.name.startswith('_'):
                continue
            
            # Skip ignored directories
            rel_parts = path.relative_to(self.root).parts
            if any(part in self.IGNORE_DIRS or part.endswith('.egg-info') for part in rel_parts):
                continue
            
            # Apply include patterns (if any)
            rel_path = path.relative_to(self.root).as_posix()
            if self.include_patterns:
                if not any(fnmatch.fnmatch(rel_path, p) for p in self.include_patterns):
                    continue
            
            # Apply exclude patterns
            if self.exclude_patterns:
                if any(fnmatch.fnmatch(rel_path, p) for p in self.exclude_patterns):
                    continue
            
            examples.append(path)
        
        # Sort for deterministic order
        return sorted(examples, key=lambda p: p.relative_to(self.root).as_posix())


class ExampleRunner:
    """Runs individual examples in isolated subprocesses."""
    
    def __init__(
        self,
        timeout: int = 60,
        capture_output: bool = True,
        stream_output: bool = False,
        env_overrides: Optional[dict] = None,
        pythonpath_additions: Optional[List[str]] = None,
    ):
        self.timeout = timeout
        self.capture_output = capture_output
        self.stream_output = stream_output
        self.env_overrides = env_overrides or {}
        self.pythonpath_additions = pythonpath_additions or []
    
    def _make_slug(self, path: Path, root: Optional[Path] = None) -> str:
        """Create a filesystem-safe slug from path."""
        if root:
            rel = path.relative_to(root)
        else:
            rel = path
        return rel.as_posix().replace('/', '__').replace('.py', '')
    
    def _build_env(self) -> dict:
        """Build environment for subprocess."""
        env = os.environ.copy()
        
        # Add PYTHONPATH
        pythonpath_parts = []
        if self.pythonpath_additions:
            pythonpath_parts.extend(self.pythonpath_additions)
        
        existing = env.get('PYTHONPATH', '')
        if existing:
            pythonpath_parts.append(existing)
        
        if pythonpath_parts:
            env['PYTHONPATH'] = os.pathsep.join(pythonpath_parts)
        
        # Apply overrides
        env.update(self.env_overrides)
        
        return env
    
    def _check_required_env(self, meta: ExampleMetadata) -> Optional[str]:
        """Check if required env vars are present. Returns missing var name or None."""
        for key in meta.require_env:
            if not os.environ.get(key):
                return key
        return None
    
    def run(
        self,
        path: Path,
        root: Optional[Path] = None,
        on_output: Optional[Callable[[str, str], None]] = None,
    ) -> ExampleResult:
        """Run a single example and return result."""
        slug = self._make_slug(path, root)
        meta = ExampleMetadata.from_file(path)
        
        # Check skip conditions
        if meta.skip:
            return ExampleResult(
                path=path,
                slug=slug,
                status="skipped",
                skip_reason=meta.skip_reason,
            )
        
        if meta.is_interactive:
            return ExampleResult(
                path=path,
                slug=slug,
                status="skipped",
                skip_reason="Interactive example (contains input())",
            )
        
        missing_env = self._check_required_env(meta)
        if missing_env:
            return ExampleResult(
                path=path,
                slug=slug,
                status="skipped",
                skip_reason=f"Missing required env: {missing_env}",
            )
        
        # Determine timeout
        timeout = meta.timeout if meta.timeout else self.timeout
        
        # Build command
        cmd = [sys.executable, '-u', str(path)]
        env = self._build_env()
        cwd = path.parent  # Run from example's directory
        
        # Record start time
        start_time = datetime.now(timezone.utc)
        start_ts = start_time.isoformat()
        
        stdout_data = []
        stderr_data = []
        exit_code = 0
        status = "passed"
        error_summary = None
        
        try:
            if self.stream_output and on_output:
                # Stream output in real-time
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                    cwd=cwd,
                    text=True,
                    bufsize=1,
                )
                
                import selectors
                sel = selectors.DefaultSelector()
                sel.register(process.stdout, selectors.EVENT_READ)
                sel.register(process.stderr, selectors.EVENT_READ)
                
                deadline = time.time() + timeout
                
                while process.poll() is None:
                    remaining = deadline - time.time()
                    if remaining <= 0:
                        process.terminate()
                        try:
                            process.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            process.kill()
                        status = "timeout"
                        break
                    
                    events = sel.select(timeout=min(0.1, remaining))
                    for key, _ in events:
                        line = key.fileobj.readline()
                        if line:
                            if key.fileobj == process.stdout:
                                stdout_data.append(line)
                                on_output(line, 'stdout')
                            else:
                                stderr_data.append(line)
                                on_output(line, 'stderr')
                
                sel.close()
                
                # Read remaining output
                if process.stdout:
                    remaining_stdout = process.stdout.read()
                    if remaining_stdout:
                        stdout_data.append(remaining_stdout)
                if process.stderr:
                    remaining_stderr = process.stderr.read()
                    if remaining_stderr:
                        stderr_data.append(remaining_stderr)
                
                exit_code = process.returncode or 0
                
            else:
                # Capture output without streaming
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=env,
                    cwd=cwd,
                )
                exit_code = result.returncode
                stdout_data = [result.stdout] if result.stdout else []
                stderr_data = [result.stderr] if result.stderr else []
                
        except subprocess.TimeoutExpired:
            status = "timeout"
        except Exception as e:
            status = "failed"
            error_summary = str(e)
            exit_code = 1
        
        # Record end time
        end_time = datetime.now(timezone.utc)
        end_ts = end_time.isoformat()
        duration = (end_time - start_time).total_seconds()
        
        # Process output
        stdout_str = ''.join(stdout_data)
        stderr_str = ''.join(stderr_data)
        
        # Determine final status
        if status != "timeout":
            if exit_code != 0:
                if meta.xfail:
                    status = "xfail"
                else:
                    status = "failed"
                    # Extract error summary from stderr
                    if stderr_str:
                        lines = stderr_str.strip().split('\n')
                        error_summary = lines[-1][:200] if lines else None
            else:
                status = "passed"
        
        return ExampleResult(
            path=path,
            slug=slug,
            status=status,
            exit_code=exit_code,
            duration_seconds=duration,
            start_time=start_ts,
            end_time=end_ts,
            skip_reason=None,
            error_summary=error_summary,
            stderr_tail=stderr_str[-500:] if stderr_str else None,
            stdout=stdout_str if self.capture_output else None,
            stderr=stderr_str if self.capture_output else None,
        )


class ReportGenerator:
    """Generates JSON and Markdown reports from run results."""
    
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_json(self, report: RunReport) -> Path:
        """Generate JSON report file."""
        data = {
            "metadata": {
                "timestamp": report.timestamp,
                "platform": report.platform_info,
                "python_version": report.python_version,
                "praisonai_version": report.praisonai_version,
                "git_commit": report.git_commit,
                "cli_args": report.cli_args,
                "totals": report.totals,
            },
            "examples": [
                {
                    "path": str(ex.path),
                    "slug": ex.slug,
                    "status": ex.status,
                    "exit_code": ex.exit_code,
                    "duration_seconds": ex.duration_seconds,
                    "start_time": ex.start_time,
                    "end_time": ex.end_time,
                    "skip_reason": ex.skip_reason,
                    "error_summary": ex.error_summary,
                    "stderr_tail": ex.stderr_tail,
                    "stdout_path": f"logs/{ex.slug}.stdout.log" if ex.stdout else None,
                    "stderr_path": f"logs/{ex.slug}.stderr.log" if ex.stderr else None,
                }
                for ex in report.examples
            ],
        }
        
        json_path = self.output_dir / "report.json"
        json_path.write_text(json.dumps(data, indent=2))
        return json_path
    
    def generate_markdown(self, report: RunReport) -> Path:
        """Generate Markdown report file."""
        totals = report.totals
        total_count = sum(totals.values())
        
        lines = [
            "# Examples Run Report",
            "",
            f"**Generated**: {report.timestamp}",
            f"**Platform**: {report.platform_info}",
            f"**Python**: {report.python_version}",
            f"**PraisonAI**: {report.praisonai_version}",
        ]
        
        if report.git_commit:
            lines.append(f"**Git Commit**: {report.git_commit}")
        
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
            f"| ⚠️ XFail | {totals['xfail']} |",
            f"| **Total** | **{total_count}** |",
            "",
            "## Results",
            "",
            "| Example | Status | Duration |",
            "|---------|--------|----------|",
        ])
        
        status_icons = {
            "passed": "✅",
            "failed": "❌",
            "skipped": "⏭️",
            "timeout": "⏱️",
            "xfail": "⚠️",
        }
        
        for ex in report.examples:
            icon = status_icons.get(ex.status, "?")
            duration = f"{ex.duration_seconds:.2f}s" if ex.duration_seconds else "-"
            lines.append(f"| `{ex.path.name}` | {icon} {ex.status} | {duration} |")
        
        # Add failures section
        failures = [ex for ex in report.examples if ex.status == "failed"]
        if failures:
            lines.extend([
                "",
                "## Failures",
                "",
            ])
            for ex in failures:
                lines.extend([
                    f"### {ex.path.name}",
                    "",
                    f"**Path**: `{ex.path}`",
                    f"**Exit Code**: {ex.exit_code}",
                    "",
                ])
                if ex.error_summary:
                    lines.extend([
                        "**Error**:",
                        "```",
                        ex.error_summary,
                        "```",
                        "",
                    ])
                if ex.stderr_path:
                    lines.append(f"**Logs**: `{ex.stderr_path}`")
                lines.append("")
        
        md_path = self.output_dir / "report.md"
        md_path.write_text('\n'.join(lines))
        return md_path
    
    def save_logs(self, report: RunReport) -> Path:
        """Save stdout/stderr logs for each example."""
        logs_dir = self.output_dir / "logs"
        logs_dir.mkdir(exist_ok=True)
        
        for ex in report.examples:
            if ex.stdout:
                stdout_path = logs_dir / f"{ex.slug}.stdout.log"
                stdout_path.write_text(ex.stdout)
                ex.stdout_path = f"logs/{ex.slug}.stdout.log"
            
            if ex.stderr:
                stderr_path = logs_dir / f"{ex.slug}.stderr.log"
                stderr_path.write_text(ex.stderr)
                ex.stderr_path = f"logs/{ex.slug}.stderr.log"
        
        return logs_dir


class ExamplesExecutor:
    """Main orchestrator for running examples suite."""
    
    def __init__(
        self,
        path: Path,
        timeout: int = 60,
        fail_fast: bool = False,
        stream_output: bool = True,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        require_env: Optional[List[str]] = None,
        report_dir: Optional[Path] = None,
        generate_json: bool = True,
        generate_md: bool = True,
    ):
        self.path = Path(path).resolve()
        self.timeout = timeout
        self.fail_fast = fail_fast
        self.stream_output = stream_output
        self.include_patterns = include_patterns
        self.exclude_patterns = exclude_patterns
        self.require_env = require_env or []
        self.report_dir = report_dir
        self.generate_json = generate_json
        self.generate_md = generate_md
    
    def _get_pythonpath(self) -> List[str]:
        """Get PYTHONPATH additions for local package imports."""
        paths = []
        
        # Try to find src directories
        current = self.path
        for _ in range(5):  # Look up to 5 levels
            src_dir = current / "src"
            if src_dir.exists():
                # Add all immediate subdirs of src
                for subdir in src_dir.iterdir():
                    if subdir.is_dir() and not subdir.name.startswith('.'):
                        paths.append(str(subdir))
                break
            
            # Also check for praisonai-agents and praisonai directly
            for pkg in ["praisonai-agents", "praisonai"]:
                pkg_dir = current / "src" / pkg
                if pkg_dir.exists():
                    paths.append(str(pkg_dir))
            
            parent = current.parent
            if parent == current:
                break
            current = parent
        
        return paths
    
    def run(
        self,
        on_example_start: Optional[Callable[[Path, int, int], None]] = None,
        on_example_end: Optional[Callable[[ExampleResult, int, int], None]] = None,
        on_output: Optional[Callable[[str, str], None]] = None,
    ) -> RunReport:
        """Run all discovered examples and return report."""
        # Discover examples
        discovery = ExampleDiscovery(
            self.path,
            include_patterns=self.include_patterns,
            exclude_patterns=self.exclude_patterns,
        )
        examples = discovery.discover()
        
        # Check global required env
        for key in self.require_env:
            if not os.environ.get(key):
                # Skip all examples if global env requirement not met
                return RunReport(
                    examples=[
                        ExampleResult(
                            path=ex,
                            slug=ex.stem,
                            status="skipped",
                            skip_reason=f"Global required env missing: {key}",
                        )
                        for ex in examples
                    ],
                    cli_args=[],
                )
        
        # Create runner
        runner = ExampleRunner(
            timeout=self.timeout,
            capture_output=True,
            stream_output=self.stream_output,
            pythonpath_additions=self._get_pythonpath(),
        )
        
        results = []
        total = len(examples)
        
        for idx, example_path in enumerate(examples, 1):
            if on_example_start:
                on_example_start(example_path, idx, total)
            
            result = runner.run(
                example_path,
                root=self.path,
                on_output=on_output if self.stream_output else None,
            )
            results.append(result)
            
            if on_example_end:
                on_example_end(result, idx, total)
            
            # Check fail-fast
            if self.fail_fast and result.status == "failed":
                # Mark remaining as skipped
                for remaining_path in examples[idx:]:
                    results.append(ExampleResult(
                        path=remaining_path,
                        slug=remaining_path.stem,
                        status="skipped",
                        skip_reason="Skipped due to --fail-fast",
                    ))
                break
        
        # Create report
        report = RunReport(
            examples=results,
            cli_args=[],  # Will be set by CLI
        )
        
        # Generate reports if configured
        if self.report_dir:
            generator = ReportGenerator(self.report_dir)
            generator.save_logs(report)
            
            if self.generate_json:
                generator.generate_json(report)
            
            if self.generate_md:
                generator.generate_markdown(report)
        
        return report
