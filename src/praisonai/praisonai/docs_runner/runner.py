"""
Snippet Runner for executing code blocks.

Runs extracted code blocks in isolated subprocesses with:
- Timeout handling
- Output capture and streaming
- Environment configuration
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable, List


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


class SnippetRunner:
    """Runs code snippets in isolated subprocesses."""
    
    def __init__(
        self,
        timeout: int = 60,
        capture_output: bool = True,
        stream_output: bool = False,
        env_overrides: Optional[dict] = None,
        pythonpath_additions: Optional[List[str]] = None,
        cwd: Optional[Path] = None,
    ):
        """
        Initialize runner.
        
        Args:
            timeout: Per-snippet timeout in seconds.
            capture_output: Whether to capture stdout/stderr.
            stream_output: Whether to stream output in real-time.
            env_overrides: Environment variable overrides.
            pythonpath_additions: Paths to add to PYTHONPATH.
            cwd: Working directory for script execution.
        """
        self.timeout = timeout
        self.capture_output = capture_output
        self.stream_output = stream_output
        self.env_overrides = env_overrides or {}
        self.pythonpath_additions = pythonpath_additions or []
        self.cwd = cwd
    
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
        script_path: Path,
        require_env: Optional[List[str]] = None,
        custom_timeout: Optional[int] = None,
        on_output: Optional[Callable[[str, str], None]] = None,
    ) -> SnippetResult:
        """
        Run a script and return result.
        
        Args:
            script_path: Path to the Python script.
            require_env: Required environment variables.
            custom_timeout: Override default timeout.
            on_output: Callback for streaming output.
            
        Returns:
            SnippetResult with execution details.
        """
        require_env = require_env or []
        timeout = custom_timeout if custom_timeout is not None else self.timeout
        
        # Check required env
        missing_env = self.check_required_env(require_env)
        if missing_env:
            return SnippetResult(
                doc_path=script_path,
                block_index=0,
                language="python",
                line_start=0,
                line_end=0,
                runnable_decision="",
                status="skipped",
                skip_reason=f"Missing required env: {missing_env}",
            )
        
        # Build command
        cmd = [sys.executable, '-u', str(script_path)]
        env = self._build_env()
        cwd = self.cwd or script_path.parent
        
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
                status = "failed"
                # Extract error summary from stderr
                if stderr_str:
                    lines = stderr_str.strip().split('\n')
                    error_summary = lines[-1][:200] if lines else None
            else:
                status = "passed"
        
        return SnippetResult(
            doc_path=script_path,
            block_index=0,
            language="python",
            line_start=0,
            line_end=0,
            runnable_decision="",
            status=status,
            exit_code=exit_code,
            duration_seconds=duration,
            start_time=start_ts,
            end_time=end_ts,
            error_summary=error_summary,
            stdout=stdout_str if self.capture_output else "",
            stderr=stderr_str if self.capture_output else "",
        )
