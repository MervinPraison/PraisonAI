"""
Built-in approval backends for PraisonAI Agents.

Provides two lightweight backends that ship with the core SDK:

- **AutoApproveBackend** — always approves (bots, trusted envs).
- **ConsoleBackend** — interactive Rich terminal prompt (CLI default).
"""

from __future__ import annotations

import asyncio
import logging

from .protocols import ApprovalDecision, ApprovalRequest

logger = logging.getLogger(__name__)

# Lazy Rich imports (same pattern as old approval.py)
_rich_console = None
_rich_panel = None
_rich_confirm = None


def _get_rich_console():
    global _rich_console
    if _rich_console is None:
        from rich.console import Console
        _rich_console = Console
    return _rich_console


def _get_rich_panel():
    global _rich_panel
    if _rich_panel is None:
        from rich.panel import Panel
        _rich_panel = Panel
    return _rich_panel


def _get_rich_confirm():
    global _rich_confirm
    if _rich_confirm is None:
        from rich.prompt import Confirm
        _rich_confirm = Confirm
    return _rich_confirm


class AutoApproveBackend:
    """Always approves.  Use for bots or trusted unattended environments."""

    async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        return ApprovalDecision(approved=True, reason="auto-approved", approver="system")

    def request_approval_sync(self, request: ApprovalRequest) -> ApprovalDecision:
        return ApprovalDecision(approved=True, reason="auto-approved", approver="system")


class ConsoleBackend:
    """Interactive Rich terminal prompt.  Default for CLI usage."""

    def _prompt_user(self, request: ApprovalRequest) -> bool:
        """Show Rich panel and ask yes/no.  Returns True if approved."""
        Console = _get_rich_console()
        Panel = _get_rich_panel()
        Confirm = _get_rich_confirm()

        console = Console()

        risk_colors = {
            "critical": "bold red",
            "high": "red",
            "medium": "yellow",
            "low": "blue",
        }
        risk_color = risk_colors.get(request.risk_level, "white")

        tool_info = f"[bold]Function:[/] {request.tool_name}\n"
        tool_info += f"[bold]Risk Level:[/] [{risk_color}]{request.risk_level.upper()}[/{risk_color}]\n"
        if request.agent_name:
            tool_info += f"[bold]Agent:[/] {request.agent_name}\n"
        tool_info += "[bold]Arguments:[/]\n"
        for key, value in request.arguments.items():
            str_value = str(value)
            if len(str_value) > 100:
                str_value = str_value[:97] + "..."
            tool_info += f"  {key}: {str_value}\n"

        console.print(Panel(
            tool_info.strip(),
            title="🔒 Tool Approval Required",
            border_style=risk_color,
            title_align="left",
        ))

        try:
            return Confirm.ask(
                f"[{risk_color}]Do you want to execute this {request.risk_level} risk tool?[/{risk_color}]",
                default=False,
            )
        except (KeyboardInterrupt, EOFError):
            return False

    def request_approval_sync(self, request: ApprovalRequest) -> ApprovalDecision:
        """Synchronous approval via Rich console prompt."""
        try:
            approved = self._prompt_user(request)
            if approved:
                return ApprovalDecision(approved=True, reason="User approved", approver="console")
            return ApprovalDecision(approved=False, reason="User denied", approver="console")
        except Exception as e:
            logger.error("Console approval error: %s", e)
            return ApprovalDecision(approved=False, reason=f"Approval error: {e}")

    async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        """Async wrapper — runs the sync prompt in an executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.request_approval_sync, request)


class CallbackBackend:
    """Wraps a legacy ``(function_name, arguments, risk_level) -> ApprovalDecision`` callback
    into an :class:`ApprovalProtocol`-compatible backend.

    Used internally by :func:`set_approval_callback` for backward compatibility.
    """

    def __init__(self, callback):
        self._callback = callback

    def request_approval_sync(self, request: ApprovalRequest) -> ApprovalDecision:
        result = self._callback(request.tool_name, request.arguments, request.risk_level)
        if isinstance(result, ApprovalDecision):
            return result
        # Legacy callbacks may return dict-like or bool
        if isinstance(result, bool):
            return ApprovalDecision(approved=result)
        return ApprovalDecision(approved=bool(result))

    async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        if asyncio.iscoroutinefunction(self._callback):
            result = await self._callback(request.tool_name, request.arguments, request.risk_level)
        else:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, self._callback, request.tool_name, request.arguments, request.risk_level,
            )
        if isinstance(result, ApprovalDecision):
            return result
        if isinstance(result, bool):
            return ApprovalDecision(approved=result)
        return ApprovalDecision(approved=bool(result))
