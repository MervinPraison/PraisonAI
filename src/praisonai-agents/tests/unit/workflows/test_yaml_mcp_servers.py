"""Unit tests for top-level ``mcp_servers:`` (and ``mcp:`` alias) in workflow YAML."""

from __future__ import annotations

import praisonaiagents.mcp as mcp_pkg


def _fake_mcp_factory(calls):
    def fake_mcp(target, args=None, **opts):
        calls.append((target, args, opts))

        def fake_tool(query: str) -> str:
            """Fake MCP tool."""
            return query

        fake_tool.prefix = None

        def with_tool_prefix(prefix):
            fake_tool.prefix = prefix
            return fake_tool

        fake_tool.with_tool_prefix = with_tool_prefix
        return fake_tool

    return fake_mcp


class TestYamlMcpServers:
    def test_top_level_mcp_servers_shared_and_prefixed_when_multiple(self, monkeypatch):
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser

        calls = []
        monkeypatch.setattr(mcp_pkg, "MCP", _fake_mcp_factory(calls))

        yaml_text = """
name: MCP Workflow
mcp_servers:
  github:
    url: https://api.github.com/mcp
    headers:
      Authorization: Bearer tok
  fs:
    command: npx
    args: ["-y", "server-fs", "/my docs"]
  unused:
    command: npx
    args: ["-y", "unused"]

agents:
  researcher:
    instructions: Research
    tools: [github, fs]
  reviewer:
    instructions: Review
    tools: [github]

steps:
  - agent: researcher
    action: Gather context
  - agent: reviewer
    action: Review findings
"""
        wf = YAMLWorkflowParser().parse_string(yaml_text)
        researcher, reviewer = wf.steps[0], wf.steps[1]

        # Only referenced servers started; github opened once and shared.
        assert [c[0] for c in calls] == ["https://api.github.com/mcp", "npx"]
        assert calls[0][2]["headers"] == {"Authorization": "Bearer tok"}
        assert calls[1][1] == ["-y", "server-fs", "/my docs"]

        # Shared client instance across agents, prefixed because >1 server configured.
        gh_from_researcher = researcher.tools[0]
        fs_from_researcher = researcher.tools[1]
        gh_from_reviewer = reviewer.tools[0]
        assert gh_from_researcher is gh_from_reviewer
        assert gh_from_researcher.prefix == "github"
        assert fs_from_researcher.prefix == "fs"

    def test_mcp_alias_direct_and_nested_servers(self, monkeypatch):
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser

        calls = []
        monkeypatch.setattr(mcp_pkg, "MCP", _fake_mcp_factory(calls))

        direct_yaml = """
name: Direct Alias
mcp:
  github:
    url: https://api.github.com/mcp
agents:
  a:
    instructions: Hi
    tools: [github]
steps:
  - agent: a
    action: Go
"""
        wf1 = YAMLWorkflowParser().parse_string(direct_yaml)
        assert len(calls) == 1
        assert calls[0][0] == "https://api.github.com/mcp"
        # Single server keeps bare names (not prefixed).
        assert wf1.steps[0].tools[0].prefix is None

        nested_yaml = """
name: Nested Alias
mcp:
  servers:
    docs:
      url: https://docs.example/mcp
agents:
  a:
    instructions: Hi
    tools: [docs]
steps:
  - agent: a
    action: Go
"""
        wf2 = YAMLWorkflowParser().parse_string(nested_yaml)
        assert len(calls) == 2
        assert calls[1][0] == "https://docs.example/mcp"
        assert len(wf2.steps[0].tools) == 1

    def test_agents_yaml_roles_format_supports_mcp_servers(self, monkeypatch):
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser

        calls = []
        monkeypatch.setattr(mcp_pkg, "MCP", _fake_mcp_factory(calls))

        yaml_text = """
framework: praisonai
topic: Audit
mcp_servers:
  linear:
    url: https://mcp.linear.app/mcp
roles:
  triager:
    role: Triager
    goal: Triage bugs
    backstory: Careful triager
    tools: [linear]
    tasks:
      triage:
        description: Check open issues
"""
        wf = YAMLWorkflowParser().parse_string(yaml_text)
        assert len(calls) == 1
        assert calls[0][0] == "https://mcp.linear.app/mcp"
        assert len(wf.steps[0].tools) == 1

    def test_editor_field_aliases_supported(self, monkeypatch):
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser

        calls = []
        monkeypatch.setattr(mcp_pkg, "MCP", _fake_mcp_factory(calls))

        yaml_text = """
name: Aliases
mcp_servers:
  notion:
    httpUrl: https://mcp.notion.com/mcp
    http_headers:
      X-Team: core
    includeTools: [search]
    excludeTools: [delete]
agents:
  a:
    instructions: Hi
    tools: [notion]
steps:
  - agent: a
    action: Go
"""
        YAMLWorkflowParser().parse_string(yaml_text)
        assert calls == [(
            "https://mcp.notion.com/mcp",
            None,
            {
                "headers": {"X-Team": "core"},
                "allowed_tools": ["search"],
                "disabled_tools": ["delete"],
            },
        )]

    def test_disabled_servers_are_skipped(self, monkeypatch):
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser

        calls = []
        monkeypatch.setattr(mcp_pkg, "MCP", _fake_mcp_factory(calls))

        yaml_text = """
name: Disabled
mcp_servers:
  off1:
    command: npx
    enabled: false
  off2:
    command: npx
    disabled: true
agents:
  a:
    instructions: Hi
    tools: [off1, off2]
steps:
  - agent: a
    action: Go
"""
        wf = YAMLWorkflowParser().parse_string(yaml_text)
        assert calls == []
        assert not wf.steps[0].tools

    def test_does_not_expand_env_vars(self, monkeypatch):
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser

        monkeypatch.setenv("SOME_SECRET", "s3cret-value")
        calls = []
        monkeypatch.setattr(mcp_pkg, "MCP", _fake_mcp_factory(calls))

        yaml_text = """
name: No Env Expansion
mcp_servers:
  rem:
    url: https://mcp.example/mcp
    headers:
      X: "${SOME_SECRET}"
      Y: "${env:SOME_SECRET}"
  loc:
    command: npx
    args: ["${SOME_SECRET}"]
    env:
      K: "${SOME_SECRET}"
agents:
  a:
    instructions: Hi
    tools: [rem, loc]
steps:
  - agent: a
    action: Go
"""
        YAMLWorkflowParser().parse_string(yaml_text)
        assert len(calls) == 2
        assert "s3cret-value" not in repr(calls)

    def test_bad_url_and_sse_auth_header_skipped_without_spawning(self, monkeypatch):
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser

        calls = []
        monkeypatch.setattr(mcp_pkg, "MCP", _fake_mcp_factory(calls))

        yaml_text = """
name: Invalid Remote
mcp_servers:
  bad:
    url: "touch MARKER"
  sse_auth:
    url: https://mcp.example/sse
    headers:
      Authorization: Bearer tok
agents:
  a:
    instructions: Hi
    tools: [bad, sse_auth]
steps:
  - agent: a
    action: Go
"""
        wf = YAMLWorkflowParser().parse_string(yaml_text)
        assert calls == []
        assert not wf.steps[0].tools

    def test_tool_registry_takes_precedence_and_existing_tools_preserved(self, monkeypatch):
        from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser

        calls = []
        monkeypatch.setattr(mcp_pkg, "MCP", _fake_mcp_factory(calls))

        def custom_github(q: str) -> str:
            """Custom registered tool."""
            return q

        yaml_text = """
name: Precedence
mcp_servers:
  github:
    url: https://api.github.com/mcp
agents:
  a:
    instructions: Hi
    tools: [github]
steps:
  - agent: a
    action: Go
"""
        parser = YAMLWorkflowParser(tool_registry={"github": custom_github})
        wf = parser.parse_string(yaml_text)
        assert calls == []
        assert wf.steps[0].tools == [custom_github]
