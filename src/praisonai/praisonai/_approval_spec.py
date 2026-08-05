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
    
    def _resolve_backend(self):
        """Resolve ``self.backend`` (a name) to a core approval backend, or None.

        ``"auto"`` / ``"none"`` mean "do not prompt" (auto-approve / disabled),
        so they resolve to ``None`` and the hook falls through to allow. Only the
        backends we can construct without extra config are wired here; unknown
        names return ``None`` so we never block on a backend we can't drive.
        """
        if self.backend in (None, "none", "auto"):
            return None
        try:
            if self.backend == "console":
                from praisonaiagents.approval.backends import ConsoleBackend
                return ConsoleBackend()
        except ImportError:
            return None
        return None

    def install_hook(self) -> None:
        """Install a before_tool hook to enforce approval."""
        try:
            from praisonaiagents.hooks import add_hook
            from praisonaiagents.hooks.events import BeforeToolInput
            from praisonaiagents.hooks.types import HookResult
        except ImportError:
            logger.warning("Could not import praisonaiagents.hooks - approval enforcement unavailable")
            return

        backend = self._resolve_backend()

        def approval_hook(data: BeforeToolInput) -> Optional[HookResult]:
            """Check if tool execution should be approved."""
            if not self.enabled:
                return None  # No opinion, let other hooks decide

            tool_name = data.tool_name

            # Per-tool override: an explicit level entry means this tool must be
            # gated regardless of the default policy.
            requires_prompt = self.default_policy == "prompt"
            if self.approve_tools and tool_name in self.approve_tools:
                requires_prompt = True

            # `approve_all_tools` / --trust auto-approve everything.
            if self.approve_all_tools or self.backend == "auto":
                return None

            if self.default_policy == "deny":
                logger.warning(f"Tool {tool_name} denied by default policy")
                return HookResult.deny(f"Tool {tool_name} denied by default policy")
            if self.default_policy == "allow" and not (
                self.approve_tools and tool_name in self.approve_tools
            ):
                return None

            if not requires_prompt:
                return None

            # Prompt via the resolved backend. Without a usable backend we cannot
            # obtain consent, so fail safe by denying instead of silently allowing.
            if backend is None:
                logger.warning(
                    "Tool %s requires approval but no usable backend (%s); denying.",
                    tool_name, self.backend,
                )
                return HookResult.deny(
                    f"Tool {tool_name} requires approval but backend {self.backend!r} is unavailable"
                )

            try:
                from praisonaiagents.approval.protocols import ApprovalRequest
                level = None
                if self.approve_tools:
                    level = self.approve_tools.get(tool_name)
                request = ApprovalRequest(
                    tool_name=tool_name,
                    arguments=dict(getattr(data, "tool_input", {}) or {}),
                    risk_level=level or self.approve_level or "medium",
                )
                decision = backend.request_approval_sync(request)
            except Exception as exc:  # noqa: BLE001 - fail safe on any backend error
                logger.error("Approval backend error for %s: %s", tool_name, exc)
                return HookResult.deny(f"Approval error for {tool_name}: {exc}")

            if getattr(decision, "approved", False):
                return None
            return HookResult.deny(
                getattr(decision, "reason", None) or f"Tool {tool_name} denied"
            )

        add_hook("before_tool", approval_hook)
        logger.info("Approval hook installed")
