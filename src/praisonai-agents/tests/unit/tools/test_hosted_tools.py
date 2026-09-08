"""Provider-hosted tools work on any Agent, not only DeepResearchAgent.

PraisonAI already built every one of these spec dicts -- but only inside
agent/deep_research_agent.py, as constructor flags on that one class. And the
LLM layer dropped them: _format_tools_for_litellm accepted only
type == 'function', so a hosted tool was skipped with a debug log and the model
simply never had it.
"""
import pytest

from praisonaiagents.llm.llm import LLM
from praisonaiagents.tools.hosted import (
    HOSTED_TOOL_TYPES,
    CodeInterpreterTool,
    FileSearchTool,
    HostedMCPTool,
    WebSearchTool,
    is_hosted_tool,
)


def _llm():
    llm = LLM.__new__(LLM)
    llm._formatted_tools_cache = {}
    llm._max_cache_size = 16
    return llm


def a_function_tool():
    """A normal local tool."""


class TestSpecs:
    def test_web_search_matches_what_deep_research_sends(self):
        assert WebSearchTool() == {"type": "web_search_preview"}

    def test_file_search_carries_the_vector_stores(self):
        spec = FileSearchTool(vector_store_ids=["vs_1"])
        assert spec["type"] == "file_search"
        assert spec["vector_store_ids"] == ["vs_1"]

    def test_code_interpreter_declares_a_container(self):
        assert CodeInterpreterTool()["container"]["type"] == "auto"

    def test_hosted_mcp_requires_a_url(self):
        """The provider connects to it, so a missing url is unusable."""
        with pytest.raises(ValueError, match="server_url"):
            HostedMCPTool(server_url="")


class TestRecognition:
    @pytest.mark.parametrize("factory", [WebSearchTool, CodeInterpreterTool, FileSearchTool])
    def test_hosted_tools_are_recognised(self, factory):
        assert is_hosted_tool(factory()) is True

    def test_control_a_function_tool_is_not_hosted(self):
        assert is_hosted_tool({"type": "function", "function": {"name": "x"}}) is False

    def test_control_an_unknown_type_is_not_forwarded_blindly(self):
        """Allowlisted by type, so a malformed tool is still reported."""
        assert is_hosted_tool({"type": "not_a_real_tool"}) is False


class TestTheyReachTheModel:
    def test_hosted_tools_survive_formatting(self):
        out = _llm()._format_tools_for_litellm(
            [WebSearchTool(), FileSearchTool(vector_store_ids=["vs_1"])]
        ) or []
        assert [t["type"] for t in out] == ["web_search_preview", "file_search"]

    def test_control_a_local_function_tool_is_still_formatted(self):
        out = _llm()._format_tools_for_litellm([a_function_tool]) or []
        assert any(t.get("type") == "function" for t in out)

    def test_hosted_and_local_tools_coexist(self):
        out = _llm()._format_tools_for_litellm([WebSearchTool(), a_function_tool]) or []
        assert {t.get("type") for t in out} == {"web_search_preview", "function"}

    def test_control_an_unknown_dict_is_still_dropped(self):
        """The fix must not become "forward every dict"."""
        out = _llm()._format_tools_for_litellm([{"type": "not_a_real_tool"}]) or []
        assert out == []

    def test_hosted_tools_arriving_inside_a_list_also_survive(self):
        out = _llm()._format_tools_for_litellm([[WebSearchTool()]]) or []
        assert [t["type"] for t in out] == ["web_search_preview"]


class TestCacheKey:
    def test_tool_lists_differing_only_by_hosted_tools_do_not_share_a_key(self):
        llm = _llm()
        a = llm._get_tools_cache_key([WebSearchTool()])
        b = llm._get_tools_cache_key([FileSearchTool()])
        assert a != b
