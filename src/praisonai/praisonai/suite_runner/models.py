"""
Shared data models for suite execution.

Provides unified dataclasses used by both examples and docs runners.
"""

from __future__ import annotations

import hashlib
import platform
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any


@dataclass
class RunItem:
    """
    Represents a single runnable item (example file or doc code block).
    
    Unified structure for both examples and docs suites.
    """
    
    # Identity
    item_id: str  # Unique stable identifier
    suite: str  # "examples" or "docs"
    group: str  # Top-level directory/category
    
    # Source
    source_path: Path  # Original file path
    block_index: int = 0  # For docs: which code block (0 for examples)
    language: str = "python"
    line_start: int = 0
    line_end: int = 0
    
    # Content
    code: str = ""  # The actual code content
    script_path: Optional[Path] = None  # Path to materialized script
    
    # Classification
    runnable: bool = True
    runnable_decision: str = ""  # Reason for classification
    
    # Directives
    skip: bool = False
    skip_reason: Optional[str] = None
    timeout: Optional[int] = None
    require_env: List[str] = field(default_factory=list)
    xfail: Optional[str] = None
    is_interactive: bool = False
    
    # Metadata
    title: Optional[str] = None
    
    # Agent-centric detection
    uses_agent: bool = False  # Agent() class
    uses_agents: bool = False  # AgentManager() / PraisonAIAgents class
    uses_workflow: bool = False  # Workflow class
    
    # Server detection
    is_server: bool = False  # Contains server code (uvicorn, Flask, streamlit, etc.)
    
    @property
    def agent_type(self) -> str:
        """Get agent type used in this item."""
        types = []
        if self.uses_agent:
            types.append("Agent")
        if self.uses_agents:
            types.append("Agents")
        if self.uses_workflow:
            types.append("Workflow")
        return ",".join(types) if types else "none"
    
    @property
    def code_hash(self) -> str:
        """Generate short hash of code content."""
        return hashlib.sha256(self.code.encode()).hexdigest()[:16]
    
    @property
    def display_name(self) -> str:
        """Human-readable display name."""
        if self.suite == "docs":
            return f"{self.source_path.name}:{self.block_index}"
        return self.source_path.name


@dataclass
class RunResult:
    """
    Result of executing a single RunItem.
    
    Unified structure for both examples and docs execution results.
    """
    
    # Link to item
    item_id: str
    suite: str
    group: str
    source_path: Path
    block_index: int = 0
    language: str = "python"
    line_start: int = 0
    line_end: int = 0
    
    # Classification
    runnable_decision: str = ""
    
    # Execution result
    status: str = "not_run"  # passed, failed, skipped, timeout, not_run, xfail
    exit_code: int = 0
    duration_seconds: float = 0.0
    start_time: str = ""
    end_time: str = ""
    
    # Error info
    skip_reason: Optional[str] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    
    # Output
    stdout: str = ""
    stderr: str = ""
    stdout_path: Optional[str] = None
    stderr_path: Optional[str] = None
    
    # Execution context
    python_executable: str = ""
    cwd: str = ""
    env_requirements: str = ""  # Comma-separated
    code_hash: str = ""
    
    @property
    def display_name(self) -> str:
        """Human-readable display name."""
        if self.suite == "docs":
            return f"{self.source_path.name}:{self.block_index}"
        return self.source_path.name


@dataclass
class RunReport:
    """
    Complete report from a suite execution run.
    
    Aggregates all results with metadata.
    """
    
    # Results
    results: List[RunResult] = field(default_factory=list)
    
    # Context
    suite: str = ""  # "examples", "docs", or "mixed"
    source_path: Path = field(default_factory=Path)
    report_path: Optional[Path] = None
    cli_args: List[str] = field(default_factory=list)
    
    # Metadata (populated on creation)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    platform_info: str = field(default_factory=lambda: f"{platform.system()}-{platform.release()}-{platform.machine()}")
    python_version: str = field(default_factory=lambda: platform.python_version())
    python_executable: str = ""
    praisonai_version: str = ""
    git_commit: Optional[str] = None
    
    # Grouping
    groups_run: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Populate version info."""
        import sys
        self.python_executable = sys.executable
        
        try:
            from praisonai.version import __version__
            self.praisonai_version = __version__
        except ImportError:
            self.praisonai_version = "unknown"
        
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
    def totals(self) -> Dict[str, int]:
        """Calculate totals by status."""
        counts = {
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "timeout": 0,
            "not_run": 0,
            "xfail": 0,
            "total": 0,
        }
        for r in self.results:
            counts["total"] += 1
            if r.status in counts:
                counts[r.status] += 1
        return counts
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "metadata": {
                "suite": self.suite,
                "source_path": str(self.source_path),
                "timestamp": self.timestamp,
                "platform": self.platform_info,
                "python_version": self.python_version,
                "python_executable": self.python_executable,
                "praisonai_version": self.praisonai_version,
                "git_commit": self.git_commit,
                "cli_args": self.cli_args,
                "groups_run": self.groups_run,
                "totals": self.totals,
            },
            "results": [
                {
                    "item_id": r.item_id,
                    "suite": r.suite,
                    "group": r.group,
                    "source_path": str(r.source_path),
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
                    "error_type": r.error_type,
                    "error_message": r.error_message,
                    "stdout_path": r.stdout_path,
                    "stderr_path": r.stderr_path,
                    "python_executable": r.python_executable,
                    "cwd": r.cwd,
                    "env_requirements": r.env_requirements,
                    "code_hash": r.code_hash,
                }
                for r in self.results
            ],
        }
