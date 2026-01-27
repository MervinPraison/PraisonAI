"""Tests for tool reliability improvements.

TDD tests for:
1. list_processes NoneType bug fix
2. internet_search retry logic
3. search_web reliability
"""

from unittest.mock import patch, MagicMock


class TestListProcessesReliability:
    """Tests for list_processes NoneType bug fix."""
    
    def test_list_processes_handles_none_memory_percent(self):
        """list_processes should handle None memory_percent gracefully."""
        from praisonaiagents.tools.shell_tools import ShellTools
        
        # Mock psutil.process_iter to return a process with None memory_percent
        mock_proc = MagicMock()
        mock_proc.info = {
            'pid': 1234,
            'name': 'test_process',
            'username': 'test_user',
            'memory_percent': None,  # This is the bug trigger
            'cpu_percent': 5.0
        }
        
        with patch('praisonaiagents.tools.shell_tools.psutil.process_iter', return_value=[mock_proc]):
            shell = ShellTools()
            result = shell.list_processes()
            
            # Should not raise TypeError
            assert isinstance(result, list)
            assert len(result) == 1
            assert result[0]['pid'] == 1234
            assert result[0]['memory_percent'] == 0.0  # Should default to 0.0
    
    def test_list_processes_handles_none_cpu_percent(self):
        """list_processes should handle None cpu_percent gracefully."""
        from praisonaiagents.tools.shell_tools import ShellTools
        
        mock_proc = MagicMock()
        mock_proc.info = {
            'pid': 5678,
            'name': 'another_process',
            'username': 'user',
            'memory_percent': 10.5,
            'cpu_percent': None  # This is the bug trigger
        }
        
        with patch('praisonaiagents.tools.shell_tools.psutil.process_iter', return_value=[mock_proc]):
            shell = ShellTools()
            result = shell.list_processes()
            
            assert isinstance(result, list)
            assert len(result) == 1
            assert result[0]['cpu_percent'] == 0.0  # Should default to 0.0
    
    def test_list_processes_handles_both_none(self):
        """list_processes should handle both None values gracefully."""
        from praisonaiagents.tools.shell_tools import ShellTools
        
        mock_proc = MagicMock()
        mock_proc.info = {
            'pid': 9999,
            'name': 'zombie_process',
            'username': None,
            'memory_percent': None,
            'cpu_percent': None
        }
        
        with patch('praisonaiagents.tools.shell_tools.psutil.process_iter', return_value=[mock_proc]):
            shell = ShellTools()
            result = shell.list_processes()
            
            assert isinstance(result, list)
            assert len(result) == 1
            assert result[0]['memory_percent'] == 0.0
            assert result[0]['cpu_percent'] == 0.0
            assert result[0]['username'] is None  # username can be None


class TestInternetSearchReliability:
    """Tests for internet_search retry logic."""
    
    def test_internet_search_has_retry_parameter(self):
        """internet_search should accept retries parameter."""
        from praisonaiagents.tools.duckduckgo_tools import internet_search
        import inspect
        
        sig = inspect.signature(internet_search)
        params = list(sig.parameters.keys())
        
        assert 'retries' in params, "internet_search should have 'retries' parameter"
        assert 'max_results' in params, "internet_search should have 'max_results' parameter"
    
    def test_internet_search_returns_list(self):
        """internet_search should always return a list."""
        from praisonaiagents.tools import internet_search
        
        # Even with minimal retries, should return a list
        results = internet_search("test query", retries=1)
        assert isinstance(results, list)
    
    def test_internet_search_handles_missing_package(self):
        """internet_search should handle missing duckduckgo_search package."""
        from praisonaiagents.tools.duckduckgo_tools import internet_search
        
        # Mock find_spec to return None (package not installed)
        with patch('praisonaiagents.tools.duckduckgo_tools.util.find_spec', return_value=None):
            results = internet_search("test query")
            
            assert isinstance(results, list)
            assert len(results) == 1
            assert 'error' in results[0]


class TestSearchWebReliability:
    """Tests for search_web reliability improvements."""
    
    def test_search_web_tries_multiple_providers(self):
        """search_web should try multiple providers on failure."""
        from praisonaiagents.tools import search_web
        
        # This test verifies the fallback mechanism works
        with patch.dict('os.environ', {'TAVILY_API_KEY': ''}):
            # Without API keys, should fall back to DuckDuckGo
            results = search_web("test query", providers=["duckduckgo"])
            assert isinstance(results, list)
    
    def test_search_web_has_retry_in_duckduckgo(self):
        """search_web's DuckDuckGo provider should have retry logic."""
        from praisonaiagents.tools.web_search import _search_duckduckgo
        import inspect
        
        # Check that the function has retry logic by inspecting source
        source = inspect.getsource(_search_duckduckgo)
        assert 'max_retries' in source, "_search_duckduckgo should have retry logic"
        assert 'retry_delay' in source, "_search_duckduckgo should have retry delay"


class TestToolErrorConsistency:
    """Tests for consistent error handling across tools."""
    
    def test_internet_search_error_format_missing_package(self):
        """internet_search errors should have consistent format."""
        from praisonaiagents.tools.duckduckgo_tools import internet_search
        
        # Mock find_spec to simulate missing package
        with patch('praisonaiagents.tools.duckduckgo_tools.util.find_spec', return_value=None):
            results = internet_search("test")
            
            assert isinstance(results, list)
            assert len(results) == 1
            assert 'error' in results[0]
    
    def test_search_web_error_format(self):
        """search_web errors should have consistent format when all providers fail."""
        from praisonaiagents.tools.web_search import search_web
        
        # Force all providers to fail by patching SEARCH_PROVIDERS to empty
        with patch('praisonaiagents.tools.web_search.SEARCH_PROVIDERS', []):
            results = search_web("test")
            
            assert isinstance(results, list)
            assert len(results) == 1
            assert 'error' in results[0]
            assert 'No search providers available' in results[0]['error']
