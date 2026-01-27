"""
Human Approval Framework for PraisonAI Agents

This module provides a minimal human-in-the-loop approval system for dangerous tool operations.
It extends the existing callback system to require human approval before executing high-risk tools.
"""

import logging
import asyncio
import json
import os
from typing import Dict, Set, Optional, Callable, Any, Literal, List
from functools import wraps
import contextvars
from contextvars import ContextVar
from dataclasses import dataclass, field

# Lazy import for rich components
_rich_console = None
_rich_panel = None
_rich_confirm = None

def _get_rich_console():
    """Lazy import rich Console."""
    global _rich_console
    if _rich_console is None:
        from rich.console import Console
        _rich_console = Console
    return _rich_console

def _get_rich_panel():
    """Lazy import rich Panel."""
    global _rich_panel
    if _rich_panel is None:
        from rich.panel import Panel
        _rich_panel = Panel
    return _rich_panel

def _get_rich_confirm():
    """Lazy import rich Confirm."""
    global _rich_confirm
    if _rich_confirm is None:
        from rich.prompt import Confirm
        _rich_confirm = Confirm
    return _rich_confirm

# Global registries for approval requirements
APPROVAL_REQUIRED_TOOLS: Set[str] = set()
TOOL_RISK_LEVELS: Dict[str, str] = {}

# Risk levels
RiskLevel = Literal["critical", "high", "medium", "low"]

# Global approval callback
approval_callback: Optional[Callable] = None

# Context variable to track if we're in an approved execution context
_approved_context: ContextVar[Set[str]] = ContextVar('approved_context', default=set())

# Context variable for YAML-defined auto-approved tools (from agents.yaml approve field)
_yaml_approved_tools: ContextVar[Set[str]] = ContextVar('yaml_approved_tools', default=set())

# Global permission allowlist
_permission_allowlist: Optional["PermissionAllowlist"] = None


@dataclass
class ToolPermission:
    """Permission entry for a tool."""
    tool_name: str
    allowed_paths: List[str] = field(default_factory=list)
    session_only: bool = False  # If True, permission expires with session


class PermissionAllowlist:
    """
    Persistent permission allowlist for tools.
    
    Allows pre-approving tools and paths to skip interactive approval.
    Can be saved/loaded from JSON for persistence across sessions.
    
    Usage:
        allowlist = PermissionAllowlist()
        allowlist.add_tool("read_file")
        allowlist.add_tool("write_file", paths=["./src", "./tests"])
        
        if allowlist.is_allowed("read_file"):
            # Skip approval prompt
            pass
    """
    
    def __init__(self):
        self._tools: Dict[str, ToolPermission] = {}
        self._session_tools: Set[str] = set()
        
    def add_tool(
        self, 
        tool_name: str, 
        paths: Optional[List[str]] = None,
        session_only: bool = False
    ) -> None:
        """
        Add a tool to the allowlist.
        
        Args:
            tool_name: Name of the tool to allow
            paths: Optional list of allowed paths (empty = all paths)
            session_only: If True, permission expires with session
        """
        self._tools[tool_name] = ToolPermission(
            tool_name=tool_name,
            allowed_paths=paths or [],
            session_only=session_only
        )
        if session_only:
            self._session_tools.add(tool_name)
            
    def remove_tool(self, tool_name: str) -> bool:
        """Remove a tool from the allowlist."""
        if tool_name in self._tools:
            del self._tools[tool_name]
            self._session_tools.discard(tool_name)
            return True
        return False
    
    def is_allowed(self, tool_name: str, path: Optional[str] = None) -> bool:
        """
        Check if a tool is allowed.
        
        Args:
            tool_name: Name of the tool
            path: Optional path to check against allowed paths
            
        Returns:
            True if tool is allowed (optionally for the given path)
        """
        if tool_name not in self._tools:
            return False
            
        permission = self._tools[tool_name]
        
        # If no paths specified, tool is allowed for all paths
        if not permission.allowed_paths:
            return True
            
        # If path not provided, check if tool has any permissions
        if path is None:
            return True
            
        # Check if path matches any allowed path
        for allowed_path in permission.allowed_paths:
            # Normalize paths for comparison
            norm_allowed = os.path.normpath(allowed_path)
            norm_path = os.path.normpath(path)
            
            # Check if path starts with allowed path
            if norm_path.startswith(norm_allowed):
                return True
                
        return False
    
    def is_empty(self) -> bool:
        """Check if allowlist is empty."""
        return len(self._tools) == 0
    
    def list_tools(self) -> List[str]:
        """List all allowed tools."""
        return list(self._tools.keys())
    
    def clear_session_permissions(self) -> None:
        """Clear session-only permissions."""
        for tool_name in list(self._session_tools):
            if tool_name in self._tools:
                del self._tools[tool_name]
        self._session_tools.clear()
    
    def save(self, filepath: str) -> None:
        """Save allowlist to JSON file."""
        data = {
            "tools": {
                name: {
                    "allowed_paths": perm.allowed_paths,
                    "session_only": perm.session_only
                }
                for name, perm in self._tools.items()
                if not perm.session_only  # Don't persist session-only permissions
            }
        }
        
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
    
    @classmethod
    def load(cls, filepath: str) -> "PermissionAllowlist":
        """Load allowlist from JSON file."""
        allowlist = cls()
        
        if not os.path.exists(filepath):
            return allowlist
            
        with open(filepath, "r") as f:
            data = json.load(f)
            
        for tool_name, tool_data in data.get("tools", {}).items():
            allowlist.add_tool(
                tool_name,
                paths=tool_data.get("allowed_paths", []),
                session_only=tool_data.get("session_only", False)
            )
            
        return allowlist


def get_permission_allowlist() -> PermissionAllowlist:
    """Get the global permission allowlist."""
    global _permission_allowlist
    if _permission_allowlist is None:
        _permission_allowlist = PermissionAllowlist()
    return _permission_allowlist


def set_permission_allowlist(allowlist: PermissionAllowlist) -> None:
    """Set the global permission allowlist."""
    global _permission_allowlist
    _permission_allowlist = allowlist


class ApprovalDecision:
    """Result of an approval request"""
    def __init__(self, approved: bool, modified_args: Optional[Dict[str, Any]] = None, reason: str = ""):
        self.approved = approved
        self.modified_args = modified_args or {}
        self.reason = reason

def set_approval_callback(callback_fn: Callable):
    """Set a custom approval callback function.
    
    The callback should accept (function_name, arguments, risk_level) and return ApprovalDecision.
    """
    global approval_callback
    approval_callback = callback_fn

def get_approval_callback() -> Optional[Callable]:
    """Get the current approval callback function.
    
    Returns the custom callback if set, otherwise None.
    This should be used instead of directly accessing approval_callback
    to ensure the latest callback is always used.
    """
    return approval_callback

def mark_approved(tool_name: str):
    """Mark a tool as approved in the current context."""
    approved = _approved_context.get(set())
    approved.add(tool_name)
    _approved_context.set(approved)

def is_already_approved(tool_name: str) -> bool:
    """Check if a tool is already approved in the current context."""
    approved = _approved_context.get(set())
    return tool_name in approved


def is_yaml_approved(tool_name: str) -> bool:
    """Check if a tool is auto-approved via YAML approve field."""
    try:
        yaml_approved = _yaml_approved_tools.get()
        return tool_name in yaml_approved
    except LookupError:
        return False


def is_env_auto_approve() -> bool:
    """Check if PRAISONAI_AUTO_APPROVE environment variable is set."""
    return os.environ.get("PRAISONAI_AUTO_APPROVE", "").lower() in ("true", "1", "yes")


def set_yaml_approved_tools(tools: List[str]) -> contextvars.Token:
    """
    Set the list of YAML-approved tools for the current context.
    
    This is called by the workflow runner when parsing agents.yaml with approve field.
    
    Args:
        tools: List of tool names to auto-approve
        
    Returns:
        Token that can be used to reset the context
    """
    return _yaml_approved_tools.set(set(tools))


def reset_yaml_approved_tools(token: contextvars.Token) -> None:
    """Reset YAML-approved tools to previous state."""
    _yaml_approved_tools.reset(token)


def clear_approval_context():
    """Clear the approval context."""
    _approved_context.set(set())

def require_approval(risk_level: RiskLevel = "high"):
    """Decorator to mark a tool as requiring human approval.
    
    Args:
        risk_level: The risk level of the tool ("critical", "high", "medium", "low")
    """
    def decorator(func):
        tool_name = getattr(func, '__name__', str(func))
        APPROVAL_REQUIRED_TOOLS.add(tool_name)
        TOOL_RISK_LEVELS[tool_name] = risk_level
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Skip approval if already approved in current context
            if is_already_approved(tool_name):
                return func(*args, **kwargs)
            
            # Skip approval if tool is auto-approved via YAML approve field (primary)
            if is_yaml_approved(tool_name):
                mark_approved(tool_name)
                return func(*args, **kwargs)
            
            # Skip approval if PRAISONAI_AUTO_APPROVE env var is set (secondary)
            if is_env_auto_approve():
                mark_approved(tool_name)
                return func(*args, **kwargs)
            
            # Request approval before executing the function
            try:
                # Try to check if we're in an async context
                try:
                    asyncio.get_running_loop()
                    # We're in an async context, but this is a sync function
                    # Fall back to sync approval to avoid loop conflicts
                    raise RuntimeError("Use sync fallback in async context")
                except RuntimeError:
                    # Either no running loop or we want sync fallback
                    # Use asyncio.run for clean async execution
                    decision = asyncio.run(request_approval(tool_name, kwargs))
            except Exception as e:
                # Fallback to sync approval if async fails
                logging.warning(f"Async approval failed, using sync fallback: {e}")
                callback = get_approval_callback() or console_approval_callback
                decision = callback(tool_name, kwargs, risk_level)
            
            if not decision.approved:
                raise PermissionError(f"Execution of {tool_name} denied: {decision.reason}")
            
            # Mark as approved and merge modified args
            mark_approved(tool_name)
            kwargs.update(decision.modified_args)
            return func(*args, **kwargs)
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Skip approval if already approved in current context
            if is_already_approved(tool_name):
                return await func(*args, **kwargs)
            
            # Skip approval if tool is auto-approved via YAML approve field (primary)
            if is_yaml_approved(tool_name):
                mark_approved(tool_name)
                return await func(*args, **kwargs)
            
            # Skip approval if PRAISONAI_AUTO_APPROVE env var is set (secondary)
            if is_env_auto_approve():
                mark_approved(tool_name)
                return await func(*args, **kwargs)
            
            # Request approval before executing the function
            decision = await request_approval(tool_name, kwargs)
            if not decision.approved:
                raise PermissionError(f"Execution of {tool_name} denied: {decision.reason}")
            
            # Mark as approved and merge modified args
            mark_approved(tool_name)
            kwargs.update(decision.modified_args)
            return await func(*args, **kwargs)
        
        # Return the appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return wrapper
    
    return decorator

def console_approval_callback(function_name: str, arguments: Dict[str, Any], risk_level: str) -> ApprovalDecision:
    """Default console-based approval callback.
    
    Displays tool information and prompts user for approval via console.
    """
    Console = _get_rich_console()
    Panel = _get_rich_panel()
    Confirm = _get_rich_confirm()
    
    console = Console()
    
    # Create risk level styling
    risk_colors = {
        "critical": "bold red",
        "high": "red", 
        "medium": "yellow",
        "low": "blue"
    }
    risk_color = risk_colors.get(risk_level, "white")
    
    # Display tool information
    tool_info = f"[bold]Function:[/] {function_name}\n"
    tool_info += f"[bold]Risk Level:[/] [{risk_color}]{risk_level.upper()}[/{risk_color}]\n"
    tool_info += f"[bold]Arguments:[/]\n"
    
    for key, value in arguments.items():
        # Truncate long values for display
        str_value = str(value)
        if len(str_value) > 100:
            str_value = str_value[:97] + "..."
        tool_info += f"  {key}: {str_value}\n"
    
    console.print(Panel(
        tool_info.strip(),
        title="🔒 Tool Approval Required",
        border_style=risk_color,
        title_align="left"
    ))
    
    # Get user approval
    try:
        approved = Confirm.ask(
            f"[{risk_color}]Do you want to execute this {risk_level} risk tool?[/{risk_color}]",
            default=False
        )
        
        if approved:
            console.print("[green]✅ Tool execution approved[/green]")
            return ApprovalDecision(approved=True, reason="User approved")
        else:
            console.print("[red]❌ Tool execution denied[/red]")
            return ApprovalDecision(approved=False, reason="User denied")
            
    except KeyboardInterrupt:
        console.print("\n[red]❌ Tool execution cancelled by user[/red]")
        return ApprovalDecision(approved=False, reason="User cancelled")
    except Exception as e:
        console.print(f"[red]Error during approval: {e}[/red]")
        return ApprovalDecision(approved=False, reason=f"Approval error: {e}")

async def request_approval(function_name: str, arguments: Dict[str, Any]) -> ApprovalDecision:
    """Request approval for a tool execution.
    
    Args:
        function_name: Name of the function to execute
        arguments: Arguments to pass to the function
        
    Returns:
        ApprovalDecision with approval status and any modifications
    """
    # Check if approval is required
    if function_name not in APPROVAL_REQUIRED_TOOLS:
        return ApprovalDecision(approved=True, reason="No approval required")
    
    risk_level = TOOL_RISK_LEVELS.get(function_name, "medium")
    
    # Use custom callback if set, otherwise use console callback
    callback = get_approval_callback() or console_approval_callback
    
    try:
        # Handle async callbacks
        if asyncio.iscoroutinefunction(callback):
            decision = await callback(function_name, arguments, risk_level)
        else:
            # Run sync callback in executor to avoid blocking
            loop = asyncio.get_event_loop()
            decision = await loop.run_in_executor(None, callback, function_name, arguments, risk_level)
        
        return decision
        
    except Exception as e:
        logging.error(f"Error in approval callback: {e}")
        return ApprovalDecision(approved=False, reason=f"Approval callback error: {e}")

# Default dangerous tools - can be configured at runtime
DEFAULT_DANGEROUS_TOOLS = {
    # Critical risk tools
    "execute_command": "critical",
    "kill_process": "critical", 
    "execute_code": "critical",
    
    # High risk tools
    "write_file": "high",
    "delete_file": "high",
    "move_file": "high",
    "copy_file": "high",
    "execute_query": "high",
    
    # Medium risk tools
    "evaluate": "medium",
    "crawl": "medium",
    "scrape_page": "medium",
}

def configure_default_approvals():
    """Configure default dangerous tools to require approval."""
    for tool_name, risk_level in DEFAULT_DANGEROUS_TOOLS.items():
        APPROVAL_REQUIRED_TOOLS.add(tool_name)
        TOOL_RISK_LEVELS[tool_name] = risk_level

def add_approval_requirement(tool_name: str, risk_level: RiskLevel = "high"):
    """Dynamically add approval requirement for a tool."""
    APPROVAL_REQUIRED_TOOLS.add(tool_name)
    TOOL_RISK_LEVELS[tool_name] = risk_level

def remove_approval_requirement(tool_name: str):
    """Remove approval requirement for a tool."""
    APPROVAL_REQUIRED_TOOLS.discard(tool_name)
    TOOL_RISK_LEVELS.pop(tool_name, None)

def is_approval_required(tool_name: str) -> bool:
    """Check if a tool requires approval."""
    return tool_name in APPROVAL_REQUIRED_TOOLS

def get_risk_level(tool_name: str) -> Optional[str]:
    """Get the risk level of a tool."""
    return TOOL_RISK_LEVELS.get(tool_name)

# Initialize with defaults
configure_default_approvals()