"""
Unit tests for the interactive tools provider.

Tests the canonical source of truth for default tools in interactive modes.
"""

import os
import pytest
from unittest.mock import patch, MagicMock


class TestToolGroups:
    """Tests for tool group definitions."""
    
    def test_tool_groups_defined(self):
        """Test that all expected tool groups are defined."""
        from praisonai.cli.features.interactive_tools import TOOL_GROUPS
        
        assert "acp" in TOOL_GROUPS
        assert "lsp" in TOOL_GROUPS
        assert "basic" in TOOL_GROUPS
        assert "interactive" in TOOL_GROUPS
    
    def test_acp_tools_list(self):
        """Test ACP tool group contains expected tools."""
        from praisonai.cli.features.interactive_tools import TOOL_GROUPS
        
        expected = {
            "acp_create_file",
            "acp_edit_file",
            "acp_delete_file",
            "acp_execute_command",
        }
        assert set(TOOL_GROUPS["acp"]) == expected
    
    def test_lsp_tools_list(self):
        """Test LSP tool group contains expected tools."""
        from praisonai.cli.features.interactive_tools import TOOL_GROUPS
        
        expected = {
            "lsp_list_symbols",
            "lsp_find_definition",
            "lsp_find_references",
            "lsp_get_diagnostics",
        }
        assert set(TOOL_GROUPS["lsp"]) == expected
    
    def test_basic_tools_list(self):
        """Test basic tool group contains expected tools."""
        from praisonai.cli.features.interactive_tools import TOOL_GROUPS
        
        expected = {
            "read_file",
            "write_file",
            "list_files",
            "execute_command",
            "internet_search",
        }
        assert set(TOOL_GROUPS["basic"]) == expected
    
    def test_interactive_group_is_union(self):
        """Test interactive group is union of all groups."""
        from praisonai.cli.features.interactive_tools import TOOL_GROUPS
        
        expected = set(TOOL_GROUPS["acp"]) | set(TOOL_GROUPS["lsp"]) | set(TOOL_GROUPS["basic"])
        assert set(TOOL_GROUPS["interactive"]) == expected


class TestToolConfig:
    """Tests for ToolConfig dataclass."""
    
    def test_default_config(self):
        """Test default configuration values."""
        from praisonai.cli.features.interactive_tools import ToolConfig
        
        config = ToolConfig()
        assert config.enable_acp is True
        assert config.enable_lsp is True
        assert config.enable_basic is True
        assert config.approval_mode == "auto"
    
    def test_config_from_env_disable_acp(self):
        """Test config from env with ACP disabled."""
        from praisonai.cli.features.interactive_tools import ToolConfig
        
        with patch.dict(os.environ, {"PRAISON_TOOLS_DISABLE": "acp"}):
            config = ToolConfig.from_env()
            assert config.enable_acp is False
            assert config.enable_lsp is True
    
    def test_config_from_env_disable_lsp(self):
        """Test config from env with LSP disabled."""
        from praisonai.cli.features.interactive_tools import ToolConfig
        
        with patch.dict(os.environ, {"PRAISON_TOOLS_DISABLE": "lsp"}):
            config = ToolConfig.from_env()
            assert config.enable_acp is True
            assert config.enable_lsp is False
    
    def test_config_from_env_disable_multiple(self):
        """Test config from env with multiple groups disabled."""
        from praisonai.cli.features.interactive_tools import ToolConfig
        
        with patch.dict(os.environ, {"PRAISON_TOOLS_DISABLE": "acp,lsp"}):
            config = ToolConfig.from_env()
            assert config.enable_acp is False
            assert config.enable_lsp is False
            assert config.enable_basic is True
    
    def test_config_from_env_workspace(self):
        """Test config from env with workspace override."""
        from praisonai.cli.features.interactive_tools import ToolConfig
        
        with patch.dict(os.environ, {"PRAISON_WORKSPACE": "/custom/path"}):
            config = ToolConfig.from_env()
            assert config.workspace == "/custom/path"


class TestResolveToolGroups:
    """Tests for resolve_tool_groups function."""
    
    def test_resolve_all_enabled(self):
        """Test resolving with all groups enabled."""
        from praisonai.cli.features.interactive_tools import resolve_tool_groups, ToolConfig, TOOL_GROUPS
        
        config = ToolConfig()
        tool_names = resolve_tool_groups(config=config)
        
        expected = set(TOOL_GROUPS["interactive"])
        assert tool_names == expected
    
    def test_resolve_disable_acp(self):
        """Test resolving with ACP disabled."""
        from praisonai.cli.features.interactive_tools import resolve_tool_groups, ToolConfig, TOOL_GROUPS
        
        config = ToolConfig(enable_acp=False)
        tool_names = resolve_tool_groups(disable=["acp"], config=config)
        
        # Should not contain ACP tools
        for acp_tool in TOOL_GROUPS["acp"]:
            assert acp_tool not in tool_names
        
        # Should contain LSP and basic tools
        for lsp_tool in TOOL_GROUPS["lsp"]:
            assert lsp_tool in tool_names
    
    def test_resolve_disable_lsp(self):
        """Test resolving with LSP disabled."""
        from praisonai.cli.features.interactive_tools import resolve_tool_groups, ToolConfig, TOOL_GROUPS
        
        config = ToolConfig(enable_lsp=False)
        tool_names = resolve_tool_groups(disable=["lsp"], config=config)
        
        # Should not contain LSP tools
        for lsp_tool in TOOL_GROUPS["lsp"]:
            assert lsp_tool not in tool_names
        
        # Should contain ACP and basic tools
        for acp_tool in TOOL_GROUPS["acp"]:
            assert acp_tool in tool_names
    
    def test_resolve_specific_groups(self):
        """Test resolving specific groups only."""
        from praisonai.cli.features.interactive_tools import resolve_tool_groups, TOOL_GROUPS
        
        tool_names = resolve_tool_groups(groups=["basic"])
        
        assert tool_names == set(TOOL_GROUPS["basic"])


class TestGetInteractiveTools:
    """Tests for get_interactive_tools function."""
    
    def test_get_tools_returns_list(self):
        """Test that get_interactive_tools returns a list."""
        from praisonai.cli.features.interactive_tools import get_interactive_tools, ToolConfig
        
        config = ToolConfig(workspace="/tmp")
        tools = get_interactive_tools(config=config)
        
        assert isinstance(tools, list)
    
    def test_get_tools_deterministic_order(self):
        """Test that tool order is deterministic."""
        from praisonai.cli.features.interactive_tools import get_interactive_tools, ToolConfig
        
        config = ToolConfig(workspace="/tmp")
        tools1 = get_interactive_tools(config=config)
        tools2 = get_interactive_tools(config=config)
        
        names1 = [t.__name__ for t in tools1]
        names2 = [t.__name__ for t in tools2]
        
        assert names1 == names2
    
    def test_get_tools_with_disable_acp(self):
        """Test get_interactive_tools with ACP disabled."""
        from praisonai.cli.features.interactive_tools import get_interactive_tools, ToolConfig
        
        config = ToolConfig(workspace="/tmp", enable_acp=False)
        tools = get_interactive_tools(config=config, disable=["acp"])
        
        tool_names = [t.__name__ for t in tools]
        acp_tools = [n for n in tool_names if n.startswith("acp_")]
        
        assert len(acp_tools) == 0
    
    def test_get_tools_with_disable_lsp(self):
        """Test get_interactive_tools with LSP disabled."""
        from praisonai.cli.features.interactive_tools import get_interactive_tools, ToolConfig
        
        config = ToolConfig(workspace="/tmp", enable_lsp=False)
        tools = get_interactive_tools(config=config, disable=["lsp"])
        
        tool_names = [t.__name__ for t in tools]
        lsp_tools = [n for n in tool_names if n.startswith("lsp_")]
        
        assert len(lsp_tools) == 0


class TestMergeToolOverrides:
    """Tests for merge_tool_overrides function."""
    
    def test_merge_add_tools(self):
        """Test adding tools to default list."""
        from praisonai.cli.features.interactive_tools import merge_tool_overrides
        
        def tool_a():
            pass
        
        def tool_b():
            pass
        
        def tool_c():
            pass
        
        default = [tool_a, tool_b]
        result = merge_tool_overrides(default, add_tools=[tool_c])
        
        names = [t.__name__ for t in result]
        assert "tool_c" in names
    
    def test_merge_remove_tools(self):
        """Test removing tools from default list."""
        from praisonai.cli.features.interactive_tools import merge_tool_overrides
        
        def tool_a():
            pass
        
        def tool_b():
            pass
        
        default = [tool_a, tool_b]
        result = merge_tool_overrides(default, remove_names=["tool_a"])
        
        names = [t.__name__ for t in result]
        assert "tool_a" not in names
        assert "tool_b" in names


class TestLazyImports:
    """Tests for lazy import behavior."""
    
    def test_import_time_fast(self):
        """Test that importing the module is fast (no heavy deps)."""
        import time
        
        start = time.time()
        # Force reimport
        import importlib
        import praisonai.cli.features.interactive_tools as module
        importlib.reload(module)
        duration = time.time() - start
        
        # Should be under 100ms
        assert duration < 0.1, f"Import took {duration:.3f}s, expected < 0.1s"
    
    def test_tool_groups_available_without_runtime(self):
        """Test that TOOL_GROUPS is available without runtime initialization."""
        from praisonai.cli.features.interactive_tools import TOOL_GROUPS
        
        # Should be accessible immediately
        assert len(TOOL_GROUPS) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
