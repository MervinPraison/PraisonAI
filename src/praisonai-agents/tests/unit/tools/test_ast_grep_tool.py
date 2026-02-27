"""
TDD Tests for ast_grep tool.

Tests cover:
1. Tool availability detection (installed vs not installed)
2. Graceful fallback when not installed
3. Tool assignment to Agent
4. Autonomy mode integration
5. Search, rewrite, and scan operations
"""

import pytest
import subprocess
from unittest.mock import patch, MagicMock


class TestAstGrepToolAvailability:
    """Test ast-grep tool availability detection."""
    
    def test_is_available_when_installed(self):
        """Tool should report available when sg binary exists."""
        from praisonaiagents.tools.ast_grep_tool import is_ast_grep_available
        
        with patch('shutil.which') as mock_which:
            mock_which.return_value = '/usr/local/bin/sg'
            assert is_ast_grep_available() is True
    
    def test_is_not_available_when_not_installed(self):
        """Tool should report not available when sg binary doesn't exist."""
        from praisonaiagents.tools import ast_grep_tool
        from praisonaiagents.tools.ast_grep_tool import is_ast_grep_available
        
        # Clear cache to ensure fresh check
        ast_grep_tool._availability_cache = None
        
        with patch('praisonaiagents.tools.ast_grep_tool.shutil.which') as mock_which:
            mock_which.return_value = None
            result = is_ast_grep_available()
            assert result is False
    
    def test_availability_cached(self):
        """Availability check should be cached for performance."""
        from praisonaiagents.tools import ast_grep_tool
        
        # Clear cache
        ast_grep_tool._availability_cache = None
        
        with patch('shutil.which') as mock_which:
            mock_which.return_value = '/usr/local/bin/sg'
            
            # First call
            result1 = ast_grep_tool.is_ast_grep_available()
            # Second call should use cache
            result2 = ast_grep_tool.is_ast_grep_available()
            
            # which should only be called once due to caching
            assert mock_which.call_count == 1
            assert result1 is True
            assert result2 is True


class TestAstGrepToolGracefulFallback:
    """Test graceful fallback when ast-grep is not installed."""
    
    def test_search_returns_error_when_not_installed(self):
        """Search should return helpful error when not installed."""
        from praisonaiagents.tools.ast_grep_tool import ast_grep_search
        
        with patch('praisonaiagents.tools.ast_grep_tool.is_ast_grep_available') as mock_avail:
            mock_avail.return_value = False
            
            result = ast_grep_search("def $FN($$$)", lang="python", path=".")
            
            assert "not installed" in result.lower() or "not available" in result.lower()
            assert "pip install ast-grep-cli" in result
    
    def test_rewrite_returns_error_when_not_installed(self):
        """Rewrite should return helpful error when not installed."""
        from praisonaiagents.tools.ast_grep_tool import ast_grep_rewrite
        
        with patch('praisonaiagents.tools.ast_grep_tool.is_ast_grep_available') as mock_avail:
            mock_avail.return_value = False
            
            result = ast_grep_rewrite("def $FN($$$)", "def $FN(*args)", lang="python", path=".")
            
            assert "not installed" in result.lower() or "not available" in result.lower()
    
    def test_scan_returns_error_when_not_installed(self):
        """Scan should return helpful error when not installed."""
        from praisonaiagents.tools.ast_grep_tool import ast_grep_scan
        
        with patch('praisonaiagents.tools.ast_grep_tool.is_ast_grep_available') as mock_avail:
            mock_avail.return_value = False
            
            result = ast_grep_scan(path=".")
            
            assert "not installed" in result.lower() or "not available" in result.lower()
    
    def test_tool_does_not_crash_when_not_installed(self):
        """Tool should never crash, even when not installed."""
        from praisonaiagents.tools.ast_grep_tool import (
            ast_grep_search, ast_grep_rewrite, ast_grep_scan
        )
        
        with patch('praisonaiagents.tools.ast_grep_tool.is_ast_grep_available') as mock_avail:
            mock_avail.return_value = False
            
            # None of these should raise exceptions
            try:
                ast_grep_search("pattern", lang="python", path=".")
                ast_grep_rewrite("old", "new", lang="python", path=".")
                ast_grep_scan(path=".")
            except Exception as e:
                pytest.fail(f"Tool crashed when not installed: {e}")


class TestAstGrepToolOperations:
    """Test ast-grep tool operations when installed."""
    
    def test_search_executes_subprocess(self):
        """Search should execute sg CLI with correct arguments."""
        from praisonaiagents.tools.ast_grep_tool import ast_grep_search
        
        with patch('praisonaiagents.tools.ast_grep_tool.is_ast_grep_available') as mock_avail:
            mock_avail.return_value = True
            
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout='{"matches": []}',
                    stderr=''
                )
                
                result = ast_grep_search("def $FN($$$)", lang="python", path="/test/path")
                
                mock_run.assert_called_once()
                call_args = mock_run.call_args
                cmd_list = call_args[0][0]
                
                assert 'sg' in cmd_list[0] or cmd_list[0] == 'sg'
                assert '--pattern' in cmd_list or 'def $FN($$$)' in cmd_list
                assert '--lang' in cmd_list or 'python' in cmd_list
                # Verify result is returned
                assert result is not None
    
    def test_search_handles_subprocess_error(self):
        """Search should handle subprocess errors gracefully."""
        from praisonaiagents.tools.ast_grep_tool import ast_grep_search
        
        with patch('praisonaiagents.tools.ast_grep_tool.is_ast_grep_available') as mock_avail:
            mock_avail.return_value = True
            
            with patch('subprocess.run') as mock_run:
                mock_run.side_effect = subprocess.SubprocessError("Command failed")
                
                result = ast_grep_search("pattern", lang="python", path=".")
                
                assert "error" in result.lower() or "failed" in result.lower()
    
    def test_rewrite_dry_run_by_default(self):
        """Rewrite should use dry-run by default for safety."""
        from praisonaiagents.tools.ast_grep_tool import ast_grep_rewrite
        
        with patch('praisonaiagents.tools.ast_grep_tool.is_ast_grep_available') as mock_avail:
            mock_avail.return_value = True
            
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout='No changes',
                    stderr=''
                )
                
                result = ast_grep_rewrite("old", "new", lang="python", path=".")
                
                # Should not actually modify files without explicit flag
                call_args = mock_run.call_args
                cmd_list = call_args[0][0]
                # Check that --update-all is NOT in the command (dry-run mode)
                assert '--update-all' not in cmd_list
                assert mock_run.called
                assert result is not None


class TestAstGrepToolAgentIntegration:
    """Test ast-grep tool integration with Agent."""
    
    def test_tool_can_be_assigned_to_agent(self):
        """Tool should be assignable to Agent via tools parameter."""
        from praisonaiagents import Agent
        from praisonaiagents.tools.ast_grep_tool import ast_grep_search
        
        # Should not raise
        agent = Agent(
            name="test",
            instructions="Test agent",
            tools=[ast_grep_search],
        )
        
        assert ast_grep_search in agent.tools or any(
            getattr(t, '__name__', '') == 'ast_grep_search' for t in agent.tools
        )
    
    def test_tool_works_when_not_installed_but_assigned(self):
        """Agent should work even if ast-grep tool is assigned but not installed."""
        from praisonaiagents import Agent
        from praisonaiagents.tools.ast_grep_tool import ast_grep_search
        
        with patch('praisonaiagents.tools.ast_grep_tool.is_ast_grep_available') as mock_avail:
            mock_avail.return_value = False
            
            # Should not raise during agent creation
            agent = Agent(
                name="test",
                instructions="Test agent",
                tools=[ast_grep_search],
            )
            
            # Agent should be created successfully
            assert agent is not None
    
    def test_tool_import_via_lazy_loading(self):
        """Tool should be importable via lazy loading from tools package."""
        # This tests the TOOL_MAPPINGS integration
        from praisonaiagents.tools import ast_grep_search
        
        assert callable(ast_grep_search)
    
    def test_all_ast_grep_tools_importable(self):
        """All ast-grep tools should be importable."""
        from praisonaiagents.tools import (
            ast_grep_search,
            ast_grep_rewrite,
            ast_grep_scan,
        )
        
        assert callable(ast_grep_search)
        assert callable(ast_grep_rewrite)
        assert callable(ast_grep_scan)


class TestAstGrepToolAutonomyIntegration:
    """Test ast-grep tool integration with autonomy mode."""
    
    def test_autonomy_config_has_default_tools_field(self):
        """AutonomyConfig should have default_tools field."""
        from praisonaiagents.agent.autonomy import AutonomyConfig
        
        config = AutonomyConfig()
        assert hasattr(config, 'default_tools')
    
    def test_autonomy_default_tools_includes_ast_grep(self):
        """Autonomy default_tools should include ast_grep when available."""
        from praisonaiagents.tools.ast_grep_tool import get_ast_grep_tools
        
        with patch('praisonaiagents.tools.ast_grep_tool.is_ast_grep_available') as mock_avail:
            mock_avail.return_value = True
            
            tools = get_ast_grep_tools()
            
            # Should include ast_grep tools
            tool_names = [getattr(t, '__name__', str(t)) for t in tools]
            assert any('ast_grep' in name for name in tool_names)
    
    def test_autonomy_default_tools_graceful_fallback(self):
        """get_ast_grep_tools should return tools even when ast-grep not installed."""
        from praisonaiagents.tools.ast_grep_tool import get_ast_grep_tools
        
        # get_ast_grep_tools always returns the tools - they handle unavailability internally
        tools = get_ast_grep_tools()
        
        # Should return a list with the 3 ast-grep tools
        assert isinstance(tools, list)
        assert len(tools) == 3
    
    def test_agent_with_autonomy_gets_default_tools(self):
        """Agent with autonomy enabled should get default tools injected."""
        from praisonaiagents import Agent
        from praisonaiagents.tools.ast_grep_tool import ast_grep_search
        
        with patch('praisonaiagents.tools.ast_grep_tool.is_ast_grep_available') as mock_avail:
            mock_avail.return_value = True
            
            agent = Agent(
                name="test",
                instructions="Test agent",
                autonomy=True,
            )
            
            # Agent should have ast-grep tools injected
            assert agent is not None
            assert len(agent.tools) > 0, "Agent with autonomy=True should have default tools"
            
            # Verify ast_grep_search is in the tools
            tool_names = [getattr(t, '__name__', str(t)) for t in agent.tools]
            assert 'ast_grep_search' in tool_names, f"ast_grep_search should be in agent.tools, got: {tool_names}"
    
    def test_agent_with_custom_default_tools(self):
        """Agent with AutonomyConfig(default_tools=[X]) should use custom tools."""
        from praisonaiagents import Agent
        from praisonaiagents.agent.autonomy import AutonomyConfig
        
        def custom_tool():
            """A custom tool for testing."""
            return "custom"
        
        config = AutonomyConfig(default_tools=[custom_tool])
        
        agent = Agent(
            name="test",
            instructions="Test agent",
            autonomy=config,
        )
        
        # Agent should have the custom tool
        assert custom_tool in agent.tools, "Custom default_tools should be injected"
    
    def test_agent_autonomy_default_tools_in_config_dict(self):
        """AutonomyConfig.default_tools should be serialized to agent.autonomy_config dict."""
        from praisonaiagents import Agent
        
        with patch('praisonaiagents.tools.ast_grep_tool.is_ast_grep_available') as mock_avail:
            mock_avail.return_value = True
            
            agent = Agent(
                name="test",
                instructions="Test agent",
                autonomy=True,
            )
            
            # default_tools should be in the autonomy_config dict
            assert 'default_tools' in agent.autonomy_config, "default_tools should be in autonomy_config dict"


class TestAstGrepToolSchema:
    """Test ast-grep tool schema generation for LLM."""
    
    def test_search_has_docstring(self):
        """Search tool should have proper docstring for LLM."""
        from praisonaiagents.tools.ast_grep_tool import ast_grep_search
        
        assert ast_grep_search.__doc__ is not None
        assert len(ast_grep_search.__doc__) > 50
    
    def test_rewrite_has_docstring(self):
        """Rewrite tool should have proper docstring for LLM."""
        from praisonaiagents.tools.ast_grep_tool import ast_grep_rewrite
        
        assert ast_grep_rewrite.__doc__ is not None
        assert len(ast_grep_rewrite.__doc__) > 50
    
    def test_scan_has_docstring(self):
        """Scan tool should have proper docstring for LLM."""
        from praisonaiagents.tools.ast_grep_tool import ast_grep_scan
        
        assert ast_grep_scan.__doc__ is not None
        assert len(ast_grep_scan.__doc__) > 50


class TestAstGrepToolEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_pattern_handled(self):
        """Empty pattern should be handled gracefully."""
        from praisonaiagents.tools.ast_grep_tool import ast_grep_search
        
        with patch('praisonaiagents.tools.ast_grep_tool.is_ast_grep_available') as mock_avail:
            mock_avail.return_value = True
            
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(returncode=1, stdout='', stderr='Invalid pattern')
                
                result = ast_grep_search("", lang="python", path=".")
                
                # Should not crash, should return error message
                assert isinstance(result, str)
    
    def test_invalid_language_handled(self):
        """Invalid language should be handled gracefully."""
        from praisonaiagents.tools.ast_grep_tool import ast_grep_search
        
        with patch('praisonaiagents.tools.ast_grep_tool.is_ast_grep_available') as mock_avail:
            mock_avail.return_value = True
            
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=1, stdout='', stderr='Unknown language'
                )
                
                result = ast_grep_search("pattern", lang="invalid_lang", path=".")
                
                assert isinstance(result, str)
    
    def test_nonexistent_path_handled(self):
        """Nonexistent path should be handled gracefully."""
        from praisonaiagents.tools.ast_grep_tool import ast_grep_search
        
        with patch('praisonaiagents.tools.ast_grep_tool.is_ast_grep_available') as mock_avail:
            mock_avail.return_value = True
            
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=1, stdout='', stderr='Path not found'
                )
                
                result = ast_grep_search("pattern", lang="python", path="/nonexistent/path")
                
                assert isinstance(result, str)


class TestAstGrepToolImportPerformance:
    """Test that tool import doesn't impact performance."""
    
    def test_lazy_import_no_subprocess_on_import(self):
        """Importing the tool should not execute subprocess."""
        with patch('subprocess.run') as mock_run:
            # Re-import to test
            import importlib
            import praisonaiagents.tools.ast_grep_tool as module
            importlib.reload(module)
            
            # subprocess.run should not be called on import
            mock_run.assert_not_called()
    
    def test_availability_not_checked_on_import(self):
        """Availability should not be checked on module import."""
        with patch('shutil.which') as mock_which:
            import importlib
            import praisonaiagents.tools.ast_grep_tool as module
            
            # Clear cache to force fresh check
            module._availability_cache = None
            
            importlib.reload(module)
            
            # which should not be called on import
            mock_which.assert_not_called()
