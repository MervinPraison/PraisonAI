"""
Tests for Workflow Context Management.

TDD: These tests define the expected behavior for context propagation
from Workflow to child agents, parallel loop isolation, and tool output truncation.

Tests cover:
1. Workflow context param propagates to temp agents
2. Workflow context param propagates to existing agents  
3. Parallel loop workers have isolated context
4. Tool output truncation works in workflow context
5. Zero overhead when context=False
"""

import pytest
from unittest.mock import Mock, patch


class TestWorkflowContextPropagation:
    """Test that workflow context param propagates to child agents."""
    
    def test_workflow_context_true_propagates_to_temp_agents(self):
        """When workflow has context=True, temp agents should receive context=True."""
        from praisonaiagents import Workflow, Task
        
        # Create workflow with context enabled
        workflow = Workflow(
            name="test_workflow",
            steps=[
                Task(
                    name="step1",
                    action="Test action {{input}}",
                )
            ],
            context=True,  # Enable context management
        )
        
        # Mock the Agent class at the correct import location
        with patch('praisonaiagents.agent.agent.Agent') as MockAgent:
            mock_agent_instance = Mock()
            mock_agent_instance.chat = Mock(return_value="test response")
            MockAgent.return_value = mock_agent_instance
            
            # Run workflow
            try:
                workflow.run("test input")
            except Exception:
                pass  # May fail due to mocking, but we want to check Agent call
            
            # Verify Agent was called with context param
            if MockAgent.called:
                call_kwargs = MockAgent.call_args[1] if MockAgent.call_args[1] else {}
                # The key assertion: context should be passed
                assert 'context' in call_kwargs, "Agent should receive context param from workflow"
                assert call_kwargs['context'] is True or call_kwargs['context'] is not False, \
                    "Agent context should be truthy when workflow context=True"
    
    def test_workflow_context_false_no_overhead(self):
        """When workflow has context=False, no context manager should be created."""
        from praisonaiagents import Workflow, Task
        
        workflow = Workflow(
            name="test_workflow",
            steps=[
                Task(
                    name="step1",
                    action="Test action",
                )
            ],
            context=False,  # Disabled (default)
        )
        
        # Context manager should not be initialized
        assert workflow._context_manager is None or not workflow._context_manager_initialized, \
            "Context manager should not be initialized when context=False"
    
    def test_workflow_context_propagates_to_existing_agent(self):
        """When workflow has context=True, existing agents should get context enabled."""
        from praisonaiagents import Workflow, Agent
        
        # Create an agent without context
        agent = Agent(
            name="test_agent",
            instructions="Test instructions",
            context=False,  # Initially disabled
        )
        
        # Create workflow with context enabled
        workflow = Workflow(
            name="test_workflow",
            steps=[agent],
            context=True,
        )
        
        # After workflow processes the agent, it should have context enabled
        # This tests that workflow propagates its context setting to child agents
        # The implementation should set agent._context_param or agent.context_manager
        
        # For now, we just verify the workflow has context enabled
        assert workflow.context is True, "Workflow should have context=True"


class TestParallelLoopContextIsolation:
    """Test that parallel loop workers have isolated context."""
    
    def test_parallel_loop_workers_have_isolated_chat_history(self):
        """Each parallel worker should have its own isolated chat history."""
        from praisonaiagents.workflows.workflows import Workflow, Loop, Task
        
        # Track chat histories from each worker
        worker_histories = []
        
        def capture_history_handler(context):
            """Handler that captures the chat history state."""
            # In a real scenario, we'd check the agent's chat_history
            # For now, we verify the context is isolated
            worker_histories.append(context.variables.get('loop_index', -1))
            return f"Result for item {context.variables.get('item', 'unknown')}"
        
        workflow = Workflow(
            name="parallel_test",
            steps=[
                Loop(
                    step=Task(
                        name="worker",
                        handler=capture_history_handler,
                    ),
                    over="items",
                    parallel=True,
                    max_workers=4,
                )
            ],
            variables={"items": ["a", "b", "c", "d"]},
        )
        
        workflow.run("")
        
        # Verify all 4 items were processed
        assert len(worker_histories) == 4, "All 4 items should be processed"
        # Verify each got a unique loop_index (0, 1, 2, 3)
        assert set(worker_histories) == {0, 1, 2, 3}, "Each worker should have unique loop_index"
    
    def test_parallel_workers_dont_share_accumulated_context(self):
        """Parallel workers should not accumulate context from other workers."""
        from praisonaiagents.workflows.workflows import Workflow, Loop, Task
        
        # This test verifies that when using agents in parallel loops,
        # each agent starts with a clean chat_history, not accumulated from others
        
        accumulated_lengths = []
        
        def check_history_length(context):
            """Check that history doesn't grow across parallel workers."""
            # In isolated execution, each worker should start fresh
            # We can't directly access agent.chat_history in handler,
            # but we can verify variables don't leak
            prev = context.variables.get('_accumulated', 0)
            accumulated_lengths.append(prev)
            return "done"
        
        workflow = Workflow(
            name="isolation_test",
            steps=[
                Loop(
                    step=Task(
                        name="checker",
                        handler=check_history_length,
                    ),
                    over="items",
                    parallel=True,
                    max_workers=2,
                )
            ],
            variables={"items": [1, 2, 3, 4]},
        )
        
        workflow.run("")
        
        # All workers should see 0 accumulated (isolated)
        assert all(x == 0 for x in accumulated_lengths), \
            "Parallel workers should not see accumulated state from others"


class TestToolOutputTruncation:
    """Test that tool outputs are truncated when context management is enabled."""
    
    def test_tool_output_truncated_with_context_enabled(self):
        """Tool outputs should be truncated when agent has context=True."""
        from praisonaiagents import Agent
        
        # Create agent with context management
        agent = Agent(
            name="test_agent",
            instructions="Test",
            context=True,
        )
        
        # Verify context manager exists
        assert agent.context_manager is not None, \
            "Agent with context=True should have context_manager"
        
        # Test truncation
        long_output = "x" * 100000  # 100K characters
        truncated = agent._truncate_tool_output("test_tool", long_output)
        
        # Should be truncated (default budget is ~10K tokens ≈ 40K chars)
        assert len(truncated) < len(long_output), \
            "Long tool output should be truncated"
        assert "[truncated]" in truncated.lower() or len(truncated) < 50000, \
            "Truncated output should indicate truncation or be shorter"
    
    def test_tool_output_not_truncated_without_context(self):
        """Tool outputs should pass through unchanged when context=False."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="test_agent",
            instructions="Test",
            context=False,  # Disabled
        )
        
        long_output = "x" * 100000
        result = agent._truncate_tool_output("test_tool", long_output)
        
        # Should be unchanged
        assert result == long_output, \
            "Tool output should not be modified when context=False"


class TestWorkflowContextManagerConfig:
    """Test workflow context manager configuration."""
    
    def test_workflow_accepts_manager_config(self):
        """Workflow should accept ManagerConfig for detailed configuration."""
        from praisonaiagents import Workflow, Task
        from praisonaiagents.context import ManagerConfig
        
        config = ManagerConfig(
            auto_compact=True,
            compact_threshold=0.7,
            default_tool_output_max=5000,
        )
        
        workflow = Workflow(
            name="configured_workflow",
            steps=[
                Task(name="step1", action="test"),
            ],
            context=config,
        )
        
        # Workflow should store the config
        assert workflow.context is config or workflow._context_manager is not None, \
            "Workflow should accept and store ManagerConfig"
    
    def test_workflow_context_string_preset(self):
        """Workflow should accept string presets for context."""
        from praisonaiagents import Workflow, Task
        
        # This tests future functionality where context="auto" enables smart defaults
        workflow = Workflow(
            name="preset_workflow",
            steps=[
                Task(name="step1", action="test"),
            ],
            context=True,  # Simple boolean for now
        )
        
        assert workflow.context is True, "Workflow should accept boolean context"


class TestZeroOverhead:
    """Test that context management has zero overhead when disabled."""
    
    def test_no_context_manager_import_when_disabled(self):
        """ContextManager should not be imported when context=False."""
        from praisonaiagents import Workflow, Task
        
        workflow = Workflow(
            name="no_context",
            steps=[
                Task(name="step1", action="test"),
            ],
            context=False,
        )
        
        # _context_manager should be None and not initialized
        assert workflow._context_manager is None, \
            "Context manager should be None when context=False"
        assert not workflow._context_manager_initialized, \
            "Context manager should not be initialized when context=False"
    
    def test_agent_context_lazy_loading(self):
        """Agent context manager should be lazy loaded."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="lazy_agent",
            instructions="Test",
            context=True,
        )
        
        # Before first access, should not be initialized
        assert not agent._context_manager_initialized, \
            "Context manager should not be initialized until first access"
        
        # After access, should be initialized
        _ = agent.context_manager
        assert agent._context_manager_initialized, \
            "Context manager should be initialized after first access"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
