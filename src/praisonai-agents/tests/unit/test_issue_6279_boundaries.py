"""Regression tests for #6279: tools cache key, argument validation, approval TTY/timeout."""

import asyncio
import threading
from unittest.mock import MagicMock, patch

import pytest


# ── 1. tools cache keyed on content, not name ───────────────────────────────

def _make(kind):
    if kind == "a":
        def search(query: str):
            "Search the web"
    else:
        def search(sql: str, limit: int):
            "Query the database"
    return search


class TestToolsCacheKey:
    def test_same_name_callables_formatted_independently(self):
        from praisonaiagents.llm.llm import LLM

        llm = LLM(model="gpt-4o-mini")
        fa = llm._format_tools_for_litellm([_make("a")])
        fb = llm._format_tools_for_litellm([_make("b")])
        assert list(fa[0]["function"]["parameters"]["properties"]) == ["query"]
        assert list(fb[0]["function"]["parameters"]["properties"]) == ["sql", "limit"]

    def test_same_name_dict_tools_formatted_independently(self):
        from praisonaiagents.llm.llm import LLM

        def spec(desc):
            return {"type": "function", "function": {
                "name": "lookup", "description": desc,
                "parameters": {"type": "object", "properties": {}}}}

        llm = LLM(model="gpt-4o-mini")
        assert llm._format_tools_for_litellm([spec("v1")])[0]["function"]["description"] == "v1"
        assert llm._format_tools_for_litellm([spec("v2")])[0]["function"]["description"] == "v2"

    def test_same_tool_hits_cache(self):
        from praisonaiagents.llm.llm import LLM

        tool = _make("a")
        llm = LLM(model="gpt-4o-mini")
        first = llm._format_tools_for_litellm([tool])
        assert llm._format_tools_for_litellm([tool]) is first

    def test_cache_evicts_instead_of_freezing(self):
        from praisonaiagents.llm.llm import LLM

        llm = LLM(model="gpt-4o-mini")
        llm._max_cache_size = 3
        specs = [{"type": "function", "function": {
            "name": f"t{i}", "description": "d",
            "parameters": {"type": "object", "properties": {}}}} for i in range(5)]
        for s in specs:
            llm._format_tools_for_litellm([s])
        assert len(llm._formatted_tools_cache) == 3
        newest = llm._get_tools_cache_key([specs[-1]])
        assert newest in llm._formatted_tools_cache

    def test_agent_and_openai_client_keys_distinguish_same_name(self):
        from praisonaiagents import Agent
        from praisonaiagents.llm.openai_client import OpenAIClient

        a, b = _make("a"), _make("b")
        agent = Agent(name="x", instructions="hi", output="silent")
        assert agent._get_tools_cache_key([a]) != agent._get_tools_cache_key([b])
        key = OpenAIClient._get_tools_cache_key
        assert key(None, [a]) != key(None, [b])


# ── 2. tool-call argument validation ────────────────────────────────────────

@pytest.fixture
def agent_and_calls():
    from praisonaiagents import Agent

    calls = []

    def add(a: int, b: int = 1) -> int:
        "Add"
        calls.append((a, b))
        return a + b

    def lookup(name: str) -> str:
        "Lookup"
        calls.append(name)
        return "ok"

    ag = Agent(name="x", instructions="hi", tools=[add, lookup], output="silent")
    return ag, calls


class TestToolArgumentValidation:
    @pytest.mark.parametrize("fn,args", [
        ("add", {"a": "abc"}),
        ("lookup", {"name": {"k": 1}}),
        ("add", {}),
        ("add", {"a": 1, "zz": 2}),
    ])
    def test_invalid_args_returned_to_model_without_running(self, agent_and_calls, fn, args):
        ag, calls = agent_and_calls
        result = ag.execute_tool(fn, args)
        assert isinstance(result, dict)
        assert "Expected parameters" in result["error"]
        assert "expected_parameters" in result
        assert "_praison_retryable" not in result
        assert calls == []

    def test_coercible_args_still_run(self, agent_and_calls):
        ag, calls = agent_and_calls
        assert ag.execute_tool("add", {"a": "5"}) == 6
        assert calls == [(5, 1)]

    def test_async_path_validates(self, agent_and_calls):
        ag, calls = agent_and_calls
        result = asyncio.run(ag.execute_tool_async("add", {"a": "abc"}))
        assert isinstance(result, dict) and "expected_parameters" in result
        assert calls == []

    def test_raising_tool_still_ends_turn(self):
        from praisonaiagents import Agent
        from praisonaiagents.errors import ToolExecutionError

        def boom(x: int) -> int:
            "Boom"
            raise RuntimeError("kaput")

        ag = Agent(name="x", instructions="hi", tools=[boom], output="silent")
        with pytest.raises(ToolExecutionError):
            ag.execute_tool("boom", {"x": 1})


# ── 3. ConsoleBackend: no TTY / timeout ─────────────────────────────────────

def _request():
    from praisonaiagents.approval.protocols import ApprovalRequest
    return ApprovalRequest(tool_name="write_file", arguments={"path": "a"}, risk_level="high")


class TestConsoleBackendHeadless:
    def test_no_tty_denies_without_prompting(self):
        from praisonaiagents.approval.backends import ConsoleBackend

        with patch("praisonaiagents.approval.backends._get_rich_console"), \
             patch("praisonaiagents.approval.backends._get_rich_panel"), \
             patch("praisonaiagents.approval.backends._get_rich_prompt") as prompt, \
             patch("praisonaiagents.approval.backends._stdin_is_tty", return_value=False):
            decision = ConsoleBackend().request_approval_sync(_request())
        assert decision.approved is False
        assert decision.metadata.get("expired") is True
        prompt.return_value.ask.assert_not_called()

    def test_tty_prompt_expires_at_timeout(self):
        from praisonaiagents.approval.backends import ConsoleBackend

        release = threading.Event()
        prompt_cls = MagicMock()
        prompt_cls.ask.side_effect = lambda *a, **k: (release.wait(5), "o")[1]
        try:
            with patch("praisonaiagents.approval.backends._get_rich_console"), \
                 patch("praisonaiagents.approval.backends._get_rich_panel"), \
                 patch("praisonaiagents.approval.backends._get_rich_prompt", return_value=prompt_cls), \
                 patch("praisonaiagents.approval.backends._stdin_is_tty", return_value=True):
                decision = ConsoleBackend().request_approval_sync(_request(), timeout=0.2)
        finally:
            release.set()
        assert decision.approved is False
        assert decision.metadata.get("expired") is True

    def test_registry_passes_timeout_to_sync_backend(self):
        from praisonaiagents.approval.protocols import ApprovalDecision
        from praisonaiagents.approval.registry import ApprovalRegistry

        seen = {}

        class Backend:
            def request_approval_sync(self, request, timeout=None):
                seen["timeout"] = timeout
                return ApprovalDecision(approved=False, reason="no")

            async def request_approval(self, request):  # pragma: no cover
                return ApprovalDecision(approved=False, reason="no")

        reg = ApprovalRegistry()
        reg.set_backend(Backend())
        reg.approve_sync("x", "execute_command", {"command": "ls"}, force=True)
        assert seen["timeout"] == reg.timeout
