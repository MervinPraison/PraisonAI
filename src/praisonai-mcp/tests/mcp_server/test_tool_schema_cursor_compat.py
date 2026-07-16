"""
Regression tests for Cursor / strict MCP client tool schema compatibility.

Ensures no tool emits ``inputSchema.required: null`` in the ``tools/list``
response. JSON Schema requires ``required`` to be an array of strings or absent
(never ``null``); Cursor validates with Zod and discards the entire tool
offerings batch when any tool fails. See issue #3111.
"""

import json

from praisonai_mcp.mcp_server.registry import (
    MCPToolDefinition,
    MCPToolRegistry,
    _normalize_input_schema,
)


def _no_arg_tool():
    """A zero-argument tool."""
    return "ok"


def _optional_arg_tool(session_id: str = None):
    """A tool whose only argument is optional."""
    return session_id


def _required_arg_tool(message: str, model: str = "gpt-4o-mini"):
    """A tool with a required argument."""
    return message


def test_generated_schema_omits_required_when_empty():
    reg = MCPToolRegistry()
    reg.register("no_arg", _no_arg_tool)
    reg.register("optional_arg", _optional_arg_tool)

    for tool in reg.list_schemas():
        schema = tool["inputSchema"]
        # "required" must be absent (not present-as-null) or an empty list.
        assert "required" not in schema or schema["required"] == []
        assert '"required": null' not in json.dumps(schema)


def test_generated_schema_keeps_required_when_present():
    reg = MCPToolRegistry()
    reg.register("required_arg", _required_arg_tool)

    schema = reg.list_schemas()[0]["inputSchema"]
    assert schema["required"] == ["message"]


def test_serialized_json_never_contains_required_null():
    reg = MCPToolRegistry()
    reg.register("no_arg", _no_arg_tool)
    reg.register("optional_arg", _optional_arg_tool)
    reg.register("required_arg", _required_arg_tool)

    for tool in reg.list_schemas():
        blob = json.dumps(tool)
        assert '"required": null' not in blob, tool["name"]
        assert '"required":null' not in blob, tool["name"]


def test_normalize_strips_legacy_required_null():
    # Pre-built schema with the legacy `required: null` bug.
    legacy = {"type": "object", "properties": {}, "required": None}
    normalized = _normalize_input_schema(legacy)
    assert "required" not in normalized


def test_normalize_preserves_valid_required_array():
    valid = {"type": "object", "properties": {}, "required": ["message"]}
    normalized = _normalize_input_schema(valid)
    assert normalized["required"] == ["message"]


def test_to_mcp_schema_normalizes_prebuilt_required_null():
    tool = MCPToolDefinition(
        name="legacy",
        description="legacy tool",
        handler=_no_arg_tool,
        input_schema={"type": "object", "properties": {}, "required": None},
    )
    schema = tool.to_mcp_schema()["inputSchema"]
    assert "required" not in schema
    assert '"required": null' not in json.dumps(schema)


def test_paginated_and_search_paths_never_emit_required_null():
    reg = MCPToolRegistry()
    reg.register("no_arg", _no_arg_tool)
    reg.register("required_arg", _required_arg_tool)

    page, _ = reg.list_paginated()
    for tool in page:
        assert '"required": null' not in json.dumps(tool)

    results, _, _ = reg.search()
    for tool in results:
        assert '"required": null' not in json.dumps(tool)
