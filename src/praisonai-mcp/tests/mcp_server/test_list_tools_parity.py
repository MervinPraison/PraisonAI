"""
Regression tests for MCP tool registration parity.

Ensures the discovery CLI commands (`list-tools`, `tools search|info|schema`)
register the same tool surface as `serve` and `doctor` by using `register_all()`
instead of the partial `register_all_tools()`.

See issue #3208.
"""

import pytest


@pytest.fixture
def isolated_tool_registry():
    """Provide a clean tool registry and restore prior state after the test.

    The tool registry is a process-wide singleton whose ``_tools`` and
    ``_lazy_loaders`` are mutated by the parity assertions below. Snapshot and
    restore both so tests running later in the same process are unaffected.
    """
    from praisonai_mcp.mcp_server.registry import get_tool_registry

    registry = get_tool_registry()
    saved_tools = dict(registry._tools)
    saved_loaders = list(registry._lazy_loaders)
    try:
        registry._tools.clear()
        registry._lazy_loaders.clear()
        yield registry
    finally:
        registry._tools.clear()
        registry._tools.update(saved_tools)
        registry._lazy_loaders.clear()
        registry._lazy_loaders.extend(saved_loaders)


class TestListToolsParity:
    """Tool registration parity between listing commands and serve/doctor."""

    def test_register_all_is_superset_of_register_all_tools(self, isolated_tool_registry):
        """register_all() must expose every tool register_all_tools() does, plus more."""
        from praisonai_mcp.mcp_server.adapters import register_all, register_all_tools

        registry = isolated_tool_registry

        registry._tools.clear()
        registry._lazy_loaders.clear()
        register_all_tools()
        partial_names = {tool.name for tool in registry.list_all()}

        registry._tools.clear()
        registry._lazy_loaders.clear()
        register_all()
        full_names = {tool.name for tool in registry.list_all()}

        missing = partial_names - full_names
        assert not missing, (
            f"register_all() must be a strict superset of register_all_tools(); "
            f"missing tools: {sorted(missing)}"
        )
        assert len(full_names) > len(partial_names), (
            "register_all should register extended and CLI bridge tools "
            "beyond register_all_tools"
        )

    def test_listing_commands_use_full_registration(self):
        """The listing subcommands must call register_all(), not register_all_tools()."""
        import inspect
        from praisonai_mcp.mcp_server import cli

        for method in (
            "cmd_list_tools",
            "cmd_tools_search",
            "cmd_tools_info",
            "cmd_tools_schema",
        ):
            func = getattr(cli.MCPServerCLI, method, None)
            if func is None:
                continue
            body = inspect.getsource(func)
            assert "register_all()" in body, (
                f"{method} must call register_all() for tool parity"
            )
            assert "register_all_tools()" not in body, (
                f"{method} must not use partial register_all_tools()"
            )
