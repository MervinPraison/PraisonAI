"""Tests for MCP resource and prompt surfacing.

Verifies that servers advertising resources/prompts gain synthetic,
agent-callable tools (`list_mcp_resources`, `read_mcp_resource`, etc.) while
tools-only servers behave exactly as before.
"""

import pytest
from types import SimpleNamespace
from unittest.mock import patch

from praisonaiagents.mcp.mcp import MCP
from praisonaiagents.mcp import resources as res


def _make_mcp(resources=None, resource_templates=None, prompts=None, tools=None):
    """Build an MCP instance with a stubbed runner (no real subprocess)."""
    with patch.object(MCP, "__init__", lambda self: None):
        mcp = MCP.__new__(MCP)
        mcp._tool_prefix = None
        mcp.allowed_tools = None
        mcp.disabled_tools = None
        mcp.is_sse = False
        mcp.is_http_stream = False
        mcp.runner = SimpleNamespace(
            tools=tools or [],
            resources=resources or [],
            resource_templates=resource_templates or [],
            prompts=prompts or [],
            read_resource=lambda uri: f"read:{uri}",
            get_prompt=lambda name, args: f"prompt:{name}:{args}",
        )
        mcp._tools = mcp._apply_tool_filters(mcp._generate_tool_functions())
        return mcp


class TestNormalisation:
    def test_normalize_text_resource(self):
        result = SimpleNamespace(
            contents=[SimpleNamespace(text="hello world", blob=None)]
        )
        assert res.normalize_resource_result(result) == "hello world"

    def test_normalize_binary_resource(self):
        import base64
        blob = base64.b64encode(b"1234567890").decode()
        result = SimpleNamespace(
            contents=[SimpleNamespace(text=None, blob=blob, mimeType="image/png")]
        )
        out = res.normalize_resource_result(result)
        assert "binary resource" in out
        assert "image/png" in out

    def test_normalize_truncates_large_text(self):
        big = "x" * (res.MAX_INLINE_BYTES + 100)
        result = SimpleNamespace(contents=[SimpleNamespace(text=big, blob=None)])
        out = res.normalize_resource_result(result)
        assert "truncated" in out

    def test_normalize_prompt(self):
        result = SimpleNamespace(
            description="A prompt",
            messages=[
                SimpleNamespace(role="user", content=SimpleNamespace(text="hi"))
            ],
        )
        out = res.normalize_prompt_result(result)
        assert "A prompt" in out
        assert "user: hi" in out

    def test_prompts_to_dicts_argument_hints(self):
        prompt = SimpleNamespace(
            name="greet",
            description="Greet someone",
            arguments=[SimpleNamespace(name="who", description="target", required=True)],
        )
        dicts = res.prompts_to_dicts([prompt])
        assert dicts[0]["name"] == "greet"
        assert dicts[0]["arguments"][0]["name"] == "who"
        assert dicts[0]["arguments"][0]["required"] is True


class TestSyntheticTools:
    def test_tools_only_server_has_no_synthetic_tools(self):
        mcp = _make_mcp()
        names = [t.__name__ for t in mcp.get_tools()]
        assert "list_mcp_resources" not in names
        assert "read_mcp_resource" not in names
        assert "list_mcp_prompts" not in names

    def test_resource_server_registers_resource_tools(self):
        resource = SimpleNamespace(
            uri="docs://readme", name="readme", description="d", mimeType="text/plain"
        )
        mcp = _make_mcp(resources=[resource])
        names = [t.__name__ for t in mcp.get_tools()]
        assert "list_mcp_resources" in names
        assert "list_mcp_resource_templates" in names
        assert "read_mcp_resource" in names
        assert "list_mcp_prompts" not in names

    def test_prompt_server_registers_prompt_tools(self):
        prompt = SimpleNamespace(name="p", description="d", arguments=[])
        mcp = _make_mcp(prompts=[prompt])
        names = [t.__name__ for t in mcp.get_tools()]
        assert "list_mcp_prompts" in names
        assert "get_mcp_prompt" in names
        assert "read_mcp_resource" not in names

    def test_read_mcp_resource_tool_calls_runner(self):
        resource = SimpleNamespace(
            uri="docs://readme", name="readme", description="d", mimeType="text/plain"
        )
        mcp = _make_mcp(resources=[resource])
        read_tool = next(t for t in mcp.get_tools() if t.__name__ == "read_mcp_resource")
        assert read_tool("docs://readme") == "read:docs://readme"

    def test_list_mcp_resources_tool_returns_json(self):
        resource = SimpleNamespace(
            uri="docs://readme", name="readme", description="d", mimeType="text/plain"
        )
        mcp = _make_mcp(resources=[resource])
        list_tool = next(t for t in mcp.get_tools() if t.__name__ == "list_mcp_resources")
        out = list_tool()
        assert "docs://readme" in out

    def test_get_resources_introspection(self):
        resource = SimpleNamespace(
            uri="docs://readme", name="readme", description="d", mimeType="text/plain"
        )
        mcp = _make_mcp(resources=[resource])
        listed = mcp.get_resources()
        assert listed[0]["uri"] == "docs://readme"

    def test_get_prompts_introspection(self):
        prompt = SimpleNamespace(name="p", description="d", arguments=[])
        mcp = _make_mcp(prompts=[prompt])
        assert mcp.get_prompts()[0]["name"] == "p"


class TestOpenAISchema:
    def test_resource_only_server_exposes_openai_tools(self):
        resource = SimpleNamespace(
            uri="docs://readme", name="readme", description="d", mimeType="text/plain"
        )
        mcp = _make_mcp(resources=[resource])
        schemas = mcp.to_openai_tool()
        assert schemas is not None
        names = [s["function"]["name"] for s in schemas]
        assert "read_mcp_resource" in names

    def test_prefix_applies_to_synthetic_tools(self):
        resource = SimpleNamespace(
            uri="docs://readme", name="readme", description="d", mimeType="text/plain"
        )
        mcp = _make_mcp(resources=[resource])
        mcp.with_tool_prefix("docs")
        names = [t.__name__ for t in mcp.get_tools()]
        assert "docs_read_mcp_resource" in names
        schemas = mcp.to_openai_tool()
        schema_names = [s["function"]["name"] for s in schemas]
        assert "docs_read_mcp_resource" in schema_names


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
