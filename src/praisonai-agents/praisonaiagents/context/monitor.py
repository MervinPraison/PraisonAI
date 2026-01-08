"""
Context Monitor for PraisonAI Agents.

Writes runtime context to disk for inspection and debugging.
"""

from typing import Dict, List, Any, Optional, Literal, Tuple
from pathlib import Path
from datetime import datetime
import json
import re

from .models import (
    ContextSnapshot, ContextLedger, BudgetAllocation, MonitorConfig, ContextSegment
)


def _format_pct(value: float) -> str:
    """Smart percentage formatting: <0.1% for tiny, 2 decimals for <1%, 1 decimal otherwise."""
    if value < 0.1 and value > 0:
        return "<0.1%"
    elif value < 1.0:
        return f"{value:.2f}%"
    else:
        return f"{value:.1f}%"


# Sensitive patterns for redaction
SENSITIVE_PATTERNS = [
    # OpenAI API keys
    r'sk-[a-zA-Z0-9]{20,}',
    r'sk-proj-[a-zA-Z0-9_-]+',
    # Anthropic API keys
    r'sk-ant-[a-zA-Z0-9_-]+',
    r'sk-ant-api\d+-[a-zA-Z0-9_-]+',
    # Google API keys and tokens
    r'AIza[a-zA-Z0-9_-]{30,}',  # Google API keys (30+ chars after prefix)
    r'ya29\.[a-zA-Z0-9_-]+',  # Google OAuth tokens
    r'goog-[a-zA-Z0-9_-]{20,}',  # Google service tokens
    # AWS credentials
    r'AKIA[0-9A-Z]{16}',  # AWS access keys
    r'ASIA[0-9A-Z]{16}',  # AWS temporary access keys
    r'aws_secret_access_key["\s:=]+["\']?[^"\'\s]+',
    # Azure credentials
    r'[a-zA-Z0-9]{8}-[a-zA-Z0-9]{4}-[a-zA-Z0-9]{4}-[a-zA-Z0-9]{4}-[a-zA-Z0-9]{12}',  # Azure GUIDs
    # Generic patterns
    r'[a-zA-Z0-9]{40,}',  # Generic long tokens (conservative)
    r'password["\s:=]+["\']?[^"\'\s]+',  # Password patterns
    r'secret["\s:=]+["\']?[^"\'\s]+',  # Secret patterns
    r'token["\s:=]+["\']?[^"\'\s]+',  # Token patterns
    r'api[_-]?key["\s:=]+["\']?[^"\'\s]+',  # API key patterns
    r'bearer\s+[a-zA-Z0-9_-]+',  # Bearer tokens
    r'authorization["\s:=]+["\']?[^"\'\s]+',  # Authorization headers
]


def redact_sensitive(text: str) -> str:
    """
    Redact sensitive information from text.
    
    Args:
        text: Text to redact
        
    Returns:
        Redacted text
    """
    result = text
    for pattern in SENSITIVE_PATTERNS:
        result = re.sub(pattern, '[REDACTED]', result, flags=re.IGNORECASE)
    return result


def validate_monitor_path(
    path: str,
    allow_absolute: bool = False,
    base_dir: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Validate monitor output path for security.
    
    Prevents path traversal attacks and enforces path restrictions.
    
    Args:
        path: Path to validate
        allow_absolute: Whether to allow absolute paths
        base_dir: Base directory for relative paths
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    from pathlib import Path as PathLib
    
    path_obj = PathLib(path)
    
    # Check for path traversal attempts
    if '..' in path_obj.parts:
        return False, "Path traversal (..) not allowed"
    
    # Check absolute path restriction
    if path_obj.is_absolute() and not allow_absolute:
        return False, "Absolute paths not allowed (set allow_absolute_paths=True to override)"
    
    # If base_dir specified, ensure path stays within it
    if base_dir:
        base = PathLib(base_dir).resolve()
        try:
            # For relative paths, resolve against base
            if not path_obj.is_absolute():
                full_path = (base / path_obj).resolve()
            else:
                full_path = path_obj.resolve()
            
            # Check if resolved path is under base
            if not str(full_path).startswith(str(base)):
                return False, f"Path must be within {base_dir}"
        except Exception as e:
            return False, f"Path validation error: {e}"
    
    # Check for suspicious patterns
    suspicious = ['/etc/', '/var/', '/usr/', '/root/', '/home/', '~']
    path_str = str(path_obj).lower()
    for pattern in suspicious:
        if pattern in path_str and not allow_absolute:
            return False, f"Suspicious path pattern: {pattern}"
    
    return True, ""


def should_include_content(
    file_path: str,
    ignore_patterns: Optional[List[str]] = None,
    include_patterns: Optional[List[str]] = None,
) -> bool:
    """
    Check if file content should be included based on ignore/include patterns.
    
    Respects .praisonignore and .praisoninclude rules.
    
    Args:
        file_path: Path to check
        ignore_patterns: Patterns to ignore (glob-style)
        include_patterns: Patterns to include (glob-style)
        
    Returns:
        True if content should be included
    """
    import fnmatch
    from pathlib import Path as PathLib
    
    path = PathLib(file_path)
    name = path.name
    
    # Default: include everything
    if not ignore_patterns and not include_patterns:
        return True
    
    # Check include patterns first (whitelist)
    if include_patterns:
        included = False
        for pattern in include_patterns:
            if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(str(path), pattern):
                included = True
                break
        if not included:
            return False
    
    # Check ignore patterns (blacklist)
    if ignore_patterns:
        for pattern in ignore_patterns:
            if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(str(path), pattern):
                return False
    
    return True


def load_ignore_patterns(base_dir: str = ".") -> Tuple[List[str], List[str]]:
    """
    Load ignore and include patterns from .praisonignore and .praisoninclude files.
    
    Args:
        base_dir: Directory to search for pattern files
        
    Returns:
        Tuple of (ignore_patterns, include_patterns)
    """
    from pathlib import Path as PathLib
    
    ignore_patterns = []
    include_patterns = []
    
    base = PathLib(base_dir)
    
    # Load .praisonignore
    ignore_file = base / ".praisonignore"
    if ignore_file.exists():
        try:
            content = ignore_file.read_text()
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith('#'):
                    ignore_patterns.append(line)
        except Exception:
            pass
    
    # Load .praisoninclude
    include_file = base / ".praisoninclude"
    if include_file.exists():
        try:
            content = include_file.read_text()
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith('#'):
                    include_patterns.append(line)
        except Exception:
            pass
    
    return ignore_patterns, include_patterns


def format_human_snapshot(snapshot: ContextSnapshot, redact: bool = True) -> str:
    """
    Format snapshot as human-readable text.
    
    Args:
        snapshot: Context snapshot
        redact: Whether to redact sensitive info
        
    Returns:
        Formatted text
    """
    lines = []
    
    # Header
    lines.append("=" * 80)
    lines.append("PRAISONAI CONTEXT SNAPSHOT")
    lines.append("=" * 80)
    lines.append(f"Timestamp: {snapshot.timestamp}")
    lines.append(f"Session ID: {snapshot.session_id}")
    lines.append(f"Agent: {snapshot.agent_name}")
    lines.append(f"Model: {snapshot.model_name}")
    
    if snapshot.budget:
        lines.append(f"Model Limit: {snapshot.budget.model_limit:,} tokens")
        lines.append(f"Output Reserve: {snapshot.budget.output_reserve:,} tokens")
        lines.append(f"Usable Budget: {snapshot.budget.usable:,} tokens")
    
    lines.append("")
    
    # Token Ledger
    lines.append("-" * 80)
    lines.append("TOKEN LEDGER")
    lines.append("-" * 80)
    lines.append(f"{'Component':<20} | {'Tokens':>10} | {'Budget':>10} | {'% Used':>8}")
    lines.append("-" * 20 + "-+-" + "-" * 10 + "-+-" + "-" * 10 + "-+-" + "-" * 8)
    
    if snapshot.ledger and snapshot.budget:
        segments = [
            (ContextSegment.SYSTEM_PROMPT, "System Prompt"),
            (ContextSegment.RULES, "Rules"),
            (ContextSegment.SKILLS, "Skills"),
            (ContextSegment.MEMORY, "Memory"),
            (ContextSegment.TOOLS_SCHEMA, "Tool Schemas"),
            (ContextSegment.HISTORY, "History"),
            (ContextSegment.TOOL_OUTPUTS, "Tool Outputs"),
        ]
        
        for seg, name in segments:
            tokens = snapshot.ledger.get_segment(seg)
            budget = snapshot.budget.get_segment_budget(seg)
            pct = (tokens / budget * 100) if budget > 0 else 0
            lines.append(f"{name:<20} | {tokens:>10,} | {budget:>10,} | {_format_pct(pct):>8}")
        
        lines.append("-" * 20 + "-+-" + "-" * 10 + "-+-" + "-" * 10 + "-+-" + "-" * 8)
        lines.append(f"{'TOTAL':<20} | {snapshot.ledger.total:>10,} | {snapshot.budget.usable:>10,} | {_format_pct(snapshot.utilization * 100):>8}")
    
    lines.append("")
    
    # Warnings
    if snapshot.warnings:
        lines.append("-" * 80)
        lines.append("WARNINGS")
        lines.append("-" * 80)
        for warning in snapshot.warnings:
            lines.append(f"⚠ {warning}")
        lines.append("")
    
    # History summary
    if snapshot.history_content:
        lines.append("-" * 80)
        lines.append(f"CONVERSATION HISTORY ({len(snapshot.history_content)} messages)")
        lines.append("-" * 80)
        
        for i, msg in enumerate(snapshot.history_content):
            role = msg.get("role", "unknown").upper()
            content = msg.get("content", "")
            
            if isinstance(content, str):
                if redact:
                    content = redact_sensitive(content)
                # Truncate for display
                if len(content) > 200:
                    content = content[:200] + "..."
                lines.append(f"[{i+1}] {role}: {content}")
            else:
                lines.append(f"[{i+1}] {role}: [complex content]")
        
        lines.append("")
    
    # Footer
    lines.append("=" * 80)
    lines.append("END CONTEXT SNAPSHOT")
    lines.append("=" * 80)
    
    return "\n".join(lines)


def format_json_snapshot(snapshot: ContextSnapshot, redact: bool = True) -> str:
    """
    Format snapshot as JSON.
    
    Args:
        snapshot: Context snapshot
        redact: Whether to redact sensitive info
        
    Returns:
        JSON string
    """
    data = snapshot.to_dict()
    
    # Add history with optional redaction
    if snapshot.history_content:
        history = []
        for msg in snapshot.history_content:
            msg_copy = msg.copy()
            content = msg_copy.get("content", "")
            if isinstance(content, str) and redact:
                msg_copy["content"] = redact_sensitive(content)
            history.append(msg_copy)
        data["history"] = history
    
    return json.dumps(data, indent=2, default=str)


class ContextMonitor:
    """
    Monitors and writes context to disk.
    
    Provides real-time visibility into context state for debugging
    and optimization.
    
    Example:
        monitor = ContextMonitor(
            enabled=True,
            path="./context.txt",
            format="human",
        )
        
        # Write snapshot
        monitor.snapshot(
            ledger=ledger,
            budget=budget,
            messages=messages,
            agent_name="Assistant",
        )
    """
    
    def __init__(
        self,
        enabled: bool = False,
        path: str = "./context.txt",
        format: Literal["human", "json"] = "human",
        frequency: Literal["turn", "tool_call", "manual", "overflow"] = "turn",
        redact_sensitive: bool = True,
        multi_agent_files: bool = True,
    ):
        """
        Initialize monitor.
        
        Args:
            enabled: Whether monitoring is enabled
            path: Output file path
            format: Output format (human or json)
            frequency: Update frequency
            redact_sensitive: Redact sensitive info
            multi_agent_files: Create per-agent files
        """
        self.enabled = enabled
        self.path = Path(path)
        self.format = format
        self.frequency = frequency
        self.redact = redact_sensitive
        self.multi_agent_files = multi_agent_files
        
        self._last_snapshot: Optional[ContextSnapshot] = None
        self._turn_count = 0
        self._tool_call_count = 0
    
    @classmethod
    def from_config(cls, config: MonitorConfig) -> "ContextMonitor":
        """Create monitor from config."""
        return cls(
            enabled=config.enabled,
            path=config.path,
            format=config.format,
            frequency=config.frequency,
            redact_sensitive=config.redact_sensitive,
            multi_agent_files=config.multi_agent_files,
        )
    
    def enable(self) -> None:
        """Enable monitoring."""
        self.enabled = True
    
    def disable(self) -> None:
        """Disable monitoring."""
        self.enabled = False
    
    def set_path(self, path: str) -> None:
        """Set output path."""
        self.path = Path(path)
    
    def set_format(self, format: Literal["human", "json"]) -> None:
        """Set output format."""
        self.format = format
    
    def set_frequency(self, frequency: Literal["turn", "tool_call", "manual", "overflow"]) -> None:
        """Set update frequency."""
        self.frequency = frequency
    
    def should_write(
        self,
        trigger: Literal["turn", "tool_call", "manual", "overflow"]
    ) -> bool:
        """Check if should write based on frequency."""
        if not self.enabled:
            return False
        
        if trigger == "manual":
            return True
        
        if self.frequency == "manual":
            return trigger == "manual"
        
        if self.frequency == "overflow":
            return trigger == "overflow"
        
        if self.frequency == "tool_call":
            return trigger in ("tool_call", "overflow")
        
        # frequency == "turn"
        return trigger in ("turn", "overflow")
    
    def snapshot(
        self,
        ledger: ContextLedger,
        budget: BudgetAllocation,
        messages: List[Dict[str, Any]],
        session_id: str = "",
        agent_name: str = "",
        model_name: str = "",
        trigger: Literal["turn", "tool_call", "manual", "overflow"] = "turn",
    ) -> Optional[str]:
        """
        Create and write a context snapshot.
        
        Args:
            ledger: Current token ledger
            budget: Budget allocation
            messages: Current messages
            session_id: Session identifier
            agent_name: Agent name
            model_name: Model name
            trigger: What triggered this snapshot
            
        Returns:
            Path to written file, or None if not written
        """
        if not self.should_write(trigger):
            return None
        
        # Track counts
        if trigger == "turn":
            self._turn_count += 1
        elif trigger == "tool_call":
            self._tool_call_count += 1
        
        # Create snapshot
        snapshot = ContextSnapshot(
            timestamp=datetime.utcnow().isoformat() + "Z",
            session_id=session_id,
            agent_name=agent_name,
            model_name=model_name,
            budget=budget,
            ledger=ledger,
            utilization=ledger.total / budget.usable if budget.usable > 0 else 0,
            history_content=messages,
            warnings=self._get_warnings(ledger, budget),
        )
        
        self._last_snapshot = snapshot
        
        # Determine output path
        output_path = self._get_output_path(agent_name)
        
        # Format content
        if self.format == "json":
            content = format_json_snapshot(snapshot, self.redact)
        else:
            content = format_human_snapshot(snapshot, self.redact)
        
        # Atomic write
        self._atomic_write(output_path, content)
        
        return str(output_path)
    
    def _get_output_path(self, agent_name: str = "") -> Path:
        """Get output path, optionally per-agent."""
        if not self.multi_agent_files or not agent_name:
            return self.path
        
        # Create per-agent path
        stem = self.path.stem
        suffix = self.path.suffix or (".json" if self.format == "json" else ".txt")
        
        # Sanitize agent name
        safe_name = re.sub(r'[^\w\-]', '_', agent_name.lower())
        
        return self.path.parent / f"{stem}_{safe_name}{suffix}"
    
    def _get_warnings(
        self,
        ledger: ContextLedger,
        budget: BudgetAllocation
    ) -> List[str]:
        """Generate warnings based on current state."""
        warnings = []
        
        utilization = ledger.total / budget.usable if budget.usable > 0 else 0
        
        if utilization >= 1.0:
            warnings.append(f"CRITICAL: Context overflow! {_format_pct(utilization*100)} of usable budget")
        elif utilization >= 0.9:
            warnings.append(f"WARNING: Context at {_format_pct(utilization*100)} of usable budget")
        elif utilization >= 0.8:
            warnings.append(f"NOTICE: Context at {_format_pct(utilization*100)} of usable budget")
        
        # Check individual segments
        if budget.tool_outputs > 0:
            tool_util = ledger.tool_outputs / budget.tool_outputs
            if tool_util >= 0.9:
                warnings.append(f"Tool outputs at {_format_pct(tool_util*100)} of budget")
        
        return warnings
    
    def _atomic_write(self, path: Path, content: str) -> None:
        """Write content atomically using temp file + rename."""
        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write to temp file
        temp_path = path.with_suffix(path.suffix + ".tmp")
        
        try:
            temp_path.write_text(content, encoding="utf-8")
            # Atomic rename
            temp_path.rename(path)
        except Exception:
            # Clean up temp file on error
            if temp_path.exists():
                temp_path.unlink()
            raise
    
    def get_last_snapshot(self) -> Optional[ContextSnapshot]:
        """Get the last snapshot."""
        return self._last_snapshot
    
    def get_stats(self) -> Dict[str, Any]:
        """Get monitor statistics."""
        return {
            "enabled": self.enabled,
            "path": str(self.path),
            "format": self.format,
            "frequency": self.frequency,
            "turn_count": self._turn_count,
            "tool_call_count": self._tool_call_count,
            "last_snapshot": self._last_snapshot.timestamp if self._last_snapshot else None,
        }


class MultiAgentMonitor:
    """
    Manages monitors for multiple agents.
    
    Creates per-agent monitors and optional combined view.
    """
    
    def __init__(
        self,
        base_path: str = "./context",
        format: Literal["human", "json"] = "human",
        enabled: bool = False,
        redact_sensitive: bool = True,
    ):
        """
        Initialize multi-agent monitor.
        
        Args:
            base_path: Base path for output files
            format: Output format
            enabled: Whether monitoring is enabled
            redact_sensitive: Redact sensitive info
        """
        self.base_path = Path(base_path)
        self.format = format
        self.enabled = enabled
        self.redact = redact_sensitive
        
        self._agents: Dict[str, ContextMonitor] = {}
    
    def get_agent_monitor(self, agent_id: str) -> ContextMonitor:
        """Get or create monitor for an agent."""
        if agent_id not in self._agents:
            suffix = ".json" if self.format == "json" else ".txt"
            safe_id = re.sub(r'[^\w\-]', '_', agent_id.lower())
            path = self.base_path / f"context_{safe_id}{suffix}"
            
            self._agents[agent_id] = ContextMonitor(
                enabled=self.enabled,
                path=str(path),
                format=self.format,
                redact_sensitive=self.redact,
                multi_agent_files=False,  # Already per-agent
            )
        
        return self._agents[agent_id]
    
    def enable_all(self) -> None:
        """Enable all monitors."""
        self.enabled = True
        for monitor in self._agents.values():
            monitor.enable()
    
    def disable_all(self) -> None:
        """Disable all monitors."""
        self.enabled = False
        for monitor in self._agents.values():
            monitor.disable()
    
    def get_agent_ids(self) -> List[str]:
        """Get list of monitored agent IDs."""
        return list(self._agents.keys())
