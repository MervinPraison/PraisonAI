"""
Regression tests for MCP tool registration parity.

Ensures the discovery CLI commands (`list-tools`, `tools search|info|schema`)
register the same tool surface as `serve` and `doctor` by using `register_all()`
instead of the partial `register_all_tools()`.

See issue #3208.
"""


class TestListToolsParity:
    """Tool registration parity between listing commands and serve/doctor."""

    def test_register_all_is_superset_of_register_all_tools(self):
        """register_all() must expose at least as many tools as register_all_tools()."""
        from praisonai_mcp.mcp_server.adapters import register_all, register_all_tools
        from praisonai_mcp.mcp_server.registry import get_tool_registry

        registry = get_tool_registry()

        registry._tools.clear()
        register_all_tools()
        partial_count = len(registry.list_all())

        registry._tools.clear()
        register_all()
        full_count = len(registry.list_all())

        assert full_count >= partial_count, (
            f"register_all ({full_count}) must be a superset of "
            f"register_all_tools ({partial_count})"
        )
        assert full_count > partial_count, (
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
