"""
Unified Script Runner for suite execution.

Provides subprocess execution with streaming, timeouts, and output capture.
Used by both examples and docs runners.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable, List

from .models import RunItem, RunResult


class ScriptRunner:
    """
    Runs scripts in isolated subprocesses.
    
    Unified runner for both examples and docs suites.
    """
    
    def __init__(
        self,
        timeout: int = 60,
        capture_output: bool = True,
        stream_output: bool = False,
        env_overrides: Optional[dict] = None,
        pythonpath_additions: Optional[List[str]] = None,
        cwd: Optional[Path] = None,
        python_executable: Optional[str] = None,
    ):
        """
        Initialize runner.
        
        Args:
            timeout: Per-script timeout in seconds.
            capture_output: Whether to capture stdout/stderr.
            stream_output: Whether to stream output in real-time.
            env_overrides: Environment variable overrides.
            pythonpath_additions: Paths to add to PYTHONPATH.
            cwd: Working directory for script execution.
            python_executable: Python interpreter to use (default: sys.executable).
        """
        self.timeout = timeout
        self.capture_output = capture_output
        self.stream_output = stream_output
        self.env_overrides = env_overrides or {}
        self.pythonpath_additions = pythonpath_additions or []
        self.cwd = cwd
        self.python_executable = python_executable or sys.executable
    
    def _build_env(self) -> dict:
        """Build environment for subprocess."""
        env = os.environ.copy()
        
        # Add PYTHONPATH
        pythonpath_parts = list(self.pythonpath_additions)
        existing = env.get('PYTHONPATH', '')
        if existing:
            pythonpath_parts.append(existing)
        
        if pythonpath_parts:
            env['PYTHONPATH'] = os.pathsep.join(pythonpath_parts)
        
        # Apply overrides
        env.update(self.env_overrides)
        
        return env
    
    def check_required_env(self, require_env: List[str]) -> Optional[str]:
        """
        Check if required env vars are present.
        
        Returns:
            Missing var name or None if all present.
        """
        for key in require_env:
            if not os.environ.get(key):
                return key
        return None
    
    def run(
        self,
        item: RunItem,
        on_output: Optional[Callable[[str, str], None]] = None,
    ) -> RunResult:
        """
        Run a script and return result.
        
        Args:
            item: RunItem with script_path set.
            on_output: Callback for streaming output (line, stream_type).
            
        Returns:
            RunResult with execution details.
        """
        script_path = item.script_path
        if not script_path or not script_path.exists():
            return RunResult(
                item_id=item.item_id,
                suite=item.suite,
                group=item.group,
                source_path=item.source_path,
                block_index=item.block_index,
                language=item.language,
                line_start=item.line_start,
                line_end=item.line_end,
                runnable_decision=item.runnable_decision,
                status="failed",
                error_type="FileNotFound",
                error_message=f"Script not found: {script_path}",
                code_hash=item.code_hash,
            )
        
        # Check required env
        if item.require_env:
            missing = self.check_required_env(item.require_env)
            if missing:
                return RunResult(
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
                    skip_reason=f"Missing required env: {missing}",
                    env_requirements=",".join(item.require_env),
                    code_hash=item.code_hash,
                )
        
        # Determine timeout
        timeout = item.timeout if item.timeout else self.timeout
        
        # Build command
        cmd = [self.python_executable, '-u', str(script_path)]
        env = self._build_env()
        cwd = self.cwd or script_path.parent
        
        # Record start time
        start_time = datetime.now(timezone.utc)
        start_ts = start_time.isoformat()
        
        stdout_data = []
        stderr_data = []
        exit_code = 0
        status = "passed"
        error_type = None
        error_message = None
        
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
            error_type = "TimeoutError"
            error_message = f"Exceeded {timeout}s timeout"
        except Exception as e:
            status = "failed"
            error_type = type(e).__name__
            error_message = str(e)
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
                if item.xfail:
                    status = "xfail"
                else:
                    status = "failed"
                    # Extract error info from stderr
                    if stderr_str:
                        lines = stderr_str.strip().split('\n')
                        if lines:
                            error_message = lines[-1][:500]
                            # Try to extract error type
                            for line in reversed(lines):
                                if ': ' in line:
                                    parts = line.split(': ', 1)
                                    if parts[0].endswith('Error') or parts[0].endswith('Exception'):
                                        error_type = parts[0].split('.')[-1]
                                        break
            else:
                status = "passed"
        
        return RunResult(
            item_id=item.item_id,
            suite=item.suite,
            group=item.group,
            source_path=item.source_path,
            block_index=item.block_index,
            language=item.language,
            line_start=item.line_start,
            line_end=item.line_end,
            runnable_decision=item.runnable_decision,
            status=status,
            exit_code=exit_code,
            duration_seconds=duration,
            start_time=start_ts,
            end_time=end_ts,
            error_type=error_type,
            error_message=error_message,
            stdout=stdout_str if self.capture_output else "",
            stderr=stderr_str if self.capture_output else "",
            python_executable=self.python_executable,
            cwd=str(cwd),
            env_requirements=",".join(item.require_env) if item.require_env else "",
            code_hash=item.code_hash,
        )
