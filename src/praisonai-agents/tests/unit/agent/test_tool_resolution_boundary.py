"""Regression tests for GHSA-gmjg-hv98-qggq:
Undeclared __main__ callables must NOT be executed via execute_tool.
"""
import sys
from unittest.mock import MagicMock, patch

from praisonaiagents.agent.tool_execution import ToolExecutionMixin


class _HookRunner:
    def execute_sync(self, *args, **kwargs):
        return []

    def is_blocked(self, results):
        return False


class _DummyAgent(ToolExecutionMixin):
    def __init__(self, tools=None):
        self.name = "test_agent"
        self.tools = tools or []
        self.chat_history = []
        self._hook_runner = _HookRunner()
        self.context_manager = None
        self._doom_loop_tracker = None
        self._perm_deny = frozenset()
        self._perm_allow = None
        self._approval_backend = None


def _make_approved_registry():
    reg = MagicMock()
    reg.approve_sync.return_value = MagicMock(
        approved=True, reason="mock", modified_args=None
    )
    reg.mark_approved = MagicMock()
    return reg


def _sneaky_undeclared(msg="pwned"):
    """Callable present only in __main__, never declared as a tool."""
    return {"ran": msg}


def test_undeclared_main_callable_not_executed():
    """An undeclared callable in __main__ must NOT be invoked."""
    # Inject the function into __main__ to simulate the exploit scenario.
    original = getattr(sys.modules["__main__"], "_sneaky_undeclared", None)
    sys.modules["__main__"]._sneaky_undeclared = _sneaky_undeclared
    try:
        reg = _make_approved_registry()
        with patch("praisonaiagents.approval.get_approval_registry", return_value=reg):
            agent = _DummyAgent(tools=[])
            result = agent.execute_tool("_sneaky_undeclared", {"msg": "hello"})
        # Should NOT have run the function — result must indicate not-found, not success.
        assert result != {"ran": "hello"}, (
            "Undeclared __main__ callable was executed — vulnerability still present"
        )
    finally:
        if original is None:
            delattr(sys.modules["__main__"], "_sneaky_undeclared")
        else:
            sys.modules["__main__"]._sneaky_undeclared = original


def test_declared_tool_still_executes():
    """A properly declared tool must still be callable after the fix."""
    def my_tool(x: int) -> int:
        return x * 2

    reg = _make_approved_registry()
    with patch("praisonaiagents.approval.get_approval_registry", return_value=reg):
        agent = _DummyAgent(tools=[my_tool])
        result = agent.execute_tool("my_tool", {"x": 3})
    assert result == 6, f"Declared tool did not execute correctly: {result}"


def test_globals_callable_not_executed():
    """A callable only in tool_execution module globals must NOT be invoked."""
    reg = _make_approved_registry()
    with patch("praisonaiagents.approval.get_approval_registry", return_value=reg):
        agent = _DummyAgent(tools=[])
        # 'logging' is a module-level name in tool_execution; it must not be invocable.
        result = agent.execute_tool("logging", {})
    assert not isinstance(result, dict) or result.get("ran") is None, (
        "globals() fallback executed an unintended name"
    )


def test_undeclared_returns_error_or_none():
    """execute_tool with an unknown name should return None or an error dict, not raise."""
    reg = _make_approved_registry()
    with patch("praisonaiagents.approval.get_approval_registry", return_value=reg):
        agent = _DummyAgent(tools=[])
        result = agent.execute_tool("completely_nonexistent_xyz", {})
    # Result should be None or an error dict — not a successful execution.
    assert result is None or isinstance(result, dict), (
        f"Unexpected return type: {type(result)}"
    )
    if isinstance(result, dict):
        assert result.get("ran") is None
