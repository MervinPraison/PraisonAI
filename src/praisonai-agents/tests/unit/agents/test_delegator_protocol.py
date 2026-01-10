"""
TDD tests for delegator.py protocol compliance.

Tests that SubagentDelegator creates agents using consolidated params
instead of legacy params like verbose=, max_iter=.
"""

import pytest
from unittest.mock import Mock, patch


class TestDelegatorProtocolCompliance:
    """Test that delegator uses consolidated params when creating agents."""
    
    @pytest.mark.asyncio
    async def test_create_agent_uses_output_not_verbose(self):
        """Delegator should use output='silent' instead of verbose=False."""
        from praisonaiagents.agents.delegator import SubagentDelegator, DelegationTask
        from praisonaiagents.agents.profiles import AgentProfile
        
        # Create a delegator
        delegator = SubagentDelegator()
        
        # Create a profile and task
        profile = AgentProfile(
            name="test_agent",
            system_prompt="Test prompt",
            max_steps=10,
        )
        task = DelegationTask(
            task_id="test-1",
            agent_name="test_agent",
            objective="Test task",
            max_steps=5,
        )
        
        # Mock Agent to capture how it's called (Agent is imported inside _create_agent)
        with patch('praisonaiagents.agent.agent.Agent') as MockAgent:
            MockAgent.return_value = Mock()
            
            await delegator._create_agent(profile, task)
            
            # Verify Agent was called
            MockAgent.assert_called_once()
            call_kwargs = MockAgent.call_args[1]
            
            # Should NOT have verbose= param
            assert 'verbose' not in call_kwargs, "Should not use legacy verbose= param"
            
            # Should have output= param with 'silent' preset
            assert 'output' in call_kwargs, "Should use consolidated output= param"
            assert call_kwargs['output'] == 'silent', "Should use output='silent' for quiet mode"
    
    @pytest.mark.asyncio
    async def test_create_agent_uses_execution_not_max_iter(self):
        """Delegator should use execution= instead of max_iter=."""
        from praisonaiagents.agents.delegator import SubagentDelegator, DelegationTask
        from praisonaiagents.agents.profiles import AgentProfile
        
        delegator = SubagentDelegator()
        
        profile = AgentProfile(
            name="test_agent",
            system_prompt="Test prompt",
            max_steps=10,
        )
        task = DelegationTask(
            task_id="test-2",
            agent_name="test_agent",
            objective="Test task",
            max_steps=5,
        )
        
        with patch('praisonaiagents.agent.agent.Agent') as MockAgent:
            MockAgent.return_value = Mock()
            
            await delegator._create_agent(profile, task)
            
            call_kwargs = MockAgent.call_args[1]
            
            # Should NOT have max_iter= param
            assert 'max_iter' not in call_kwargs, "Should not use legacy max_iter= param"
            
            # Should have execution= param with max_iter in config
            assert 'execution' in call_kwargs, "Should use consolidated execution= param"
            exec_config = call_kwargs['execution']
            assert isinstance(exec_config, dict), "execution should be a dict config"
            assert 'max_iter' in exec_config, "execution config should contain max_iter"
            assert exec_config['max_iter'] == 5, "max_iter should be min(task.max_steps, profile.max_steps)"


class TestDelegatorBackwardCompatibility:
    """Test that delegator still works correctly after modernization."""
    
    @pytest.mark.asyncio
    async def test_create_agent_returns_valid_agent(self):
        """Created agent should be usable."""
        from praisonaiagents.agents.delegator import SubagentDelegator, DelegationTask
        from praisonaiagents.agents.profiles import AgentProfile
        
        delegator = SubagentDelegator()
        
        profile = AgentProfile(
            name="test_agent",
            system_prompt="You are a helpful assistant.",
            max_steps=10,
        )
        task = DelegationTask(
            task_id="test-3",
            agent_name="test_agent",
            objective="Say hello",
            max_steps=5,
        )
        
        with patch('praisonaiagents.agent.agent.Agent') as MockAgent:
            mock_agent = Mock()
            mock_agent.chat = Mock(return_value="Hello!")
            MockAgent.return_value = mock_agent
            
            agent = await delegator._create_agent(profile, task)
            
            # Agent should be returned
            assert agent is not None
            assert agent == mock_agent
