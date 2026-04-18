"""
Approval specification module - unified approval configuration across CLI, YAML, Python.

This module provides a single canonical ApprovalSpec dataclass that all three 
surfaces (CLI, YAML, Python) normalize into, preventing fragmentation and
ensuring consistent behavior across all entry points.
"""
from dataclasses import dataclass
from typing import Optional, Literal, Union, Dict, Any

Backend = Literal["console", "slack", "telegram", "discord", "webhook", "http", "agent", "auto", "none"]
ApprovalLevel = Literal["low", "medium", "high", "critical"]


def _parse_timeout(timeout_val: Optional[Union[str, int, float]]) -> Optional[float]:
    """Parse timeout value to float, handling 'none' case."""
    if timeout_val is None:
        return None
    if isinstance(timeout_val, str) and timeout_val.lower() == 'none':
        return None
    try:
        return float(timeout_val)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid timeout value: {timeout_val}")


@dataclass(frozen=True)
class ApprovalSpec:
    """
    Unified approval specification for CLI, YAML, and Python APIs.
    
    This replaces the fragmented approval configuration scattered across
    multiple fields and provides consistent behavior across all surfaces.
    """
    enabled: bool = False
    backend: Backend = "console"
    approve_all_tools: bool = False
    timeout: Optional[float] = None
    approve_level: Optional[ApprovalLevel] = None
    guardrails: Optional[str] = None

    @classmethod
    def from_cli(cls, args) -> "ApprovalSpec":
        """
        Create ApprovalSpec from CLI arguments.
        
        Handles --trust, --approval, --approve-all-tools, --approval-timeout,
        --approve-level, and --guardrail flags.
        """
        # Determine if approval is enabled from any of the CLI flags
        enabled = bool(
            getattr(args, 'trust', False) or 
            getattr(args, 'approval', None) or 
            getattr(args, 'approve_all_tools', False) or 
            getattr(args, 'approve_level', None)
        )
        
        # Determine backend
        if getattr(args, 'trust', False):
            backend = "auto"  # --trust means auto-approve
        elif getattr(args, 'approval', None):
            backend = args.approval
        else:
            backend = "console" if enabled else "none"
        
        return cls(
            enabled=enabled,
            backend=backend,  # type: ignore[arg-type]
            approve_all_tools=bool(getattr(args, 'approve_all_tools', False)),
            timeout=_parse_timeout(getattr(args, 'approval_timeout', None)),
            approve_level=getattr(args, 'approve_level', None),
            guardrails=getattr(args, 'guardrail', None),
        )

    @classmethod
    def from_yaml(cls, node: Union[None, bool, str, Dict[str, Any]]) -> "ApprovalSpec":
        """
        Create ApprovalSpec from YAML approval configuration.
        
        Accepts:
        - None/False: disabled
        - True: enabled with console backend  
        - str: enabled with specified backend
        - dict: full configuration
        
        Validates keys to prevent silent typos.
        """
        if node is None or node is False:
            return cls(enabled=False, backend="none")
        if node is True:
            return cls(enabled=True, backend="console")
        if isinstance(node, str):
            return cls(enabled=True, backend=node)  # type: ignore[arg-type]
        if isinstance(node, dict):
            # Validate allowed keys to catch typos early
            allowed = {
                "enabled", "backend", "approve_all_tools", "timeout", 
                "approve_level", "guardrails",
                # Legacy aliases for backward compatibility
                "backend_name", "all_tools", "approval_timeout"
            }
            unknown = set(node) - allowed
            if unknown:
                raise ValueError(f"Unknown approval keys: {sorted(unknown)}. Allowed: {sorted(allowed)}")
            
            # Handle legacy aliases
            backend = node.get("backend") or node.get("backend_name", "console")
            if "approve_all_tools" in node:
                approve_all_tools = node.get("approve_all_tools")
            else:
                approve_all_tools = node.get("all_tools", False)
            if "timeout" in node:
                timeout_val = node.get("timeout")
            else:
                timeout_val = node.get("approval_timeout")
            
            return cls(
                enabled=node.get("enabled", True),
                backend=backend,  # type: ignore[arg-type]
                approve_all_tools=bool(approve_all_tools),
                timeout=_parse_timeout(timeout_val) if timeout_val is not None else None,
                approve_level=node.get("approve_level"),
                guardrails=node.get("guardrails"),
            )
        raise TypeError(f"Unsupported approval node type: {type(node).__name__}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for backward compatibility with existing code."""
        result = {
            "enabled": self.enabled,
            "backend": self.backend,
            "approve_all_tools": self.approve_all_tools,
        }
        if self.timeout is not None:
            result["timeout"] = self.timeout
        if self.approve_level is not None:
            result["approve_level"] = self.approve_level
        if self.guardrails is not None:
            result["guardrails"] = self.guardrails
        return result
