"""Tests for HostedMCPTool extended fields and provider serialization (C-6)."""

import json

import pytest

from praisonaiagents.llm.llm import LLM
from praisonaiagents.llm.openai_client import OpenAIClient
from praisonaiagents.tools.hosted import (
    HostedMCPTool,
    WebSearchTool,
    is_hosted_tool,
)
from praisonaiagents.tools.schema import tools_cache_key


def _make_llm(model: str = "gpt-4o") -> LLM:
    llm = LLM.__new__(LLM)
    llm.model = model
    llm._formatted_tools_cache = {}
    llm._max_cache_size = 16
    llm.base_url = None
    llm.api_key = None
    llm.api_version = None
    llm.timeout = None
    llm.max_tokens = None
    llm.temperature = None
    llm.top_p = None
    llm.presence_penalty = None
    llm.frequency_penalty = None
    llm.logit_bias = None
    llm.response_format = None
    llm.seed = None
    llm.logprobs = None
    llm.top_logprobs = None
    llm.stop_phrases = None
    llm.extra_settings = None
    llm.reasoning_effort = None
    llm.web_search = False
    llm.web_fetch = False
    llm._auth_provider = None
    llm._provider_adapter = None
    llm._resolve_openai_compatible_model = lambda: model
    llm._resolve_subscription_creds = lambda: None
    llm._supports_claude_memory = lambda: False
    llm._supports_web_search = lambda: False
    llm._supports_web_fetch = lambda: False
    llm._is_gemini_model = lambda _m=None: False
    llm._apply_nvidia_nim_credentials = lambda _p: None
    llm._crosses_nim_boundary = lambda _a, _b: False
    llm._guard_format_with_tools = lambda _p: None
    return llm


def _make_openai_client() -> OpenAIClient:
    client = OpenAIClient.__new__(OpenAIClient)
    client._formatted_tools_cache = {}
    client._max_cache_size = 16
    client.base_url = None
    return client


def _sample_fn(query: str) -> str:
    """Search locally."""
    return query


class TestBackwardCompatibility:
    def test_defaults_match_existing_openai_spec(self):
        tool = HostedMCPTool(server_url="https://example.com/mcp")
        assert isinstance(tool, dict)
        assert is_hosted_tool(tool) is True
        assert tool == {
            "type": "mcp",
            "server_label": "mcp_server",
            "server_url": "https://example.com/mcp",
            "require_approval": "never",
        }
        assert "authorization" not in tool
        assert "allowed_tools" not in tool
        assert "defer_loading" not in tool
        assert tool.to_openai_dict() == tool

    def test_defaults_match_minimal_anthropic_payload(self):
        tool = HostedMCPTool(server_url="https://example.com/mcp")
        anth = tool.to_anthropic_dict()
        assert anth == {
            "mcp_server": {
                "type": "url",
                "url": "https://example.com/mcp",
                "name": "mcp_server",
            },
            "mcp_toolset": {
                "type": "mcp_toolset",
                "mcp_server_name": "mcp_server",
            },
        }
        assert "authorization_token" not in anth["mcp_server"]
        assert "default_config" not in anth["mcp_toolset"]
        assert "configs" not in anth["mcp_toolset"]

    def test_anthropic_completion_params_unchanged_without_hosted_mcp(self):
        llm = _make_llm("anthropic/claude-sonnet-4-5")
        formatted = llm._format_tools_for_litellm([_sample_fn])
        params = llm._build_completion_params(
            messages=[{"role": "user", "content": "hi"}],
            tools=formatted,
        )
        assert "mcp_servers" not in params
        assert "extra_headers" not in params
        assert all(t.get("type") == "function" for t in params["tools"])


class TestOpenAIResponsesSerialization:
    def test_all_fields_serialized_for_openai_responses(self):
        allowed = ["search_docs", "get_page"]
        approval = {"never": {"tool_names": ["search_docs"]}}
        tool = HostedMCPTool(
            server_url="https://mcp.example.com/mcp",
            server_label="docs",
            authorization="oauth-secret-token-999",
            allowed_tools=allowed,
            require_approval=approval,
            defer_loading=True,
        )
        # Mutating caller's list must not mutate the tool spec.
        allowed.append("mutated")

        expected = {
            "type": "mcp",
            "server_label": "docs",
            "server_url": "https://mcp.example.com/mcp",
            "require_approval": {"never": {"tool_names": ["search_docs"]}},
            "authorization": "oauth-secret-token-999",
            "allowed_tools": ["search_docs", "get_page"],
            "defer_loading": True,
        }
        assert tool == expected
        assert tool.to_openai_dict() == expected

        # OpenAIClient path
        client = _make_openai_client()
        formatted = client.format_tools([tool])
        resp_params = client._build_responses_input(
            messages=[{"role": "user", "content": "hello"}],
            model="gpt-4o",
            tools=formatted,
        )
        assert resp_params["tools"] == [expected]

        # LLM Responses path
        llm = _make_llm("gpt-4o")
        llm_formatted = llm._format_tools_for_litellm([tool])
        llm_resp = llm._build_responses_params(
            messages=[{"role": "user", "content": "hello"}],
            tools=llm_formatted,
        )
        assert llm_resp["tools"] == [expected]

    def test_require_approval_none_omitted_and_always_preserved(self):
        t_none = HostedMCPTool(server_url="https://example.com/mcp", require_approval=None)
        assert "require_approval" not in t_none
        assert "require_approval" not in t_none.to_openai_dict()

        t_always = HostedMCPTool(server_url="https://example.com/mcp", require_approval="always")
        assert t_always["require_approval"] == "always"

    def test_defer_loading_false_and_empty_allowed_tools_preserved(self):
        tool = HostedMCPTool(
            server_url="https://example.com/mcp",
            allowed_tools=[],
            defer_loading=False,
        )
        assert tool["allowed_tools"] == []
        assert tool["defer_loading"] is False

    def test_raw_mcp_dict_strips_none_optional_fields_on_responses_path(self):
        client = _make_openai_client()
        raw = {
            "type": "mcp",
            "server_label": "raw",
            "server_url": "https://example.com/mcp",
            "authorization": None,
            "allowed_tools": None,
            "require_approval": None,
            "defer_loading": None,
        }
        resp = client._build_responses_input(
            messages=[{"role": "user", "content": "hi"}],
            model="gpt-4o",
            tools=[raw],
        )
        assert resp["tools"] == [
            {"type": "mcp", "server_label": "raw", "server_url": "https://example.com/mcp"}
        ]


class TestAnthropicSerialization:
    def test_all_fields_mapped_to_mcp_servers_and_mcp_toolset(self):
        tool = HostedMCPTool(
            server_url="https://mcp.example.com/mcp",
            server_label="cal",
            authorization="Bearer anth-secret-42",
            allowed_tools=["list_events", "get_event"],
            require_approval="always",
            defer_loading=True,
        )
        anth = tool.to_anthropic_dict()
        assert anth["mcp_server"] == {
            "type": "url",
            "url": "https://mcp.example.com/mcp",
            "name": "cal",
            "authorization_token": "anth-secret-42",
        }
        assert anth["mcp_toolset"] == {
            "type": "mcp_toolset",
            "mcp_server_name": "cal",
            "default_config": {"enabled": False, "defer_loading": True},
            "configs": {
                "list_events": {"enabled": True},
                "get_event": {"enabled": True},
            },
        }
        assert "require_approval" not in anth["mcp_server"]
        assert "require_approval" not in anth["mcp_toolset"]

    def test_defer_loading_only_and_empty_allowed_tools(self):
        t_defer = HostedMCPTool(
            server_url="https://mcp.example.com/mcp",
            server_label="docs",
            defer_loading=True,
        )
        assert t_defer.to_anthropic_dict()["mcp_toolset"] == {
            "type": "mcp_toolset",
            "mcp_server_name": "docs",
            "default_config": {"defer_loading": True},
        }

        t_empty = HostedMCPTool(
            server_url="https://mcp.example.com/mcp",
            server_label="locked",
            allowed_tools=[],
        )
        assert t_empty.to_anthropic_dict()["mcp_toolset"] == {
            "type": "mcp_toolset",
            "mcp_server_name": "locked",
            "default_config": {"enabled": False},
        }

    def test_llm_build_completion_params_maps_hosted_mcp_for_anthropic(self):
        llm = _make_llm("anthropic/claude-sonnet-4-5")
        mcp_tool = HostedMCPTool(
            server_url="https://mcp.example.com/mcp",
            server_label="cal",
            authorization="secret-anth-tok",
            allowed_tools=["list_events"],
            defer_loading=True,
        )
        formatted = llm._format_tools_for_litellm([mcp_tool, _sample_fn])
        params = llm._build_completion_params(
            messages=[{"role": "user", "content": "schedule?"}],
            tools=formatted,
            extra_headers={"anthropic-beta": "existing-beta-2025"},
        )
        assert params["mcp_servers"] == [
            {
                "type": "url",
                "url": "https://mcp.example.com/mcp",
                "name": "cal",
                "authorization_token": "secret-anth-tok",
            }
        ]
        assert params["tools"][0] == {
            "type": "mcp_toolset",
            "mcp_server_name": "cal",
            "default_config": {"enabled": False, "defer_loading": True},
            "configs": {"list_events": {"enabled": True}},
        }
        assert params["tools"][1]["type"] == "function"
        beta_parts = [
            b.strip() for b in params["extra_headers"]["anthropic-beta"].split(",")
        ]
        assert "existing-beta-2025" in beta_parts
        assert "mcp-client-2025-11-20" in beta_parts

    def test_non_anthropic_completion_params_do_not_split_mcp_tool(self):
        llm = _make_llm("xai/grok-4")
        mcp_tool = HostedMCPTool(
            server_url="https://mcp.example.com/mcp",
            server_label="docs",
            allowed_tools=["ask"],
        )
        formatted = llm._format_tools_for_litellm([mcp_tool, WebSearchTool()])
        params = llm._build_completion_params(
            messages=[{"role": "user", "content": "hi"}],
            tools=formatted,
        )
        assert "mcp_servers" not in params
        assert params["tools"][0]["type"] == "mcp"


class TestSecretRedaction:
    def test_authorization_never_leaked_in_repr_str_or_cache_key(self):
        secret = "oauth_super_secret_value_XYZ123"
        tool = HostedMCPTool(
            server_url="https://mcp.example.com/mcp",
            server_label="private",
            authorization=secret,
        )
        assert secret not in repr(tool)
        assert secret not in str(tool)
        assert secret not in repr(tool.copy())
        assert secret not in repr(tool.to_openai_dict())
        assert secret not in repr(tool.to_anthropic_dict())
        assert secret not in tools_cache_key([tool])

        # Wire JSON serialization must still transmit the real token.
        wire = json.loads(json.dumps(tool))
        assert wire["authorization"] == secret
        anth_wire = json.loads(json.dumps(tool.to_anthropic_dict()))
        assert anth_wire["mcp_server"]["authorization_token"] == secret

        # Provider params repr must also never leak the secret.
        client = _make_openai_client()
        resp = client._build_responses_input(
            messages=[{"role": "user", "content": "hi"}],
            model="gpt-4o",
            tools=[tool],
        )
        assert secret not in repr(resp)

        llm = _make_llm("anthropic/claude-sonnet-4-5")
        anth_params = llm._build_completion_params(
            messages=[{"role": "user", "content": "hi"}],
            tools=[tool],
        )
        assert secret not in repr(anth_params)

    def test_distinct_authorization_tokens_have_distinct_cache_keys(self):
        t1 = HostedMCPTool(server_url="https://mcp.example.com/mcp", authorization="tok-1")
        t2 = HostedMCPTool(server_url="https://mcp.example.com/mcp", authorization="tok-2")
        assert tools_cache_key([t1]) != tools_cache_key([t2])
