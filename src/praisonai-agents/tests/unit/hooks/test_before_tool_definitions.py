"""
Unit tests for the BEFORE_TOOL_DEFINITIONS hook extension point.

Verifies that a registered hook can inspect and rewrite the advertised tool
definitions (drop a tool, edit a description) before they reach the LLM, and
that the agent runtime adopts those mutations. Backward compatible: no hook
registered means the tool definitions are unchanged.
"""

import pytest

from praisonaiagents.hooks.types import HookEvent, HookResult
from praisonaiagents.hooks.events import BeforeToolDefinitionsInput
from praisonaiagents.hooks.registry import HookRegistry
from praisonaiagents.hooks.runner import HookRunner


def _sample_tools():
    return [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a file.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "delete_file",
                "description": "Delete a file.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]


def _make_input(tools):
    return BeforeToolDefinitionsInput(
        session_id="test-session",
        cwd="/tmp",
        event_name=HookEvent.BEFORE_TOOL_DEFINITIONS,
        timestamp="2024-01-01T00:00:00",
        agent_name="TestAgent",
        model="gpt-4o",
        tool_definitions=tools,
    )


class TestBeforeToolDefinitionsEvent:
    def test_event_value(self):
        assert HookEvent.BEFORE_TOOL_DEFINITIONS.value == "before_tool_definitions"

    def test_input_to_dict(self):
        inp = _make_input(_sample_tools())
        d = inp.to_dict()
        assert d["tool_definitions_count"] == 2
        assert d["model"] == "gpt-4o"
        assert d["agent_name"] == "TestAgent"


class TestBeforeToolDefinitionsHook:
    def test_hook_can_edit_description_and_drop_tool(self):
        registry = HookRegistry()

        def shape_tools(data):
            # Drop "delete_file" and annotate "read_file"
            data.tool_definitions[:] = [
                t for t in data.tool_definitions
                if t["function"]["name"] != "delete_file"
            ]
            for t in data.tool_definitions:
                if t["function"]["name"] == "read_file":
                    t["function"]["description"] += " (sandboxed)"
            return HookResult.allow()

        registry.register_function(
            event=HookEvent.BEFORE_TOOL_DEFINITIONS,
            func=shape_tools,
        )

        runner = HookRunner(registry)
        inp = _make_input(_sample_tools())
        runner.execute_sync(HookEvent.BEFORE_TOOL_DEFINITIONS, inp)

        names = [t["function"]["name"] for t in inp.tool_definitions]
        assert "delete_file" not in names
        assert "read_file" in names
        read_tool = next(t for t in inp.tool_definitions if t["function"]["name"] == "read_file")
        assert read_tool["function"]["description"].endswith("(sandboxed)")

    def test_no_hook_is_noop(self):
        registry = HookRegistry()
        runner = HookRunner(registry)
        tools = _sample_tools()
        inp = _make_input(tools)
        runner.execute_sync(HookEvent.BEFORE_TOOL_DEFINITIONS, inp)
        assert len(inp.tool_definitions) == 2
        assert [t["function"]["name"] for t in inp.tool_definitions] == [
            "read_file", "delete_file"
        ]


class TestAgentIntegration:
    def test_apply_before_tool_definitions_hook_adopts_mutations(self):
        from praisonaiagents import Agent

        registry = HookRegistry()

        def drop_delete(data):
            data.tool_definitions[:] = [
                t for t in data.tool_definitions
                if t["function"]["name"] != "delete_file"
            ]
            return HookResult.allow()

        registry.register_function(
            event=HookEvent.BEFORE_TOOL_DEFINITIONS,
            func=drop_delete,
        )

        agent = Agent(name="TestAgent", instructions="test", llm="gpt-4o", hooks=registry)

        result = agent._apply_before_tool_definitions_hook(_sample_tools())
        names = [t["function"]["name"] for t in result]
        assert names == ["read_file"]

    def test_apply_before_tool_definitions_hook_noop_without_tools(self):
        from praisonaiagents import Agent

        agent = Agent(name="TestAgent", instructions="test", llm="gpt-4o")
        result = agent._apply_before_tool_definitions_hook([])
        assert result == []
