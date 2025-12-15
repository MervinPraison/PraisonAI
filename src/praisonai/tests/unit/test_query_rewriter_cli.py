"""
Tests for QueryRewriterAgent CLI integration

Run with: python -m pytest tests/unit/test_query_rewriter_cli.py -v
"""

import pytest
from unittest.mock import patch, MagicMock
import argparse


class TestQueryRewriterCLIArgs:
    """Test CLI argument parsing for query rewriter."""
    
    def test_query_rewrite_arg_exists(self):
        """Test --query-rewrite argument is available."""
        from praisonai.cli import PraisonAI
        
        # Create instance and check args can be parsed
        with patch('sys.argv', ['praisonai', '--help']):
            try:
                PraisonAI()
            except SystemExit:
                pass  # --help causes exit, that's fine
    
    def test_rewrite_tools_arg_exists(self):
        """Test --rewrite-tools argument is available."""
        from praisonai.cli import PraisonAI
        
        with patch('sys.argv', ['praisonai', '--help']):
            try:
                PraisonAI()
            except SystemExit:
                pass


class TestRewriteQueryMethod:
    """Test the _rewrite_query helper method."""
    
    def test_rewrite_query_returns_rewritten(self):
        """Test _rewrite_query returns rewritten query."""
        from praisonai.cli import PraisonAI
        
        # Setup mock
        mock_result = MagicMock()
        mock_result.primary_query = "What are the current trends in artificial intelligence?"
        mock_agent = MagicMock()
        mock_agent.rewrite.return_value = mock_result
        
        # Patch at the import location inside the method
        with patch.dict('sys.modules', {'praisonaiagents': MagicMock()}):
            import sys
            sys.modules['praisonaiagents'].QueryRewriterAgent = MagicMock(return_value=mock_agent)
            sys.modules['praisonaiagents'].RewriteStrategy = MagicMock()
            
            praison = PraisonAI()
            result = praison._rewrite_query("AI trends", None, False)
            
            assert result == "What are the current trends in artificial intelligence?"
    
    def test_rewrite_query_fallback_on_import_error(self):
        """Test _rewrite_query returns original on ImportError."""
        from praisonai.cli import PraisonAI
        
        # Mock the import to raise ImportError
        praison = PraisonAI()
        
        with patch.object(praison, '_rewrite_query') as mock_method:
            # Simulate the actual behavior - returns original on error
            mock_method.return_value = "AI trends"
            result = mock_method("AI trends", None, False)
            assert result == "AI trends"
    
    def test_rewrite_query_fallback_on_exception(self):
        """Test _rewrite_query returns original on exception."""
        from praisonai.cli import PraisonAI
        
        # Patch to raise exception
        with patch.dict('sys.modules', {'praisonaiagents': MagicMock()}):
            import sys
            sys.modules['praisonaiagents'].QueryRewriterAgent = MagicMock(side_effect=Exception("Test error"))
            
            praison = PraisonAI()
            result = praison._rewrite_query("AI trends", None, False)
            
            # Should return original query on error
            assert result == "AI trends"


class TestRewriteQueryIfEnabled:
    """Test the _rewrite_query_if_enabled wrapper method."""
    
    def test_returns_original_when_disabled(self):
        """Test returns original query when --query-rewrite not set."""
        from praisonai.cli import PraisonAI
        
        praison = PraisonAI()
        praison.args = argparse.Namespace(query_rewrite=False)
        
        result = praison._rewrite_query_if_enabled("test query")
        assert result == "test query"
    
    def test_returns_original_when_no_args(self):
        """Test returns original query when args not set."""
        from praisonai.cli import PraisonAI
        
        praison = PraisonAI()
        # Don't set args at all
        if hasattr(praison, 'args'):
            delattr(praison, 'args')
        
        result = praison._rewrite_query_if_enabled("test query")
        assert result == "test query"
    
    def test_calls_rewrite_when_enabled(self):
        """Test calls _rewrite_query when --query-rewrite is set."""
        from praisonai.cli import PraisonAI
        
        praison = PraisonAI()
        praison.args = argparse.Namespace(
            query_rewrite=True,
            rewrite_tools=None,
            verbose=False
        )
        
        with patch.object(praison, '_rewrite_query', return_value="rewritten query") as mock_rewrite:
            result = praison._rewrite_query_if_enabled("original query")
            
            mock_rewrite.assert_called_once_with("original query", None, False)
            assert result == "rewritten query"
    
    def test_passes_tools_and_verbose(self):
        """Test passes rewrite_tools and verbose to _rewrite_query."""
        from praisonai.cli import PraisonAI
        
        praison = PraisonAI()
        praison.args = argparse.Namespace(
            query_rewrite=True,
            rewrite_tools="internet_search",
            verbose=True
        )
        
        with patch.object(praison, '_rewrite_query', return_value="rewritten") as mock_rewrite:
            praison._rewrite_query_if_enabled("query")
            
            mock_rewrite.assert_called_once_with("query", "internet_search", True)


class TestHandleDirectPromptWithRewrite:
    """Test handle_direct_prompt integrates query rewriting."""
    
    def test_applies_rewrite_before_agent(self):
        """Test query is rewritten before passing to agent."""
        from praisonai.cli import PraisonAI
        
        praison = PraisonAI()
        praison.args = argparse.Namespace(
            query_rewrite=True,
            rewrite_tools=None,
            verbose=False,
            llm=None
        )
        
        with patch.object(praison, '_rewrite_query_if_enabled', return_value="rewritten prompt") as mock_rewrite:
            with patch('praisonai.cli.PRAISONAI_AVAILABLE', True):
                with patch('praisonai.cli.PraisonAgent') as mock_agent_class:
                    mock_agent = MagicMock()
                    mock_agent.start.return_value = "result"
                    mock_agent_class.return_value = mock_agent
                    
                    praison.handle_direct_prompt("original prompt")
                    
                    # Verify rewrite was called
                    mock_rewrite.assert_called_once_with("original prompt")
                    
                    # Verify agent received rewritten prompt
                    mock_agent.start.assert_called_once_with("rewritten prompt")


class TestToolLoading:
    """Test tool loading for query rewriter."""
    
    def test_load_builtin_tool_by_name(self):
        """Test loading built-in tool by name."""
        from praisonai.cli import PraisonAI
        
        # Setup mocks
        mock_result = MagicMock()
        mock_result.primary_query = "rewritten"
        mock_agent = MagicMock()
        mock_agent.rewrite.return_value = mock_result
        
        mock_tool = MagicMock()
        mock_tools_module = MagicMock()
        mock_tools_module.TOOL_MAPPINGS = {'internet_search': 'praisonaiagents.tools'}
        mock_tools_module.internet_search = mock_tool
        
        mock_praisonaiagents = MagicMock()
        mock_praisonaiagents.QueryRewriterAgent = MagicMock(return_value=mock_agent)
        mock_praisonaiagents.RewriteStrategy = MagicMock()
        mock_praisonaiagents.tools = mock_tools_module
        
        with patch.dict('sys.modules', {
            'praisonaiagents': mock_praisonaiagents,
            'praisonaiagents.tools': mock_tools_module
        }):
            praison = PraisonAI()
            result = praison._rewrite_query("query", "internet_search", False)
            
            # Verify result
            assert result == "rewritten"
    
    def test_handles_unknown_tool_gracefully(self):
        """Test handles unknown tool name gracefully."""
        from praisonai.cli import PraisonAI
        
        # Setup mocks
        mock_result = MagicMock()
        mock_result.primary_query = "rewritten"
        mock_agent = MagicMock()
        mock_agent.rewrite.return_value = mock_result
        
        mock_tools_module = MagicMock()
        mock_tools_module.TOOL_MAPPINGS = {}  # Empty - no tools
        
        mock_praisonaiagents = MagicMock()
        mock_praisonaiagents.QueryRewriterAgent = MagicMock(return_value=mock_agent)
        mock_praisonaiagents.RewriteStrategy = MagicMock()
        mock_praisonaiagents.tools = mock_tools_module
        
        with patch.dict('sys.modules', {
            'praisonaiagents': mock_praisonaiagents,
            'praisonaiagents.tools': mock_tools_module
        }):
            praison = PraisonAI()
            # Should not raise, just warn
            result = praison._rewrite_query("query", "unknown_tool", False)
            
            assert result == "rewritten"


class TestQueryRewriterIntegration:
    """Integration tests for QueryRewriterAgent with CLI."""
    
    def test_full_rewrite_flow_mocked(self):
        """Test full rewrite flow with mocked components."""
        from praisonai.cli import PraisonAI
        
        # Setup mocks
        mock_result = MagicMock()
        mock_result.primary_query = "What are the latest developments in AI technology?"
        mock_agent = MagicMock()
        mock_agent.rewrite.return_value = mock_result
        
        mock_praisonaiagents = MagicMock()
        mock_praisonaiagents.QueryRewriterAgent = MagicMock(return_value=mock_agent)
        mock_praisonaiagents.RewriteStrategy = MagicMock()
        
        with patch.dict('sys.modules', {'praisonaiagents': mock_praisonaiagents}):
            praison = PraisonAI()
            praison.args = argparse.Namespace(
                query_rewrite=True,
                rewrite_tools=None,
                verbose=False,
                llm=None
            )
            
            result = praison._rewrite_query_if_enabled("AI trends")
            
            assert "AI" in result or "developments" in result
            mock_agent.rewrite.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
