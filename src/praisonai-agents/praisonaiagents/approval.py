"""
Human Approval Framework for PraisonAI Agents

This module provides a minimal human-in-the-loop approval system for dangerous tool operations.
It extends the existing callback system to require human approval before executing high-risk tools.
"""

import logging
import asyncio
from typing import Dict, Set, Optional, Callable, Any, Literal
from functools import wraps
from contextvars import ContextVar
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Confirm

# Global registries for approval requirements
APPROVAL_REQUIRED_TOOLS: Set[str] = set()
TOOL_RISK_LEVELS: Dict[str, str] = {}

# Risk levels
RiskLevel = Literal["critical", "high", "medium", "low"]

# Global approval callback
approval_callback: Optional[Callable] = None

# Context variable to track if we're in an approved execution context
_approved_context: ContextVar[Set[str]] = ContextVar('approved_context', default=set())

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

def mark_approved(tool_name: str):
    """Mark a tool as approved in the current context."""
    approved = _approved_context.get(set())
    approved.add(tool_name)
    _approved_context.set(approved)

def is_already_approved(tool_name: str) -> bool:
    """Check if a tool is already approved in the current context."""
    approved = _approved_context.get(set())
    return tool_name in approved

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
                callback = approval_callback or console_approval_callback
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
    callback = approval_callback or console_approval_callback
    
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