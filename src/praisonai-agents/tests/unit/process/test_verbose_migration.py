"""
TDD Tests for verbose= to output= migration in Process class.

These tests verify:
1. Process class accepts output= parameter
2. Process class still accepts verbose= for backward compat (with deprecation)
3. output= takes precedence over verbose=
"""
import pytest
from unittest.mock import MagicMock


class TestProcessOutputMigration:
    """Test Process class migration from verbose= to output=."""
    
    def test_process_accepts_output_parameter(self):
        """Process should accept output= parameter."""
        from praisonaiagents.process.process import Process
        from praisonaiagents.agent.agent import Agent
        from praisonaiagents.task.task import Task
        
        # Create minimal mocks
        agent = MagicMock(spec=Agent)
        agent.name = "test_agent"
        task = MagicMock(spec=Task)
        task.id = "task1"
        task.name = "test_task"
        
        # This should work with output= parameter
        process = Process(
            tasks={"task1": task},
            agents=[agent],
            output="verbose"
        )
        
        # Verify verbose was set from output preset
        assert process._verbose
    
    def test_process_output_silent_sets_verbose_false(self):
        """output='silent' should set verbose=False."""
        from praisonaiagents.process.process import Process
        from praisonaiagents.agent.agent import Agent
        from praisonaiagents.task.task import Task
        
        agent = MagicMock(spec=Agent)
        agent.name = "test_agent"
        task = MagicMock(spec=Task)
        task.id = "task1"
        task.name = "test_task"
        
        process = Process(
            tasks={"task1": task},
            agents=[agent],
            output="silent"
        )
        
        assert not process._verbose
    
    def test_process_backward_compat_verbose_true(self):
        """Process should still accept verbose=True for backward compat."""
        from praisonaiagents.process.process import Process
        from praisonaiagents.agent.agent import Agent
        from praisonaiagents.task.task import Task
        
        agent = MagicMock(spec=Agent)
        agent.name = "test_agent"
        task = MagicMock(spec=Task)
        task.id = "task1"
        task.name = "test_task"
        
        # Old API should still work
        process = Process(
            tasks={"task1": task},
            agents=[agent],
            verbose=True
        )
        
        assert process._verbose
    
    def test_process_output_takes_precedence_over_verbose(self):
        """output= should take precedence over verbose= if both provided."""
        from praisonaiagents.process.process import Process
        from praisonaiagents.agent.agent import Agent
        from praisonaiagents.task.task import Task
        
        agent = MagicMock(spec=Agent)
        agent.name = "test_agent"
        task = MagicMock(spec=Task)
        task.id = "task1"
        task.name = "test_task"
        
        # output= should win
        process = Process(
            tasks={"task1": task},
            agents=[agent],
            output="silent",
            verbose=True  # This should be ignored
        )
        
        assert not process._verbose


class TestAgentVerboseRejection:
    """Test that Agent class rejects verbose= parameter."""
    
    def test_agent_rejects_verbose_parameter(self):
        """Agent(verbose=True) should raise TypeError."""
        from praisonaiagents import Agent
        
        with pytest.raises(TypeError) as exc_info:
            Agent(instructions="Test", verbose=True)
        
        assert "verbose" in str(exc_info.value).lower()
    
    def test_agent_accepts_output_verbose(self):
        """Agent(output='verbose') should work."""
        from praisonaiagents import Agent
        
        agent = Agent(instructions="Test", output="verbose")
        
        assert agent.verbose
        assert agent.markdown


class TestAgentTeamOutputParameter:
    """Test that AgentTeam uses output= not verbose=."""
    
    def test_agent_team_accepts_output_parameter(self):
        """AgentTeam should accept output= parameter."""
        from praisonaiagents import Agent, AgentTeam, Task
        
        agent = Agent(instructions="Test agent")
        task = Task(description="Test task", agent=agent)
        
        team = AgentTeam(
            agents=[agent],
            tasks=[task],
            output="verbose"
        )
        
        assert team.verbose
    
    def test_agent_team_output_silent(self):
        """AgentTeam with output='silent' should have verbose=0 or False."""
        from praisonaiagents import Agent, AgentTeam, Task
        
        agent = Agent(instructions="Test agent")
        task = Task(description="Test task", agent=agent)
        
        team = AgentTeam(
            agents=[agent],
            tasks=[task],
            output="silent"
        )
        
        assert not team.verbose
