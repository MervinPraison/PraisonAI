"""
DoctorContractProtocol for runtime config migration.

Provides a protocol for third-party migration rules and built-in rules
for migrating legacy configuration fields like cli_backend to the new
model-scoped runtime configuration.
"""

import abc
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


@runtime_checkable
class DoctorContractProtocol(Protocol):
    """
    Protocol for doctor migration rules.
    
    Third-party plugins can implement this protocol to provide custom
    migration rules for agent configurations.
    """
    
    @property
    @abc.abstractmethod
    def rule_id(self) -> str:
        """Unique identifier for this migration rule."""
        ...
    
    @abc.abstractmethod
    def collect_findings(self, config: Dict[str, Any]) -> List[Finding]:
        """
        Analyze configuration and collect migration findings.
        
        Args:
            config: Agent configuration dictionary (from YAML or Python)
            
        Returns:
            List of findings for this configuration
        """
        ...
    
    @abc.abstractmethod
    def apply_fix(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply migration fixes to configuration.
        
        Args:
            config: Agent configuration dictionary
            
        Returns:
            Updated configuration dictionary
        """
        ...