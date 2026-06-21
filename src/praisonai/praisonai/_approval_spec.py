"""
Approval specification module - unified approval configuration across CLI, YAML, Python.

This module provides a single canonical ApprovalSpec dataclass that all three 
surfaces (CLI, YAML, Python) normalize into, preventing fragmentation and
ensuring consistent behavior across all entry points.
"""
from dataclasses import dataclass
from typing import Optional, Literal, Union, Dict, Any
import logging

Backend = Literal["console", "slack", "telegram", "discord", "webhook", "http", "agent", "auto", "none"]
ApprovalLevel = Literal["low", "medium", "high", "critical"]
DefaultPolicy = Literal["deny", "prompt", "allow"]

logger = logging.getLogger(__name__)


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
    enabled: bool = True  # Safe by default
    backend: Backend = "console"
    approve_all_tools: bool = False
    timeout: Optional[float] = None
    approve_level: Optional[ApprovalLevel] = None
    guardrails: Optional[str] = None
    default_policy: DefaultPolicy = "prompt"  # New: default approval policy
    approve_tools: Optional[Dict[str, ApprovalLevel]] = None  # New: per-tool granularity

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
                "approve_level", "guardrails", "default_policy", "approve_tools",
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
                default_policy=node.get("default_policy", "prompt"),  # type: ignore[arg-type]
                approve_tools=node.get("approve_tools"),
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
        if self.default_policy != "prompt":
            result["default_policy"] = self.default_policy
        if self.approve_tools is not None:
            result["approve_tools"] = self.approve_tools
        return result
    
    def install_hook(self) -> None:
        """Install a before_tool hook to enforce approval."""
        try:
            from praisonaiagents.hooks import add_hook
            from praisonaiagents.hooks.events import BeforeToolInput
            from praisonaiagents.hooks.types import HookResult
            
            def approval_hook(data: BeforeToolInput) -> Optional[HookResult]:
                """Check if tool execution should be approved."""
                if not self.enabled:
                    return None  # No opinion, let other hooks decide
                
                tool_name = data.tool_name
                
                # Check per-tool policy
                if self.approve_tools and tool_name in self.approve_tools:
                    level = self.approve_tools[tool_name]
                    # TODO: Implement actual approval logic based on level
                    logger.debug(f"Tool {tool_name} requires approval level: {level}")
                
                # Apply default policy
                if self.default_policy == "deny":
                    logger.warning(f"Tool {tool_name} denied by default policy")
                    return HookResult.deny(f"Tool {tool_name} denied by default policy")
                elif self.default_policy == "allow":
                    return None  # Allow
                else:  # "prompt"
                    # TODO: Implement prompting logic based on backend
                    logger.info(f"Tool {tool_name} would prompt for approval (backend: {self.backend})")
                    return None
            
            add_hook("before_tool", approval_hook)
            logger.info("Approval hook installed")
        except ImportError:
            logger.warning("Could not import praisonaiagents.hooks - approval enforcement unavailable")
