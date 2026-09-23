"""Regression tests for issue #5149:

1. Default-path (OpenAI) chat_history rollback must remove only the failing
   turn's own messages, never a concurrent turn's (per-turn ownership tracking
   was only wired into the custom-LLM branch before this fix).
2. Per-tool guardrails run in the async tool path must be offloaded to a worker
   thread so a blocking user guardrail cannot stall the event loop.
3. Event hooks registered for one Agent (via HooksConfig(registry=...)) must not
   fire on an unrelated Agent that uses the shared default registry.
"""
import asyncio

from praisonaiagents.agent.memory_mixin import MemoryMixin


class _RollbackAgent(MemoryMixin):
    """Minimal host exercising the shared rollback/ownership helpers.

    Mirrors the real Agent's async-safe chat_history backing so the ownership
    helpers see the same list the lock guards.
    """

    def __init__(self):
        from praisonaiagents.agent.async_safety import AsyncSafeState
        self._state = AsyncSafeState([])

    @property
    def chat_history(self):
        return self._state.get()

    @property
    def _history_lock(self):
        return self._state


def test_default_path_rollback_preserves_concurrent_turn_messages():
    # Turn A opts into ownership tracking (what the fixed default path now does).
    agent = _RollbackAgent()
    token = agent._begin_turn_tracking()
    snapshot = len(agent.chat_history)  # 0
    agent._add_to_chat_history("user", "A-user")
    agent._add_to_chat_history("assistant", "A-assistant")

    # A concurrent turn B interleaves its own messages after A's snapshot by
    # appending directly (simulating another turn on another thread/context).
    agent.chat_history.append({"role": "user", "content": "B-user"})
    agent.chat_history.append({"role": "assistant", "content": "B-assistant"})

    # Turn A fails and rolls back to its snapshot. The old positional
    # ``del chat_history[snapshot:]`` would have erased B's messages too.
    agent._rollback_chat_history_to(snapshot)
    agent._end_turn_tracking(token)

    remaining = [m["content"] for m in agent.chat_history]
    assert "B-user" in remaining and "B-assistant" in remaining
    assert "A-user" not in remaining and "A-assistant" not in remaining


def test_async_tool_guardrail_offloaded_to_thread():
    # A blocking guardrail must run on a worker thread, not the event loop, so
    # verify _apply_tool_result_guardrails is invoked from a *different* thread
    # than the one running the coroutine.
    import threading
    from praisonaiagents.agent.execution_mixin import ExecutionMixin

    seen = {}

    class _Agent(ExecutionMixin):
        def __init__(self):
            self.name = "g"
            self.tools = []

        async def _check_tool_approval_async(self, function_name, arguments):
            return (None, arguments)

        def _check_tool_policy_and_guardrails(self, function_name, arguments, tools=None):
            seen["policy_thread"] = threading.current_thread().name
            return None, arguments

        def _resolve_mcp_tool_result(self, function_name, arguments):
            return True, "raw"

        def _normalize_mcp_result(self, result):
            return result

        def _apply_tool_result_guardrails(self, function_name, result, tools=None):
            seen["thread"] = threading.current_thread().name
            return result

    agent = _Agent()

    async def _run():
        seen["loop_thread"] = threading.current_thread().name
        # Reaches the result-guardrail gate via the MCP early-return branch.
        return await agent._execute_tool_async_impl("t", {})

    result = asyncio.run(_run())
    assert result == "raw"
    # Both the policy/guardrail check and the result guardrail must run on a
    # worker thread (asyncio.to_thread), never inline on the event loop.
    assert seen["policy_thread"] != seen["loop_thread"]
    assert seen["thread"] != seen["loop_thread"]


def test_async_terminal_turn_unregisters_live_owner():
    # Greptile finding: a terminal async turn (last achat/arun/astart in its
    # context) began ownership tracking but never ended it, so its completed
    # ownership list lingered in the process-wide live-turn registry and a later
    # ephemeral() cleanup treated its committed messages as still live. The
    # async default path now ends tracking in a finally (via _clear_turn_tracking).
    from praisonaiagents.agent import memory_mixin

    agent = _RollbackAgent()

    # Simulate a completed async turn: begin tracking, append, then end via the
    # same helper the fixed _achat_impl finally now calls.
    agent._begin_turn_tracking()
    agent._add_to_chat_history("user", "committed-user")
    agent._add_to_chat_history("assistant", "committed-assistant")

    # While the turn is live, its messages are exposed to concurrent ephemeral()
    # cleanup via the live-turn registry.
    assert len(memory_mixin._live_turn_message_ids()) == 2

    # Terminal turn finishing must drop its ownership from the global registry.
    agent._clear_turn_tracking()
    assert memory_mixin._live_turn_message_ids() == set()

    # Committed messages remain in history (only the *registry* entry is cleared).
    contents = [m["content"] for m in agent.chat_history]
    assert "committed-user" in contents and "committed-assistant" in contents


def test_hooks_config_registry_isolates_event_hooks():
    from praisonaiagents.hooks import HookRegistry, get_default_registry
    from praisonaiagents.config import HooksConfig
    from praisonaiagents import Agent

    private = HookRegistry()
    a = Agent(name="a", instructions="x", hooks=HooksConfig(registry=private))
    b = Agent(name="b", instructions="y")  # uses the shared default registry

    assert a._hook_runner.registry is private
    assert b._hook_runner.registry is get_default_registry()
    assert a._hook_runner.registry is not b._hook_runner.registry
