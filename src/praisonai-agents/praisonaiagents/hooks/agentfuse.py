"""Optional AgentFuse middleware for pre-dispatch tool decisions."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .middleware import ToolRequest, ToolResponse


class AgentFuseToolMiddleware:
    """Evaluate AgentFuse immediately before PraisonAI's tool handler chain."""

    _hook_type = "wrap_tool_call"

    def __init__(self, guard: Any) -> None:
        try:
            from dhms_agentfuse import RuntimeGuard, ToolCallRequest
        except ImportError as exc:
            raise ImportError(
                "AgentFuse middleware requires the 'agentfuse' optional dependency: "
                "pip install 'praisonaiagents[agentfuse]'"
            ) from exc

        if not isinstance(guard, RuntimeGuard):
            raise TypeError("guard must be a dhms_agentfuse.RuntimeGuard")

        self._guard = guard
        self._request_type = ToolCallRequest
        self._decisions: dict[str, Any] = {}

    def decision_for(self, tool_call_id: str) -> Any | None:
        """Return the completed policy decision for a tool call, if available."""
        return self._decisions.get(tool_call_id)

    def __call__(
        self,
        request: ToolRequest,
        call_next: Callable[[ToolRequest], ToolResponse],
    ) -> ToolResponse:
        context = request.context
        tool_call_id = (
            context.metadata.get("tool_call_id") if context is not None else None
        )
        if not tool_call_id:
            return ToolResponse(
                tool_name=request.tool_name,
                result={
                    "status": "blocked",
                    "policy_denied": True,
                    "tool_failure": False,
                    "reason_code": "missing_tool_call_id",
                    "host_execution": {
                        "outcome": "not_executed",
                        "handler_started": False,
                    },
                },
                context=context,
            )

        decision = self._guard.evaluate(
            self._request_type(
                tool_call_id=tool_call_id,
                tool_name=request.tool_name,
                arguments=request.arguments,
                safe_metadata={"integration": "praisonaiagents"},
            )
        )
        self._decisions[tool_call_id] = decision

        if decision.action == "block":
            return ToolResponse(
                tool_name=request.tool_name,
                result={
                    "status": "blocked",
                    "policy_denied": True,
                    "tool_failure": False,
                    "reason_code": decision.reason_code,
                    "agentfuse_decision": decision.to_safe_dict(),
                    "host_execution": {
                        "outcome": "not_executed",
                        "handler_started": False,
                    },
                },
                context=context,
            )

        return call_next(request)
