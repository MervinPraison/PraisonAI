"""Tool search: config, bridge tools, deferral and catalog search.

These were script-style checks that caught every exception and returned
True/False, so pytest passed them whatever happened. They now assert.
"""

from praisonaiagents.tools.tool_search import (
    PRAISONAI_CORE_TOOLS,
    ToolSearchConfig,
    assemble_tool_defs,
    bridge_tool_schemas,
    search_catalog,
)

BRIDGE = ["tool_search", "tool_describe", "tool_call"]


def _names(defs):
    return [d["function"]["name"] for d in defs]


def test_config_from_raw():
    assert ToolSearchConfig().enabled == "auto"
    assert ToolSearchConfig.from_raw(True).enabled == "on"
    assert ToolSearchConfig.from_raw(False).enabled == "off"
    assert PRAISONAI_CORE_TOOLS
    assert _names(bridge_tool_schemas()) == BRIDGE


def test_nothing_deferred_without_deferrable_tools():
    tool_defs = [{"type": "function", "function": {"name": "test_tool", "description": "Test"}}]
    for enabled in ("off", "on"):
        assembled, metadata = assemble_tool_defs(tool_defs, ToolSearchConfig(enabled=enabled))
        assert _names(assembled) == ["test_tool"], enabled
        assert metadata["bridge_mode"] is False and metadata["deferred_count"] == 0, enabled


def test_deferrable_tool_is_replaced_by_bridge_and_searchable():
    tool_defs = [
        {"type": "function", "function": {"name": "read_file", "description": "Read file"}},
        {
            "type": "function",
            "function": {"name": "mcp_weather", "description": "Get weather"},
            "__praisonai_deferrable__": True,
        },
    ]
    assembled, metadata = assemble_tool_defs(tool_defs, ToolSearchConfig(enabled="on"))
    assert _names(assembled) == ["read_file"] + BRIDGE
    assert metadata["bridge_mode"] is True and metadata["deferred_count"] == 1
    assert len(metadata["catalog"]) == 1

    results = search_catalog(metadata["deferrable_tools"], "weather", limit=5)
    assert [r["name"] for r in results] == ["mcp_weather"]


def test_config_is_exported_from_config_module():
    from praisonaiagents.config import ToolSearchConfig as Exported

    assert Exported is ToolSearchConfig
