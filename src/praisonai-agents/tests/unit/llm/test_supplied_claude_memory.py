"""A supplied claude_memory object must not require the default implementation (issue #5895)."""

from praisonaiagents.llm.llm import LLM


class _Adapter:
    def get_tool_definition(self):
        return {"type": "memory_20250818", "name": "memory"}

    def get_beta_header(self):
        return "context-management-2025-06-27"

    def execute(self, *args, **kwargs):
        return "ok"


def _llm(claude_memory):
    return LLM(
        model="anthropic/claude-sonnet-4-20250514",
        api_key="test-key",
        claude_memory=claude_memory,
    )


def test_supplied_adapter_is_used_and_cached():
    adapter = _Adapter()
    llm = _llm(adapter)
    assert llm._get_claude_memory_tool() is adapter
    assert llm._get_claude_memory_tool() is adapter


def test_supplied_adapter_reaches_completion_params():
    llm = _llm(_Adapter())
    params = llm._build_completion_params(messages=[{"role": "user", "content": "Hello"}])
    assert {"type": "memory_20250818", "name": "memory"} in params["tools"]
    assert params["extra_headers"]["anthropic-beta"] == "context-management-2025-06-27"


def test_disabled_returns_none():
    assert _llm(None)._get_claude_memory_tool() is None
    assert _llm(False)._get_claude_memory_tool() is None
