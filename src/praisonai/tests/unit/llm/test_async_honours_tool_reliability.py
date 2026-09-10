"""`max_tool_repairs` and `force_tool_usage` were accepted and ignored on async.

Both are user-settable and both are set automatically by `OllamaAdapter` for
every Ollama LLM. Both were consulted only inside `get_response`, so an agent
that awaited instead of called silently got neither -- with no warning that a
setting it had accepted was doing nothing.
"""

import asyncio

import pytest

from praisonaiagents.llm.llm import LLM


def get_weather(city: str) -> str:
    """Get the weather for a city.

    Args:
        city: the city
    """
    return f"{city}: 21C sunny"


class M(dict):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.__dict__.update(kw)


def _resp(content, tool_calls=None):
    return M(choices=[M(message=M(content=content, tool_calls=tool_calls),
                        finish_reason="stop")])


@pytest.fixture
def llm(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    return LLM(model="ollama/qwen3:0.6b", base_url="http://127.0.0.1:11434")


class TestSharedHelpers:
    """The policy itself, independent of which path calls it."""

    def test_force_returns_a_nudge_when_tools_were_ignored(self, llm):
        msg = llm._force_tool_usage_message(
            "I cannot help with that.", None,
            [{"type": "function", "function": {"name": "get_weather"}}], 0)
        assert msg and "get_weather" in msg

    def test_force_returns_nothing_when_a_tool_was_called(self, llm):
        assert llm._force_tool_usage_message(
            "", [{"function": {"name": "get_weather"}}],
            [{"type": "function", "function": {"name": "get_weather"}}], 0) is None

    def test_repair_returns_nothing_when_the_budget_is_spent(self, llm):
        llm.max_tool_repairs = 0
        assert llm._tool_repair_message(
            [{"function": {"name": "nope", "arguments": "{}"}}],
            [{"type": "function", "function": {"name": "get_weather"}}]) is None

    def test_repair_charges_the_budget_once_per_attempt(self, llm):
        llm.max_tool_repairs = 2
        llm._current_repair_count = 0
        bad = [{"function": {"name": "not_a_tool", "arguments": "{}"}}]
        tools = [{"type": "function", "function": {
            "name": "get_weather",
            "parameters": {"type": "object", "properties": {"city": {"type": "string"}}}}}]
        if llm._tool_repair_message(bad, tools):
            assert llm._current_repair_count == 1


class TestAsyncAppliesThePolicy:
    def test_async_forces_tool_usage_when_the_model_ignores_tools(self, llm):
        """THE regression: async never sent the nudge."""
        seen = []

        async def fake(**kwargs):
            seen.append([m.get("content", "") for m in kwargs.get("messages", [])])
            # Ignore the tools on turn one; answer once nudged.
            if any("You MUST use" in str(c) or "use the available tools" in str(c).lower()
                   for c in seen[-1]):
                return _resp("Paris is sunny.")
            return _resp("I don't think I need a tool.")

        llm._acompletion_with_retry = fake
        asyncio.run(llm.get_response_async(
            prompt="weather in Paris?", tools=[get_weather],
            execute_tool_fn=lambda n, a, *x, **k: get_weather(**a),
            temperature=0, verbose=False, stream=False))

        joined = " ".join(c for turn in seen for c in map(str, turn))
        assert "get_weather" in joined, (
            "async never sent the force-tool-usage nudge; "
            f"messages seen: {seen!r}"
        )
        assert len(seen) > 1, "async gave up after one turn instead of nudging"


class TestAsyncPolicyIsNotStreamingScoped:
    def test_reliability_policy_runs_after_the_stream_branch_converges(self):
        """The policy must sit at the same indent as `if use_streaming`, i.e. it
        runs after BOTH the streaming and non-streaming branches -- not nested
        inside the non-streaming `else`. Placed inside that branch, a
        streaming-with-tools provider that sets a repair budget (e.g.
        LocalOpenAIAdapter) silently skipped the policy the sync path applies."""
        import inspect
        import textwrap
        import praisonaiagents.llm.llm as mod

        src = textwrap.dedent(inspect.getsource(mod.LLM.get_response_async))
        lines = src.split("\n")

        def indent_of(needle):
            for line in lines:
                if needle in line and not line.lstrip().startswith("#"):
                    return len(line) - len(line.lstrip())
            return None

        branch_indent = indent_of("if use_streaming:")
        force_indent = indent_of("_force = self._force_tool_usage_message(")
        repair_indent = indent_of("_repair = self._tool_repair_message(")
        assert branch_indent is not None
        assert force_indent == branch_indent, (
            "force-tool policy is nested inside a response branch; a streaming "
            "provider will skip it")
        assert repair_indent == branch_indent, (
            "repair policy is nested inside a response branch; a streaming "
            "provider will skip it")


class TestSyncIsUnchanged:
    def test_sync_still_uses_the_same_policy(self, llm):
        """The helpers must not have altered sync behaviour."""
        assert llm._force_tool_usage_message(
            "no tool for me", None,
            [{"type": "function", "function": {"name": "get_weather"}}], 0) is not None
