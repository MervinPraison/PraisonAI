"""
Built-in approval backends for PraisonAI Agents.

Provides lightweight backends that ship with the core SDK:

- **AutoApproveBackend** — always approves (bots, trusted envs).
- **ConsoleBackend** — interactive Rich terminal prompt (CLI default).
- **AgentApproval** — delegates approval decision to another AI agent.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

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


class AgentApproval:
    """Delegates approval decisions to another AI agent.

    The approver agent receives a structured prompt describing the tool call
    and responds with ``APPROVE`` or ``DENY``.  This enables autonomous
    multi-agent approval workflows without human intervention.

    Lives in the core SDK because it only depends on the Agent class which
    is already in core — no external dependencies.

    Args:
        approver_agent: An Agent instance that will evaluate approval requests.
            If ``None``, a default approver agent is created with sensible
            instructions.
        llm: LLM model to use for the default approver agent (default ``gpt-4o-mini``).

    Example::

        from praisonaiagents import Agent
        from praisonaiagents.approval import AgentApproval

        approver = Agent(
            name="security-reviewer",
            instructions="Only approve low-risk read operations. Deny anything destructive.",
        )
        worker = Agent(
            name="worker",
            tools=[execute_command],
            approval=AgentApproval(approver_agent=approver),
        )
    """

    def __init__(
        self,
        approver_agent: Any = None,
        llm: str = "gpt-4o-mini",
    ):
        self._approver_agent = approver_agent
        self._llm = llm

    def __repr__(self) -> str:
        name = getattr(self._approver_agent, "name", None) or "default"
        return f"AgentApproval(approver={name!r})"

    def _get_approver(self) -> Any:
        """Lazily create or return the approver agent."""
        if self._approver_agent is not None:
            return self._approver_agent

        # Lazy import to avoid circular dependency at module level
        from praisonaiagents.agent.agent import Agent

        self._approver_agent = Agent(
            name="approval-reviewer",
            instructions=(
                "You are a security reviewer for tool execution requests. "
                "Evaluate each request and respond with exactly one word: "
                "APPROVE or DENY. Consider the tool name, arguments, and risk level. "
                "Deny anything that looks destructive, dangerous, or unauthorized. "
                "Approve safe read-only operations."
            ),
            llm=self._llm,
        )
        return self._approver_agent

    def _build_prompt(self, request: ApprovalRequest) -> str:
        """Build the evaluation prompt for the approver agent."""
        args_str = "\n".join(
            f"  {k}: {v}" for k, v in request.arguments.items()
        ) or "  (none)"

        return (
            f"Tool Approval Request:\n"
            f"  Tool: {request.tool_name}\n"
            f"  Risk Level: {request.risk_level.upper()}\n"
            f"  Agent: {request.agent_name or 'unknown'}\n"
            f"  Arguments:\n{args_str}\n\n"
            f"Respond with exactly one word: APPROVE or DENY"
        )

    async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        """Ask the approver agent to evaluate the request."""
        try:
            approver = self._get_approver()
            prompt = self._build_prompt(request)

            # Use the agent's chat method
            if hasattr(approver, "achat"):
                response = await approver.achat(prompt)
            elif hasattr(approver, "chat"):
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(None, approver.chat, prompt)
            else:
                return ApprovalDecision(
                    approved=False,
                    reason="Approver agent has no chat method",
                )

            response_text = str(response).strip().upper()
            approved = "APPROVE" in response_text and "DENY" not in response_text

            return ApprovalDecision(
                approved=approved,
                reason=f"Agent {'approved' if approved else 'denied'}: {str(response).strip()[:200]}",
                approver=getattr(approver, "name", "agent"),
                metadata={"platform": "agent", "response": str(response).strip()[:500]},
            )

        except Exception as e:
            logger.error(f"AgentApproval error: {e}")
            return ApprovalDecision(
                approved=False,
                reason=f"Agent approval error: {e}",
            )

    def request_approval_sync(self, request: ApprovalRequest) -> ApprovalDecision:
        """Synchronous wrapper."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, self.request_approval(request))
                return future.result(timeout=60)
        else:
            return asyncio.run(self.request_approval(request))


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
