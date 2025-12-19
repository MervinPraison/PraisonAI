"""
Autonomy Modes for PraisonAI CLI.

Inspired by Codex CLI's approval modes and Gemini CLI's approval settings.
Provides configurable autonomy levels: suggest, auto-edit, full-auto.

Architecture:
- AutonomyMode: Enum for different autonomy levels
- AutonomyPolicy: Policy configuration for each mode
- AutonomyManager: Manages mode transitions and approvals
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Set
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class AutonomyMode(Enum):
    """
    Autonomy levels for agent execution.
    
    Inspired by Codex CLI's approval modes:
    - SUGGEST: Read-only, requires approval for all changes
    - AUTO_EDIT: Auto-approve file edits, require approval for commands
    - FULL_AUTO: Auto-approve everything (YOLO mode)
    """
    SUGGEST = "suggest"          # Default: ask for approval on everything
    AUTO_EDIT = "auto_edit"      # Auto-approve file edits only
    FULL_AUTO = "full_auto"      # Auto-approve everything (dangerous)
    
    @classmethod
    def from_string(cls, value: str) -> "AutonomyMode":
        """Parse mode from string."""
        value = value.lower().strip().replace("-", "_")
        for mode in cls:
            if mode.value == value:
                return mode
        raise ValueError(f"Unknown autonomy mode: {value}")


class ActionType(Enum):
    """Types of actions that require approval."""
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    SHELL_COMMAND = "shell_command"
    NETWORK_REQUEST = "network_request"
    CODE_EXECUTION = "code_execution"
    GIT_OPERATION = "git_operation"
    TOOL_CALL = "tool_call"


@dataclass
class ActionRequest:
    """
    Request for an action that may require approval.
    
    Attributes:
        action_type: Type of action
        description: Human-readable description
        details: Additional details (file path, command, etc.)
        risk_level: Estimated risk (low, medium, high)
        reversible: Whether the action can be undone
    """
    action_type: ActionType
    description: str
    details: Dict[str, Any] = field(default_factory=dict)
    risk_level: str = "medium"
    reversible: bool = True
    
    def __str__(self) -> str:
        return f"{self.action_type.value}: {self.description}"


@dataclass
class ApprovalResult:
    """Result of an approval request."""
    approved: bool
    reason: Optional[str] = None
    modified_action: Optional[ActionRequest] = None
    remember_choice: bool = False


@dataclass
class AutonomyPolicy:
    """
    Policy configuration for autonomy mode.
    
    Defines which actions are auto-approved, require approval,
    or are blocked entirely.
    """
    mode: AutonomyMode
    
    # Actions that are auto-approved
    auto_approve: Set[ActionType] = field(default_factory=set)
    
    # Actions that always require approval
    require_approval: Set[ActionType] = field(default_factory=set)
    
    # Actions that are blocked entirely
    blocked: Set[ActionType] = field(default_factory=set)
    
    # Trusted paths for file operations
    trusted_paths: Set[str] = field(default_factory=set)
    
    # Trusted commands (patterns)
    trusted_commands: Set[str] = field(default_factory=set)
    
    # Maximum auto-approved actions before requiring confirmation
    max_auto_actions: int = 10
    
    # Whether to show what would be done in suggest mode
    show_preview: bool = True
    
    @classmethod
    def for_mode(cls, mode: AutonomyMode) -> "AutonomyPolicy":
        """Create default policy for a given mode."""
        if mode == AutonomyMode.SUGGEST:
            return cls(
                mode=mode,
                auto_approve={ActionType.FILE_READ},
                require_approval={
                    ActionType.FILE_WRITE,
                    ActionType.FILE_DELETE,
                    ActionType.SHELL_COMMAND,
                    ActionType.CODE_EXECUTION,
                    ActionType.GIT_OPERATION,
                    ActionType.NETWORK_REQUEST,
                    ActionType.TOOL_CALL,
                },
                blocked=set(),
                show_preview=True
            )
        elif mode == AutonomyMode.AUTO_EDIT:
            return cls(
                mode=mode,
                auto_approve={
                    ActionType.FILE_READ,
                    ActionType.FILE_WRITE,
                    ActionType.TOOL_CALL,
                },
                require_approval={
                    ActionType.FILE_DELETE,
                    ActionType.SHELL_COMMAND,
                    ActionType.CODE_EXECUTION,
                    ActionType.GIT_OPERATION,
                    ActionType.NETWORK_REQUEST,
                },
                blocked=set(),
                show_preview=True
            )
        elif mode == AutonomyMode.FULL_AUTO:
            return cls(
                mode=mode,
                auto_approve={
                    ActionType.FILE_READ,
                    ActionType.FILE_WRITE,
                    ActionType.FILE_DELETE,
                    ActionType.SHELL_COMMAND,
                    ActionType.CODE_EXECUTION,
                    ActionType.GIT_OPERATION,
                    ActionType.NETWORK_REQUEST,
                    ActionType.TOOL_CALL,
                },
                require_approval=set(),
                blocked=set(),
                show_preview=False,
                max_auto_actions=100
            )
        else:
            raise ValueError(f"Unknown mode: {mode}")


class AutonomyManager:
    """
    Manages autonomy mode and approval flow.
    
    Handles:
    - Mode transitions
    - Approval requests
    - Action tracking
    - Policy enforcement
    """
    
    def __init__(
        self,
        mode: AutonomyMode = AutonomyMode.SUGGEST,
        policy: Optional[AutonomyPolicy] = None,
        approval_callback: Optional[Callable[[ActionRequest], ApprovalResult]] = None,
        verbose: bool = False
    ):
        self.mode = mode
        self.policy = policy or AutonomyPolicy.for_mode(mode)
        self.approval_callback = approval_callback or self._default_approval
        self.verbose = verbose
        
        # Tracking
        self._action_count = 0
        self._auto_approved_count = 0
        self._denied_count = 0
        self._remembered_approvals: Dict[str, bool] = {}
    
    def set_mode(self, mode: AutonomyMode) -> None:
        """Change the autonomy mode."""
        old_mode = self.mode
        self.mode = mode
        self.policy = AutonomyPolicy.for_mode(mode)
        
        if self.verbose:
            logger.info(f"Autonomy mode changed: {old_mode.value} -> {mode.value}")
    
    def request_approval(self, action: ActionRequest) -> ApprovalResult:
        """
        Request approval for an action.
        
        Returns:
            ApprovalResult with approval decision
        """
        self._action_count += 1
        
        # Check if blocked
        if action.action_type in self.policy.blocked:
            self._denied_count += 1
            return ApprovalResult(
                approved=False,
                reason=f"Action type '{action.action_type.value}' is blocked by policy"
            )
        
        # Check remembered approvals
        action_key = self._get_action_key(action)
        if action_key in self._remembered_approvals:
            approved = self._remembered_approvals[action_key]
            if approved:
                self._auto_approved_count += 1
            else:
                self._denied_count += 1
            return ApprovalResult(approved=approved, reason="Remembered choice")
        
        # Check if auto-approved
        if action.action_type in self.policy.auto_approve:
            # Check max auto actions
            if self._auto_approved_count >= self.policy.max_auto_actions:
                # Force approval after max auto actions
                return self._request_user_approval(action)
            
            self._auto_approved_count += 1
            return ApprovalResult(approved=True, reason="Auto-approved by policy")
        
        # Check if requires approval
        if action.action_type in self.policy.require_approval:
            return self._request_user_approval(action)
        
        # Default: require approval for unknown action types
        return self._request_user_approval(action)
    
    def _request_user_approval(self, action: ActionRequest) -> ApprovalResult:
        """Request approval from user via callback."""
        result = self.approval_callback(action)
        
        if result.remember_choice:
            action_key = self._get_action_key(action)
            self._remembered_approvals[action_key] = result.approved
        
        if result.approved:
            self._auto_approved_count += 1
        else:
            self._denied_count += 1
        
        return result
    
    def _get_action_key(self, action: ActionRequest) -> str:
        """Generate a key for remembering approval decisions."""
        # Use action type and relevant details
        key_parts = [action.action_type.value]
        
        if "path" in action.details:
            key_parts.append(action.details["path"])
        if "command" in action.details:
            key_parts.append(action.details["command"])
        
        return ":".join(key_parts)
    
    def _default_approval(self, action: ActionRequest) -> ApprovalResult:
        """Default approval callback using console input."""
        from rich.console import Console
        from rich.panel import Panel
        from rich.prompt import Confirm
        
        console = Console()
        
        # Build action description
        risk_color = {
            "low": "green",
            "medium": "yellow",
            "high": "red"
        }.get(action.risk_level, "white")
        
        details_str = "\n".join(
            f"  {k}: {v}" for k, v in action.details.items()
        ) if action.details else "  (no details)"
        
        panel_content = f"""
[bold]{action.description}[/bold]

Type: {action.action_type.value}
Risk: [{risk_color}]{action.risk_level}[/{risk_color}]
Reversible: {"Yes" if action.reversible else "No"}

Details:
{details_str}
"""
        
        console.print(Panel(
            panel_content,
            title="🔒 Approval Required",
            border_style="yellow"
        ))
        
        approved = Confirm.ask("Approve this action?", default=False)
        remember = False
        
        if approved:
            remember = Confirm.ask("Remember this choice for similar actions?", default=False)
        
        return ApprovalResult(
            approved=approved,
            remember_choice=remember
        )
    
    def get_stats(self) -> Dict[str, int]:
        """Get approval statistics."""
        return {
            "total_actions": self._action_count,
            "auto_approved": self._auto_approved_count,
            "denied": self._denied_count,
            "remembered": len(self._remembered_approvals)
        }
    
    def reset_stats(self) -> None:
        """Reset approval statistics."""
        self._action_count = 0
        self._auto_approved_count = 0
        self._denied_count = 0
    
    def clear_remembered(self) -> None:
        """Clear remembered approval decisions."""
        self._remembered_approvals.clear()


# ============================================================================
# CLI Integration Handler
# ============================================================================

class AutonomyModeHandler:
    """
    Handler for integrating autonomy modes with PraisonAI CLI.
    """
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._manager: Optional[AutonomyManager] = None
    
    @property
    def feature_name(self) -> str:
        return "autonomy_mode"
    
    def initialize(
        self,
        mode: str = "suggest",
        approval_callback: Optional[Callable[[ActionRequest], ApprovalResult]] = None
    ) -> AutonomyManager:
        """
        Initialize the autonomy manager.
        
        Args:
            mode: Autonomy mode string (suggest, auto_edit, full_auto)
            approval_callback: Optional custom approval callback
            
        Returns:
            Configured AutonomyManager
        """
        try:
            autonomy_mode = AutonomyMode.from_string(mode)
        except ValueError:
            logger.warning(f"Unknown mode '{mode}', defaulting to 'suggest'")
            autonomy_mode = AutonomyMode.SUGGEST
        
        self._manager = AutonomyManager(
            mode=autonomy_mode,
            approval_callback=approval_callback,
            verbose=self.verbose
        )
        
        if self.verbose:
            from rich import print as rprint
            rprint(f"[cyan]Autonomy mode: {autonomy_mode.value}[/cyan]")
        
        return self._manager
    
    def get_manager(self) -> Optional[AutonomyManager]:
        """Get the current autonomy manager."""
        return self._manager
    
    def request_approval(self, action: ActionRequest) -> ApprovalResult:
        """Request approval for an action."""
        if not self._manager:
            self._manager = self.initialize()
        
        return self._manager.request_approval(action)
    
    def set_mode(self, mode: str) -> None:
        """Change the autonomy mode."""
        if not self._manager:
            self.initialize(mode)
        else:
            try:
                autonomy_mode = AutonomyMode.from_string(mode)
                self._manager.set_mode(autonomy_mode)
            except ValueError as e:
                logger.error(f"Failed to set mode: {e}")
    
    def get_mode(self) -> str:
        """Get the current autonomy mode."""
        if self._manager:
            return self._manager.mode.value
        return AutonomyMode.SUGGEST.value


# ============================================================================
# Convenience Functions
# ============================================================================

def create_file_write_action(path: str, content_preview: str = "") -> ActionRequest:
    """Create an action request for file write."""
    return ActionRequest(
        action_type=ActionType.FILE_WRITE,
        description=f"Write to file: {path}",
        details={
            "path": path,
            "preview": content_preview[:200] if content_preview else "(no preview)"
        },
        risk_level="medium",
        reversible=True
    )


def create_shell_command_action(command: str, cwd: str = ".") -> ActionRequest:
    """Create an action request for shell command."""
    # Assess risk based on command
    dangerous_patterns = ["rm ", "sudo ", "chmod ", "chown ", "> /", "| sh", "curl |"]
    risk = "high" if any(p in command for p in dangerous_patterns) else "medium"
    
    return ActionRequest(
        action_type=ActionType.SHELL_COMMAND,
        description=f"Execute command: {command}",
        details={
            "command": command,
            "cwd": cwd
        },
        risk_level=risk,
        reversible=False
    )


def create_git_action(operation: str, details: Dict[str, Any] = None) -> ActionRequest:
    """Create an action request for git operation."""
    return ActionRequest(
        action_type=ActionType.GIT_OPERATION,
        description=f"Git {operation}",
        details=details or {},
        risk_level="low" if operation in ["status", "log", "diff"] else "medium",
        reversible=operation not in ["push", "force-push"]
    )


def create_tool_call_action(tool_name: str, args: Dict[str, Any] = None) -> ActionRequest:
    """Create an action request for tool call."""
    return ActionRequest(
        action_type=ActionType.TOOL_CALL,
        description=f"Call tool: {tool_name}",
        details={
            "tool": tool_name,
            "args": args or {}
        },
        risk_level="low",
        reversible=True
    )
