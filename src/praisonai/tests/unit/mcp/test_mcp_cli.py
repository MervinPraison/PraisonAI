"""
Unit tests for MCP CLI commands.

Tests the new CLI commands:
- praisonai mcp tools search
- praisonai mcp tools info
- praisonai mcp tools schema
- praisonai mcp list-tools (with pagination)
"""

import json
from unittest.mock import patch, MagicMock
from praisonai.mcp_server.cli import MCPServerCLI


class TestMCPToolsCLI:
    """Test MCP tools CLI subcommands."""
    
    def test_tools_help(self, capsys):
        """Test tools help output."""
        cli = MCPServerCLI()
        result = cli.cmd_tools(["--help"])
        assert result == cli.EXIT_SUCCESS
        
        captured = capsys.readouterr()
        assert "search" in captured.out.lower()
        assert "info" in captured.out.lower()
        assert "schema" in captured.out.lower()
    
    def test_tools_unknown_subcommand(self, capsys):
        """Test unknown tools subcommand."""
        cli = MCPServerCLI()
        result = cli.cmd_tools(["unknown"])
        assert result == cli.EXIT_ERROR
    
    @patch("praisonai.mcp_server.cli.MCPServerCLI.cmd_tools_search")
    def test_tools_search_dispatch(self, mock_search):
        """Test tools search dispatches correctly."""
        mock_search.return_value = 0
        cli = MCPServerCLI()
        cli.cmd_tools(["search", "query"])
        mock_search.assert_called_once_with(["query"])
    
    @patch("praisonai.mcp_server.cli.MCPServerCLI.cmd_tools_info")
    def test_tools_info_dispatch(self, mock_info):
        """Test tools info dispatches correctly."""
        mock_info.return_value = 0
        cli = MCPServerCLI()
        cli.cmd_tools(["info", "tool.name"])
        mock_info.assert_called_once_with(["tool.name"])
    
    @patch("praisonai.mcp_server.cli.MCPServerCLI.cmd_tools_schema")
    def test_tools_schema_dispatch(self, mock_schema):
        """Test tools schema dispatches correctly."""
        mock_schema.return_value = 0
        cli = MCPServerCLI()
        cli.cmd_tools(["schema", "tool.name"])
        mock_schema.assert_called_once_with(["tool.name"])


class TestToolsSearchCLI:
    """Test tools search CLI command."""
    
    @patch("praisonai.mcp_server.adapters.register_all_tools")
    @patch("praisonai.mcp_server.registry.get_tool_registry")
    def test_search_json_output(self, mock_get_registry, mock_register, capsys):
        """Test search with JSON output."""
        mock_registry = MagicMock()
        mock_registry.search.return_value = (
            [{"name": "test.tool", "description": "Test"}],
            None,
            1
        )
        mock_get_registry.return_value = mock_registry
        
        cli = MCPServerCLI()
        result = cli.cmd_tools_search(["test", "--json"])
        
        assert result == cli.EXIT_SUCCESS
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["total"] == 1
        assert len(output["tools"]) == 1
    
    @patch("praisonai.mcp_server.adapters.register_all_tools")
    @patch("praisonai.mcp_server.registry.get_tool_registry")
    def test_search_no_results(self, mock_get_registry, mock_register, capsys):
        """Test search with no results."""
        mock_registry = MagicMock()
        mock_registry.search.return_value = ([], None, 0)
        mock_get_registry.return_value = mock_registry
        
        cli = MCPServerCLI()
        result = cli.cmd_tools_search(["nonexistent"])
        
        assert result == cli.EXIT_SUCCESS
        captured = capsys.readouterr()
        assert "no tools found" in captured.out.lower()
    
    @patch("praisonai.mcp_server.adapters.register_all_tools")
    @patch("praisonai.mcp_server.registry.get_tool_registry")
    def test_search_with_filters(self, mock_get_registry, mock_register):
        """Test search with category and read-only filters."""
        mock_registry = MagicMock()
        mock_registry.search.return_value = ([], None, 0)
        mock_get_registry.return_value = mock_registry
        
        cli = MCPServerCLI()
        cli.cmd_tools_search(["--category", "memory", "--read-only"])
        
        mock_registry.search.assert_called_once()
        call_kwargs = mock_registry.search.call_args[1]
        assert call_kwargs["category"] == "memory"
        assert call_kwargs["read_only"] is True


class TestToolsInfoCLI:
    """Test tools info CLI command."""
    
    @patch("praisonai.mcp_server.adapters.register_all_tools")
    @patch("praisonai.mcp_server.registry.get_tool_registry")
    def test_info_tool_not_found(self, mock_get_registry, mock_register, capsys):
        """Test info for non-existent tool."""
        mock_registry = MagicMock()
        mock_registry.get.return_value = None
        mock_get_registry.return_value = mock_registry
        
        cli = MCPServerCLI()
        result = cli.cmd_tools_info(["nonexistent.tool"])
        
        assert result == cli.EXIT_ERROR
        captured = capsys.readouterr()
        assert "not found" in captured.err.lower() or "not found" in captured.out.lower()
    
    @patch("praisonai.mcp_server.adapters.register_all_tools")
    @patch("praisonai.mcp_server.registry.get_tool_registry")
    def test_info_json_output(self, mock_get_registry, mock_register, capsys):
        """Test info with JSON output."""
        mock_tool = MagicMock()
        mock_tool.name = "test.tool"
        mock_tool.description = "Test tool"
        mock_tool.category = "test"
        mock_tool.tags = ["unit"]
        mock_tool.to_mcp_schema.return_value = {
            "name": "test.tool",
            "description": "Test tool",
            "annotations": {"readOnlyHint": True},
            "inputSchema": {"type": "object", "properties": {}},
        }
        
        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_tool
        mock_get_registry.return_value = mock_registry
        
        cli = MCPServerCLI()
        result = cli.cmd_tools_info(["test.tool", "--json"])
        
        assert result == cli.EXIT_SUCCESS
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["name"] == "test.tool"


class TestToolsSchemaCLI:
    """Test tools schema CLI command."""
    
    @patch("praisonai.mcp_server.adapters.register_all_tools")
    @patch("praisonai.mcp_server.registry.get_tool_registry")
    def test_schema_output(self, mock_get_registry, mock_register, capsys):
        """Test schema JSON output."""
        mock_tool = MagicMock()
        mock_tool.to_mcp_schema.return_value = {
            "name": "test.tool",
            "description": "Test tool",
            "inputSchema": {"type": "object"},
            "annotations": {},
        }
        
        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_tool
        mock_get_registry.return_value = mock_registry
        
        cli = MCPServerCLI()
        result = cli.cmd_tools_schema(["test.tool"])
        
        assert result == cli.EXIT_SUCCESS
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["name"] == "test.tool"
    
    @patch("praisonai.mcp_server.adapters.register_all_tools")
    @patch("praisonai.mcp_server.registry.get_tool_registry")
    def test_schema_tool_not_found(self, mock_get_registry, mock_register, capsys):
        """Test schema for non-existent tool."""
        mock_registry = MagicMock()
        mock_registry.get.return_value = None
        mock_get_registry.return_value = mock_registry
        
        cli = MCPServerCLI()
        result = cli.cmd_tools_schema(["nonexistent.tool"])
        
        assert result == cli.EXIT_ERROR


class TestListToolsCLI:
    """Test list-tools CLI command with pagination."""
    
    @patch("praisonai.mcp_server.adapters.register_all_tools")
    @patch("praisonai.mcp_server.registry.get_tool_registry")
    def test_list_tools_json(self, mock_get_registry, mock_register, capsys):
        """Test list-tools with JSON output."""
        mock_registry = MagicMock()
        mock_registry.list_paginated.return_value = (
            [{"name": "tool1"}, {"name": "tool2"}],
            "next_cursor_value"
        )
        mock_get_registry.return_value = mock_registry
        
        cli = MCPServerCLI()
        result = cli.cmd_list_tools(["--json"])
        
        assert result == cli.EXIT_SUCCESS
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert len(output["tools"]) == 2
        assert output["nextCursor"] == "next_cursor_value"
    
    @patch("praisonai.mcp_server.adapters.register_all_tools")
    @patch("praisonai.mcp_server.registry.get_tool_registry")
    def test_list_tools_with_cursor(self, mock_get_registry, mock_register):
        """Test list-tools with pagination cursor."""
        mock_registry = MagicMock()
        mock_registry.list_paginated.return_value = ([], None)
        mock_registry.list_all.return_value = []
        mock_get_registry.return_value = mock_registry
        
        cli = MCPServerCLI()
        cli.cmd_list_tools(["--cursor", "abc123", "--limit", "10"])
        
        mock_registry.list_paginated.assert_called_once_with(
            cursor="abc123",
            page_size=10
        )
