"""
DoctorContractProtocol for runtime config migration.

Provides a protocol for third-party migration rules and built-in rules
for migrating legacy configuration fields like cli_backend to the new
model-scoped runtime configuration.
"""

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
from dataclasses import dataclass


@dataclass
class Finding:
    """Represents a migration finding from a doctor rule."""
    
    rule_id: str
    severity: str  # "warning", "error", "info"
    message: str
    fix_description: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


@dataclass
class ConfigDiff:
    """A per-rule before/after change produced by a repair."""

    rule_id: str
    before: Dict[str, Any]
    after: Dict[str, Any]

    def unified_diff(self) -> str:
        """Render a unified before/after diff for previewing the change."""
        import difflib
        import json

        before_lines = json.dumps(self.before, indent=2, sort_keys=True, default=str).splitlines()
        after_lines = json.dumps(self.after, indent=2, sort_keys=True, default=str).splitlines()
        diff = difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=f"{self.rule_id} (before)",
            tofile=f"{self.rule_id} (after)",
            lineterm="",
        )
        return "\n".join(diff)


@dataclass
class RepairPlan:
    """
    Result of a doctor repair pass, carrying the safety contract surface.

    In dry-run mode nothing is written; ``config`` holds the proposed result and
    ``diffs`` describes each change so a caller can preview before applying.
    """

    config: Dict[str, Any]
    diffs: List[ConfigDiff]
    backup_path: Optional[str] = None
    residual_findings: Optional[List[Finding]] = None
    refused: Optional[List[Finding]] = None
    applied: bool = False

    def __post_init__(self) -> None:
        if self.residual_findings is None:
            self.residual_findings = []
        if self.refused is None:
            self.refused = []

    @property
    def has_changes(self) -> bool:
        """True if any rule proposed a change."""
        return len(self.diffs) > 0

    def render_diffs(self) -> str:
        """Render all per-rule unified diffs joined together."""
        return "\n".join(d.unified_diff() for d in self.diffs)


@runtime_checkable
class DoctorContractProtocol(Protocol):
    """
    Protocol for doctor migration rules.
    
    Third-party plugins can implement this protocol to provide custom
    migration rules for agent configurations.
    """
    
    @property
    def rule_id(self) -> str:
        """Unique identifier for this migration rule."""
        ...
    
    def collect_findings(self, config: Dict[str, Any]) -> List[Finding]:
        """
        Analyze configuration and collect migration findings.
        
        Args:
            config: Agent configuration dictionary (from YAML or Python)
            
        Returns:
            List of findings for this configuration
        """
        ...
    
    def apply_fix(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply migration fixes to configuration.
        
        Args:
            config: Agent configuration dictionary
            
        Returns:
            Updated configuration dictionary
        """
        ...