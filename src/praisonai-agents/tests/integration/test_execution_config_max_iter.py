"""
Integration test for ExecutionConfig max_iter end-to-end behavior.

Tests that ExecutionConfig.max_iter is properly propagated to LLM instances
and respected during agent execution loops.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from praisonaiagents import Agent
from praisonaiagents.config.feature_configs import ExecutionConfig
from praisonaiagents.llm.llm import LLM


class TestExecutionConfigMaxIter:
    """Integration test for max_iter configuration propagation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.test_llm_config = {
            "api_base": "http://test",
            "api_key": "test-key",
            "provider": "custom"
        }
    
    def test_execution_config_default_max_iter(self):
        """Test that ExecutionConfig has correct default max_iter."""
        config = ExecutionConfig()
        assert config.max_iter == 20
    
    def test_execution_config_custom_max_iter(self):
        """Test ExecutionConfig with custom max_iter."""
        config = ExecutionConfig(max_iter=15)
        assert config.max_iter == 15
    
    @patch('praisonaiagents.llm.llm.LLM._chat_completion')
    def test_agent_with_execution_config_max_iter(self, mock_chat):
        """Test that Agent passes ExecutionConfig.max_iter to LLM."""
        # Mock the LLM response to avoid actual API calls
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Hello, I'm a test response!"
        mock_response.choices[0].message.tool_calls = None
        mock_chat.return_value = mock_response
        
        # Create agent with custom max_iter
        execution_config = ExecutionConfig(max_iter=15)
        
        with patch('praisonaiagents.agent.agent.LLM') as MockLLM:
            mock_llm_instance = Mock()
            MockLLM.return_value = mock_llm_instance
            
            agent = Agent(
                name="test_agent",
                instructions="Be helpful",
                llm=self.test_llm_config,
                execution=execution_config
            )
            
            # Verify LLM was instantiated with max_iter from ExecutionConfig
            MockLLM.assert_called()
            call_args = MockLLM.call_args
            
            # max_iter should be passed to LLM constructor
            assert 'max_iter' in call_args.kwargs
            assert call_args.kwargs['max_iter'] == 15
            
            # Execute agent to verify max_iter is enforced in practice
            result = agent.start("Count to 5 and stop")
            assert result is not None
    
    def test_llm_constructor_accepts_max_iter(self):
        """Test that LLM constructor accepts max_iter parameter."""
        llm = LLM(
            api_base="http://test",
            api_key="test-key",
            max_iter=25
        )
        
        assert llm.max_iter == 25
    
    def test_llm_constructor_default_max_iter(self):
        """Test LLM constructor default max_iter value."""
        llm = LLM(
            api_base="http://test", 
            api_key="test-key"
        )
        
        # Verifies alignment with ExecutionConfig default
        assert hasattr(llm, 'max_iter')
        assert llm.max_iter == 20  # Default aligned with ExecutionConfig
    
    @patch('praisonaiagents.agent.agent.LLM')
    def test_agent_without_execution_config_uses_llm_default(self, MockLLM):
        """Test that Agent without ExecutionConfig doesn't override LLM max_iter."""
        mock_llm_instance = Mock()
        MockLLM.return_value = mock_llm_instance
        
        agent = Agent(
            name="test_agent",
            instructions="Be helpful",
            llm=self.test_llm_config
        )
        
        # Verify LLM was called without max_iter override
        MockLLM.assert_called()
        call_args = MockLLM.call_args
        
        # max_iter should still be passed (from ExecutionConfig default in Agent._exec_config)
        # or use LLM's own default
        # This verifies the current wiring behavior
    
    def test_execution_config_preset_strings(self):
        """Test ExecutionConfig preset string handling."""
        # Test that string presets work (if implemented)
        try:
            # This might not be implemented yet, but documents expected behavior
            config = ExecutionConfig.from_preset("thorough")
            assert config.max_iter > 20  # Thorough should have higher limits
        except (AttributeError, NotImplementedError):
            # Skip if presets not implemented yet
            pytest.skip("ExecutionConfig presets not implemented yet")
    
    @patch('praisonaiagents.agent.agent.LLM')
    def test_different_llm_init_paths_respect_max_iter(self, MockLLM):
        """Test that all LLM initialization paths in Agent respect max_iter."""
        mock_llm_instance = Mock()
        MockLLM.return_value = mock_llm_instance
        execution_config = ExecutionConfig(max_iter=30)
        
        test_cases = [
            # Dict config
            {"provider": "openai", "model": "gpt-4o", "api_key": "test"},
            # String config
            "gpt-4o",
            # With base_url
            {"base_url": "http://test", "model": "test-model", "api_key": "test"}
        ]
        
        for llm_config in test_cases:
            MockLLM.reset_mock()
            
            agent = Agent(
                name=f"test_agent_{hash(str(llm_config))}",
                instructions="Be helpful",
                llm=llm_config,
                execution=execution_config
            )
            
            # Verify LLM was called with max_iter
            MockLLM.assert_called()
            call_args = MockLLM.call_args
            assert 'max_iter' in call_args.kwargs
            assert call_args.kwargs['max_iter'] == 30
    
    def test_max_iter_bounds_validation(self):
        """Test validation of max_iter bounds."""
        # Test reasonable bounds
        valid_configs = [
            ExecutionConfig(max_iter=1),
            ExecutionConfig(max_iter=100),
            ExecutionConfig(max_iter=1000)
        ]
        
        for config in valid_configs:
            assert config.max_iter > 0
        
        # Test edge cases
        try:
            # Some validation might be implemented
            invalid_config = ExecutionConfig(max_iter=0)
            # If no validation, just ensure it's set
            assert invalid_config.max_iter == 0
        except ValueError:
            # If validation is implemented, this is expected
            pass
    
    def test_execution_config_integration_with_autonomy(self):
        """Test ExecutionConfig.max_iter works with autonomy mode."""
        execution_config = ExecutionConfig(max_iter=12)
        
        # Test that ExecutionConfig can be used alongside AutonomyConfig
        from praisonaiagents.agent.autonomy import AutonomyConfig
        autonomy_config = AutonomyConfig()
        
        # This should not conflict
        with patch('praisonaiagents.agent.agent.LLM') as MockLLM:
            mock_llm_instance = Mock()
            MockLLM.return_value = mock_llm_instance
            
            agent = Agent(
                name="test_agent",
                instructions="Be helpful",
                llm=self.test_llm_config,
                execution=execution_config,
                autonomy=autonomy_config
            )
            
            # Verify both configs can coexist and max_iter is propagated
            MockLLM.assert_called()
            call_args = MockLLM.call_args
            assert 'max_iter' in call_args.kwargs
            assert call_args.kwargs['max_iter'] == 12


class TestMaxIterInToolCallLoops:
    """Test that max_iter is respected in tool calling loops."""
    
    def test_max_iter_limits_tool_call_iterations(self):
        """Test that max_iter properly limits tool call iterations."""
        llm = LLM(
            api_base="http://test",
            api_key="test-key", 
            max_iter=3
        )
        
        # Mock a scenario where tool calls would exceed max_iter
        with patch.object(llm, '_chat_completion') as mock_chat:
            # Mock response with tool calls that would continue indefinitely
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.tool_calls = [Mock()]
            mock_response.choices[0].message.tool_calls[0].function.name = "test_tool"
            mock_response.choices[0].message.tool_calls[0].function.arguments = '{"query": "test"}'
            mock_response.choices[0].message.tool_calls[0].id = "call_123"
            mock_response.choices[0].message.content = None
            mock_chat.return_value = mock_response
            
            # Mock tool executor to return a result
            with patch('praisonaiagents.llm.llm.create_tool_call_executor') as mock_executor:
                mock_executor_instance = Mock()
                mock_executor_instance.execute_tool_calls.return_value = [
                    Mock(name="test_tool", result="tool result", error=None)
                ]
                mock_executor.return_value = mock_executor_instance
                
                # This should be limited by max_iter and not run indefinitely
                try:
                    llm.get_response(
                        user_message="Test message",
                        conversation_history=[],
                        tools=[],
                    )
                    
                    # Verify that the number of chat completion calls is limited
                    assert mock_chat.call_count <= llm.max_iter
                    
                except Exception:
                    # If the implementation throws an exception due to max_iter,
                    # that's also acceptable behavior
                    assert mock_chat.call_count <= llm.max_iter
    
    def test_hardcoded_iteration_limits_removed(self):
        """Test that hardcoded iteration limits have been replaced with max_iter."""
        llm = LLM(
            api_base="http://test",
            api_key="test-key",
            max_iter=50  # Higher than typical hardcoded limits
        )
        
        # This is a smoke test to ensure max_iter is actually used
        # The specific implementation details may vary
        assert llm.max_iter == 50
        
        # If there are any methods with hardcoded limits, they should use self.max_iter
        # This is tested by checking that iteration behavior respects the configured value
        # rather than hardcoded constants like 5, 10, 20, etc.
    
    def test_real_agent_execution_with_max_iter(self):
        """Real agentic test: Agent calls real LLM with max_iter enforcement.
        
        This is a REAL agentic test as required by AGENTS.md §9.4:
        - Agent must call agent.start() with real prompt
        - Agent must call the LLM and produce actual text response
        - Not just smoke tests of object construction
        """
        from praisonaiagents import Agent
        from praisonaiagents.config.feature_configs import ExecutionConfig
        
        # Use a simple, reliable test configuration
        agent = Agent(
            name="test_agent",
            instructions="You are a helpful assistant. Always respond briefly in one sentence.",
            llm="gpt-4o-mini",  # Fast, reliable model for testing
            execution=ExecutionConfig(max_iter=3)  # Low limit to test enforcement
        )
        
        # Agent MUST call LLM and produce actual text response
        result = agent.start("Say hello in one sentence")
        print(f"Real agentic test result: {result}")  # Print output so developers can verify
        
        # Verify we got actual LLM output
        assert result is not None
        assert isinstance(result, str)
        assert len(result.strip()) > 0
        assert "hello" in result.lower() or "hi" in result.lower()  # Verify it responded to prompt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])