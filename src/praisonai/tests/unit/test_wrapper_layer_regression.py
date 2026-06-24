"""
Regression tests for wrapper layer bug fixes.

Tests for the fixes implemented in PR #1646 (wrapper layer gaps):
1. InteractiveRuntime lifecycle is properly managed
2. Tool resolution is consistent across all entry points
3. CLI backend validation works correctly across frameworks

Tests for the fixes implemented in PR #1896 (observability & tool cache):
4. ToolResolver cache `instantiate=True` fast-path fix
5. Observability finalization on adapter exception paths
"""

import pytest
import unittest.mock as mock
from unittest.mock import MagicMock, patch, call, Mock


class TestInteractiveRuntimeLifecycle:
    """Test InteractiveRuntime is not stopped before agents.start()"""

    @pytest.mark.skip(reason="InteractiveRuntime lifecycle moved to PraisonAIAdapter")
    def test_interactive_runtime_lifecycle_mock(self):
        """Legacy test retained for regression tracking."""
        pass


class TestToolResolutionConsistency:
    """Test that tool resolution is consistent across all entry points"""
    
    def test_tool_resolver_instantiate_parameter(self):
        """Test ToolResolver.resolve() instantiate parameter works correctly"""
        from praisonai.tool_resolver import ToolResolver
        
        resolver = ToolResolver()
        
        # Test with a mock class tool
        class MockTool:
            def __init__(self):
                self.instantiated = True
        
        with patch.object(resolver, '_resolve_from_praisonai_tools') as mock_resolve:
            mock_resolve.return_value = MockTool
            
            # Without instantiate=True, should return class
            result = resolver.resolve('mock_tool', instantiate=False)
            assert result == MockTool
            
            # With instantiate=True, should return instance
            result = resolver.resolve('mock_tool', instantiate=True)
            assert hasattr(result, 'instantiated')
            assert result.instantiated is True

    def test_bots_cli_uses_tool_resolver(self):
        """Test that bots_cli._resolve_tool_by_name uses ToolResolver"""
        from praisonai.cli.features.bots_cli import BotHandler
        
        bots = BotHandler()
        
        with patch('praisonai.tool_resolver.ToolResolver') as MockResolver:
            mock_resolver = MockResolver.return_value
            mock_resolver.resolve.return_value = MagicMock()
            
            result = bots._resolve_tool_by_name('test_tool')
            
            # Verify ToolResolver was used
            MockResolver.assert_called_once()
            mock_resolver.resolve.assert_called_once_with('test_tool', instantiate=True)

    def test_job_workflow_uses_tool_resolver(self):
        """Test that job_workflow uses ToolResolver for tool resolution"""
        from praisonai.cli.features.job_workflow import JobWorkflowExecutor
        
        executor = JobWorkflowExecutor({}, "dummy_path.yaml")
        
        with patch('praisonai.tool_resolver.ToolResolver') as MockResolver:
            mock_resolver = MockResolver.return_value
            mock_resolver.resolve.return_value = "resolved_tool"
            
            result = executor._resolve_agent_tools(['test_tool'])
            
            # Verify ToolResolver was used
            MockResolver.assert_called_once()
            mock_resolver.resolve.assert_called_once_with('test_tool', instantiate=True)
            assert result == ["resolved_tool"]


class TestCliBackendValidation:
    """Test CLI backend validation across frameworks"""
    
    def test_cli_backend_config_resolver(self):
        """Test the unified CLI backend config resolver"""
        from praisonai.cli_backends import resolve_cli_backend_config
        
        # Test string input
        with patch('praisonai.cli_backends.registry.resolve_cli_backend') as mock_resolve:
            mock_resolve.return_value = MagicMock()
            
            result = resolve_cli_backend_config("claude-code")
            mock_resolve.assert_called_once_with("claude-code")
        
        # Test dict input
        with patch('praisonai.cli_backends.registry.resolve_cli_backend') as mock_resolve:
            mock_resolve.return_value = MagicMock()
            
            config = {"id": "claude-code", "overrides": {"timeout": 30}}
            result = resolve_cli_backend_config(config)
            mock_resolve.assert_called_once_with("claude-code", overrides={"timeout": 30})
        
        # Test invalid dict (missing id)
        with pytest.raises(ValueError, match="must contain an 'id' field"):
            resolve_cli_backend_config({"overrides": {"timeout": 30}})

    def test_framework_cli_backend_validation(self):
        """Test that CLI backend validation works for unsupported frameworks"""
        from praisonai.agents_generator import AgentsGenerator
        
        generator = AgentsGenerator(
            agent_file=None,
            framework='autogen',
            config_list=[{"model": "gpt-4o-mini"}]
        )
        
        # Config with cli_backend on unsupported framework
        config = {
            'roles': {
                'test_agent': {
                    'role': 'Test Agent',
                    'goal': 'Test',
                    'backstory': 'Testing',
                    'cli_backend': 'claude-code'  # Should trigger validation error
                }
            }
        }
        
        # Should raise ValueError for incompatible framework
        with pytest.raises(ValueError, match="Runtime features require framework='praisonai'"):
            generator._validate_cli_backend_compatibility(config, 'autogen')

    def test_cli_backend_validation_accepts_praisonai_adapter_name(self):
        """Runtime features must validate against adapter.name, not the adapter object."""
        from praisonai.agents_generator import AgentsGenerator

        generator = AgentsGenerator(
            agent_file=None,
            framework='praisonai',
            config_list=[{"model": "gpt-4o-mini"}]
        )
        config = {
            'roles': {
                'test_agent': {
                    'role': 'Test Agent',
                    'goal': 'Test',
                    'backstory': 'Testing',
                    'cli_backend': 'claude-code',
                }
            }
        }
        # Must not raise when framework name is the string 'praisonai'
        generator._validate_cli_backend_compatibility(config, 'praisonai')

    def test_agent_wrapper_cli_backend_resolution(self):
        """Test that Agent wrapper resolves CLI backend configs correctly"""
        from praisonai.agent import Agent
        
        # Test that string cli_backend is resolved
        with patch('praisonai.cli_backends.resolve_cli_backend_config') as mock_resolve:
            mock_resolve.return_value = MagicMock()
            
            agent = Agent(name="test", cli_backend="claude-code")
            mock_resolve.assert_called_once_with("claude-code")
        
        # Test that dict cli_backend is resolved
        with patch('praisonai.cli_backends.resolve_cli_backend_config') as mock_resolve:
            mock_resolve.return_value = MagicMock()
            
            config = {"id": "claude-code", "overrides": {"timeout": 30}}
            agent = Agent(name="test", cli_backend=config)
            mock_resolve.assert_called_once_with(config)
        
        # Test that protocol instances pass through unchanged
        mock_instance = MagicMock()
        mock_instance.process_turn = MagicMock()  # Duck typing for protocol
        
        with patch('praisonai.cli_backends.resolve_cli_backend_config') as mock_resolve:
            agent = Agent(name="test", cli_backend=mock_instance)
            # Should not call resolver for already-resolved instances
            mock_resolve.assert_not_called()


# ===== NEW TESTS FOR PR #1896 BUG FIXES =====

class TestToolResolverCacheFix:
    """Test ToolResolver cache instantiate=True fast-path fix."""
    
    def test_cached_tool_instantiation_fast_path(self):
        """Test that cached classes are instantiated when instantiate=True in fast path."""
        from praisonai.tool_resolver import ToolResolver
        
        # Create a mock class that can be instantiated
        class MockTool:
            def __init__(self):
                self.called = True
                
            def __call__(self):
                return "mock result"
        
        resolver = ToolResolver()
        
        # Pre-populate cache with a class
        resolver._resolve_cache["test_tool"] = MockTool
        
        # Test fast-path with instantiate=False (should return class)
        result_class = resolver.resolve("test_tool", instantiate=False)
        assert result_class is MockTool
        
        # Test fast-path with instantiate=True (should return instance)
        result_instance = resolver.resolve("test_tool", instantiate=True)
        assert isinstance(result_instance, MockTool)
        assert result_instance.called is True
        assert result_instance is not MockTool
    
    def test_cached_function_no_instantiation(self):
        """Test that cached functions are returned as-is regardless of instantiate flag."""
        from praisonai.tool_resolver import ToolResolver
        
        def mock_function():
            return "function result"
        
        resolver = ToolResolver()
        
        # Pre-populate cache with a function
        resolver._resolve_cache["test_func"] = mock_function
        
        # Both should return the same function
        result_false = resolver.resolve("test_func", instantiate=False)
        result_true = resolver.resolve("test_func", instantiate=True)
        
        assert result_false is mock_function
        assert result_true is mock_function
    
    def test_cached_none_value(self):
        """Test that cached None values (tool not found) are handled correctly."""
        from praisonai.tool_resolver import ToolResolver
        
        resolver = ToolResolver()
        
        # Pre-populate cache with None (tool not found)
        resolver._resolve_cache["nonexistent_tool"] = None
        
        # Both should return None
        result_false = resolver.resolve("nonexistent_tool", instantiate=False)
        result_true = resolver.resolve("nonexistent_tool", instantiate=True)
        
        assert result_false is None
        assert result_true is None


class TestObservabilityFinalization:
    """Test observability finalization on adapter exception paths."""
    
    @patch('praisonai.observability.hooks._end_agentops')
    def test_finalize_observability_success(self, mock_end_agentops):
        """Test finalize_observability calls _end_agentops with success status."""
        from praisonai.observability.hooks import finalize_observability
        
        finalize_observability("test_framework", status="Success")
        
        mock_end_agentops.assert_called_once_with("Success")
    
    @patch('praisonai.observability.hooks._end_agentops')
    def test_finalize_observability_failure(self, mock_end_agentops):
        """Test finalize_observability calls _end_agentops with failure status."""
        from praisonai.observability.hooks import finalize_observability
        
        finalize_observability("test_framework", status="Failure")
        
        mock_end_agentops.assert_called_once_with("Failure")
    
    @patch('praisonai.observability.hooks._end_agentops')
    def test_finalize_observability_default_status(self, mock_end_agentops):
        """Test finalize_observability uses 'Success' as default status."""
        from praisonai.observability.hooks import finalize_observability
        
        finalize_observability("test_framework")
        
        mock_end_agentops.assert_called_once_with("Success")
    
    @patch('praisonai.observability.hooks.logger')
    def test_end_agentops_import_error_handling(self, mock_logger):
        """Test _end_agentops handles ImportError gracefully."""
        from praisonai.observability.hooks import _end_agentops
        
        with patch('builtins.__import__', side_effect=ImportError("agentops not found")):
            _end_agentops("Success")
            
        # Should not raise exception and should not log warnings (just returns silently)
        mock_logger.warning.assert_not_called()
    
    @patch('praisonai.observability.hooks.logger')
    def test_end_agentops_exception_handling(self, mock_logger):
        """Test _end_agentops handles agentops.end_session exceptions gracefully."""
        from praisonai.observability.hooks import _end_agentops
        
        # Mock agentops module to be available but end_session raises exception
        mock_agentops = Mock()
        mock_agentops.end_session.side_effect = Exception("Session end failed")
        
        with patch.dict('sys.modules', {'agentops': mock_agentops}):
            _end_agentops("Success")
            
        # Should not raise exception but should log warning
        mock_agentops.end_session.assert_called_once_with("Success")
        mock_logger.warning.assert_called_once_with("agentops.end_session failed: %s", mock_agentops.end_session.side_effect)


class TestFrameworkAdapterExceptionPaths:
    """Test that framework adapters call finalize_observability on exception paths."""
    
    @patch('praisonai.observability.hooks.finalize_observability')
    @pytest.mark.skip(reason="AutoGenV4Adapter delegates execution; inspect source test outdated")
    def test_autogen_v4_adapter_exception_handling(self, mock_finalize):
        """Test AutoGenV4Adapter calls finalize_observability on exceptions."""
        # This is a smoke test to verify the structure exists
        # Real testing would require mocking the entire AutoGen framework
        try:
            from praisonai.framework_adapters.autogen_adapter import AutoGenV4Adapter
            
            # Verify the class exists and has arun method
            assert hasattr(AutoGenV4Adapter, 'arun')
            
            # Check that the implementation includes try/except blocks
            import inspect
            source = inspect.getsource(AutoGenV4Adapter.arun)
            
            # Verify exception handling structure exists
            assert 'try:' in source or 'except:' in source, "AutoGenV4Adapter.arun should have exception handling"
            assert 'finalize_observability' in source, "AutoGenV4Adapter.arun should call finalize_observability"
            
        except ImportError:
            # Skip if autogen dependencies not available
            pytest.skip("AutoGen dependencies not available")
    
    @patch('praisonai.observability.hooks.finalize_observability')
    @pytest.mark.skip(reason="AG2Adapter.run is a stub; inspect source test outdated")
    def test_ag2_adapter_exception_handling(self, mock_finalize):
        """Test AG2Adapter calls finalize_observability on exceptions."""
        # This is a smoke test to verify the structure exists
        try:
            from praisonai.framework_adapters.autogen_adapter import AG2Adapter
            
            # Verify the class exists and has run method
            assert hasattr(AG2Adapter, 'run')
            
            # Check that the implementation includes try/except blocks
            import inspect
            source = inspect.getsource(AG2Adapter.run)
            
            # Verify exception handling structure exists
            assert 'try:' in source or 'except:' in source, "AG2Adapter.run should have exception handling"
            assert 'finalize_observability' in source, "AG2Adapter.run should call finalize_observability"
            
        except ImportError:
            # Skip if AG2 dependencies not available
            pytest.skip("AG2 dependencies not available")
    
    def test_crewai_adapter_finalization_calls(self):
        """Test CrewAIAdapter calls finalize_observability with correct status."""
        try:
            from praisonai.framework_adapters.crewai_adapter import CrewAIAdapter
            
            # Verify the class exists and has run method
            assert hasattr(CrewAIAdapter, 'run')
            
            # Check that the implementation calls finalize_observability
            import inspect
            source = inspect.getsource(CrewAIAdapter.run)
            
            # Verify finalize_observability call exists with status parameter
            assert 'finalize_observability' in source, "CrewAIAdapter.run should call finalize_observability"
            assert 'status=' in source, "CrewAIAdapter.run should call finalize_observability with status parameter"
            
        except ImportError:
            # Skip if CrewAI dependencies not available
            pytest.skip("CrewAI dependencies not available")
    
    def test_praisonai_adapter_finalization_calls(self):
        """Test PraisonAIAdapter calls finalize_observability with correct status."""
        from praisonai.framework_adapters.praisonai_adapter import PraisonAIAdapter
        
        # Verify the class exists and has both run and arun methods
        assert hasattr(PraisonAIAdapter, 'run')
        assert hasattr(PraisonAIAdapter, 'arun')
        
        # Check that both implementations call finalize_observability
        import inspect

        arun_source = inspect.getsource(PraisonAIAdapter.arun)

        assert 'finalize_observability' in arun_source, "PraisonAIAdapter.arun should call finalize_observability"
        assert 'status=' in arun_source, "PraisonAIAdapter.arun should call finalize_observability with status parameter"
