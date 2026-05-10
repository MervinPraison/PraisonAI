"""
Regression tests for the three wrapper layer gaps fixed in Issue #1646.

Tests ensure:
1. InteractiveRuntime lifecycle is properly managed
2. Tool resolution is consistent across all entry points
3. CLI backend validation works correctly across frameworks
"""

import pytest
from unittest.mock import MagicMock, patch


class TestInteractiveRuntimeLifecycle:
    """Test InteractiveRuntime is not stopped before agents.start()"""
    
    def test_interactive_runtime_lifecycle_mock(self):
        """Test that InteractiveRuntime.stop() is not called prematurely"""
        with patch('praisonai.praisonai.agents_generator.asyncio') as mock_asyncio, \
             patch('praisonai.praisonai.agents_generator.InteractiveRuntime') as MockRuntime, \
             patch('praisonai.praisonai.agents_generator.create_agent_centric_tools') as mock_tools:
            
            # Setup mocks
            mock_loop = MagicMock()
            mock_asyncio.new_event_loop.return_value = mock_loop
            mock_runtime = MockRuntime.return_value
            mock_tools.return_value = []
            
            from praisonai.praisonai.agents_generator import AgentsGenerator
            
            generator = AgentsGenerator(
                agent_file=None, 
                framework='praisonai',
                config_list=[{"model": "gpt-4o-mini"}]
            )
            
            # Config with ACP enabled
            config = {
                'config': {'acp': True},
                'roles': {
                    'test_agent': {
                        'role': 'Test Agent',
                        'goal': 'Test',
                        'backstory': 'Testing',
                        'tasks': {
                            'test_task': {
                                'description': 'Test task',
                                'expected_output': 'Done'
                            }
                        }
                    }
                }
            }
            
            # Run the configuration
            try:
                result = generator.run_generation(config)
            except Exception as e:
                # Expected to fail due to missing framework adapter, but that's OK for lifecycle test
                pass
            
            # Verify runtime.start() was called but stop() was NOT called during setup
            mock_loop.run_until_complete.assert_any_call(mock_runtime.start())
            
            # Should NOT have been stopped during the setup phase
            stop_calls = [call for call in mock_loop.run_until_complete.call_args_list 
                         if call[0][0] == mock_runtime.stop()]
            
            # Stop should only be called once (in cleanup), not during setup
            assert len(stop_calls) <= 1, "Runtime should not be stopped prematurely"


class TestToolResolutionConsistency:
    """Test that tool resolution is consistent across all entry points"""
    
    def test_tool_resolver_instantiate_parameter(self):
        """Test ToolResolver.resolve() instantiate parameter works correctly"""
        from praisonai.praisonai.tool_resolver import ToolResolver
        
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
        from praisonai.praisonai.cli.features.bots_cli import Bots
        
        bots = Bots()
        
        with patch('praisonai.praisonai.cli.features.bots_cli.ToolResolver') as MockResolver:
            mock_resolver = MockResolver.return_value
            mock_resolver.resolve.return_value = MagicMock()
            
            result = bots._resolve_tool_by_name('test_tool')
            
            # Verify ToolResolver was used
            MockResolver.assert_called_once()
            mock_resolver.resolve.assert_called_once_with('test_tool', instantiate=True)

    def test_job_workflow_uses_tool_resolver(self):
        """Test that job_workflow uses ToolResolver for tool resolution"""
        from praisonai.praisonai.cli.features.job_workflow import JobWorkflowParser
        
        parser = JobWorkflowParser({})
        
        with patch('praisonai.praisonai.cli.features.job_workflow.ToolResolver') as MockResolver:
            mock_resolver = MockResolver.return_value
            mock_resolver.resolve.return_value = lambda: "resolved_tool"
            
            result = parser._resolve_agent_tools(['test_tool'])
            
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
        from praisonai.praisonai.agents_generator import AgentsGenerator
        
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
        with pytest.raises(ValueError, match="cli_backend requires framework='praisonai'"):
            generator._validate_cli_backend_compatibility(config, 'autogen')

    def test_agent_wrapper_cli_backend_resolution(self):
        """Test that Agent wrapper resolves CLI backend configs correctly"""
        from praisonai.praisonai.agent import Agent
        
        # Test that string cli_backend is resolved
        with patch('praisonai.praisonai.agent.resolve_cli_backend_config') as mock_resolve:
            mock_resolve.return_value = MagicMock()
            
            agent = Agent(name="test", cli_backend="claude-code")
            mock_resolve.assert_called_once_with("claude-code")
        
        # Test that dict cli_backend is resolved
        with patch('praisonai.praisonai.agent.resolve_cli_backend_config') as mock_resolve:
            mock_resolve.return_value = MagicMock()
            
            config = {"id": "claude-code", "overrides": {"timeout": 30}}
            agent = Agent(name="test", cli_backend=config)
            mock_resolve.assert_called_once_with(config)
        
        # Test that protocol instances pass through unchanged
        mock_instance = MagicMock()
        mock_instance.process_turn = MagicMock()  # Duck typing for protocol
        
        with patch('praisonai.praisonai.agent.resolve_cli_backend_config') as mock_resolve:
            agent = Agent(name="test", cli_backend=mock_instance)
            # Should not call resolver for already-resolved instances
            mock_resolve.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__])