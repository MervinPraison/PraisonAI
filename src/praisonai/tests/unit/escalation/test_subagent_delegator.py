"""
Tests for Subagent Delegator.

TDD tests for subagent delegation framework.
"""

import pytest
from unittest.mock import Mock, AsyncMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'praisonai-agents'))

from praisonaiagents.agents.delegator import (
    SubagentDelegator,
    DelegationConfig,
    DelegationTask,
    DelegationResult,
    DelegationStatus,
    delegate_to_agent,
)
from praisonaiagents.agents.profiles import (
    AgentProfile,
    AgentMode,
    get_profile,
    list_profiles,
)


class TestDelegationConfig:
    """Tests for DelegationConfig."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = DelegationConfig()
        
        assert config.max_concurrent_subagents == 3
        assert config.max_total_subagents == 10
        assert config.default_timeout_seconds == 300.0
        assert config.inherit_permissions is True
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = DelegationConfig(
            max_concurrent_subagents=5,
            max_total_subagents=20,
            default_timeout_seconds=600.0,
        )
        
        assert config.max_concurrent_subagents == 5
        assert config.max_total_subagents == 20
        assert config.default_timeout_seconds == 600.0


class TestDelegationTask:
    """Tests for DelegationTask."""
    
    def test_task_creation(self):
        """Test task creation with defaults."""
        task = DelegationTask(
            task_id="test_1",
            agent_name="explorer",
            objective="Find files",
        )
        
        assert task.task_id == "test_1"
        assert task.agent_name == "explorer"
        assert task.status == DelegationStatus.PENDING
        assert task.result is None
    
    def test_task_with_context(self):
        """Test task with context."""
        task = DelegationTask(
            task_id="test_2",
            agent_name="explorer",
            objective="Find auth files",
            context={"workspace": "/path/to/project"},
        )
        
        assert task.context["workspace"] == "/path/to/project"


class TestDelegationResult:
    """Tests for DelegationResult."""
    
    def test_successful_result(self):
        """Test successful result."""
        result = DelegationResult(
            task_id="test_1",
            agent_name="explorer",
            success=True,
            result="Found 5 files",
        )
        
        assert result.success
        assert result.result == "Found 5 files"
        assert result.error is None
    
    def test_failed_result(self):
        """Test failed result."""
        result = DelegationResult(
            task_id="test_1",
            agent_name="explorer",
            success=False,
            error="Agent not found",
        )
        
        assert not result.success
        assert result.error == "Agent not found"


class TestAgentProfiles:
    """Tests for agent profiles."""
    
    def test_explorer_profile_exists(self):
        """Test explorer profile exists."""
        profile = get_profile("explorer")
        
        assert profile is not None
        assert profile.name == "explorer"
        assert profile.mode == AgentMode.SUBAGENT
    
    def test_explorer_is_read_only(self):
        """Test explorer profile is read-only."""
        profile = get_profile("explorer")
        
        assert profile is not None
        assert profile.metadata.get("read_only") is True
        assert "write_file" in profile.metadata.get("blocked_tools", [])
    
    def test_list_profiles(self):
        """Test listing profiles."""
        profiles = list_profiles()
        
        assert len(profiles) > 0
        names = [p.name for p in profiles]
        assert "explorer" in names
        assert "general" in names
    
    def test_profile_to_dict(self):
        """Test profile serialization."""
        profile = get_profile("explorer")
        
        data = profile.to_dict()
        assert data["name"] == "explorer"
        assert data["mode"] == "subagent"
        assert "tools" in data


class TestSubagentDelegator:
    """Tests for SubagentDelegator."""
    
    def test_delegator_creation(self):
        """Test delegator creation."""
        delegator = SubagentDelegator()
        
        assert delegator.config is not None
        assert delegator._running_count == 0
        assert delegator._total_count == 0
    
    def test_get_available_agents(self):
        """Test getting available agents."""
        delegator = SubagentDelegator()
        
        agents = delegator.get_available_agents()
        assert "explorer" in agents
        # Hidden agents should not be included
        assert "compaction" not in agents
    
    def test_get_agent_description(self):
        """Test getting agent description."""
        delegator = SubagentDelegator()
        
        desc = delegator.get_agent_description("explorer")
        assert "read-only" in desc.lower() or "codebase" in desc.lower()
    
    def test_generate_task_id(self):
        """Test task ID generation."""
        delegator = SubagentDelegator()
        
        id1 = delegator._generate_task_id()
        id2 = delegator._generate_task_id()
        
        assert id1 != id2
        assert id1.startswith("task_")
    
    def test_get_stats(self):
        """Test getting statistics."""
        delegator = SubagentDelegator()
        
        stats = delegator.get_stats()
        assert stats["total_tasks"] == 0
        assert stats["running_tasks"] == 0
        assert "max_concurrent" in stats
    
    @pytest.mark.asyncio
    async def test_delegate_unknown_agent(self):
        """Test delegation to unknown agent fails gracefully."""
        delegator = SubagentDelegator()
        
        result = await delegator.delegate(
            agent_name="nonexistent_agent",
            objective="Do something",
        )
        
        assert not result.success
        assert "Unknown agent" in result.error or result.error is not None
    
    @pytest.mark.asyncio
    async def test_delegate_with_mock_factory(self):
        """Test delegation with mock agent factory."""
        mock_agent = Mock()
        mock_agent.chat = Mock(return_value="Task completed")
        
        def factory(name):
            return mock_agent
        
        delegator = SubagentDelegator(agent_factory=factory)
        
        result = await delegator.delegate(
            agent_name="explorer",
            objective="Find files",
        )
        
        assert result.success
        assert result.result == "Task completed"
    
    @pytest.mark.asyncio
    async def test_delegate_respects_max_total(self):
        """Test delegation respects max total limit."""
        config = DelegationConfig(max_total_subagents=1)
        delegator = SubagentDelegator(config=config)
        delegator._total_count = 1  # Simulate already at limit
        
        result = await delegator.delegate(
            agent_name="explorer",
            objective="Find files",
        )
        
        assert not result.success
        assert "Max total" in result.error
    
    @pytest.mark.asyncio
    async def test_task_complete_callback(self):
        """Test task complete callback is called."""
        callback_results = []
        
        def on_complete(result):
            callback_results.append(result)
        
        mock_agent = Mock()
        mock_agent.chat = Mock(return_value="Done")
        
        delegator = SubagentDelegator(
            agent_factory=lambda n: mock_agent,
            on_task_complete=on_complete,
        )
        
        await delegator.delegate("explorer", "Find files")
        
        assert len(callback_results) == 1
        assert callback_results[0].success
    
    @pytest.mark.asyncio
    async def test_cancel_task(self):
        """Test task cancellation."""
        delegator = SubagentDelegator()
        
        # Create a task manually
        task = DelegationTask(
            task_id="test_cancel",
            agent_name="explorer",
            objective="Long task",
            status=DelegationStatus.RUNNING,
        )
        delegator._tasks["test_cancel"] = task
        
        result = await delegator.cancel_task("test_cancel")
        
        assert result is True
        assert task.status == DelegationStatus.CANCELLED
    
    @pytest.mark.asyncio
    async def test_cancel_nonexistent_task(self):
        """Test cancelling nonexistent task."""
        delegator = SubagentDelegator()
        
        result = await delegator.cancel_task("nonexistent")
        
        assert result is False
    
    def test_get_running_tasks(self):
        """Test getting running tasks."""
        delegator = SubagentDelegator()
        
        # Add some tasks
        delegator._tasks["t1"] = DelegationTask(
            task_id="t1",
            agent_name="explorer",
            objective="Task 1",
            status=DelegationStatus.RUNNING,
        )
        delegator._tasks["t2"] = DelegationTask(
            task_id="t2",
            agent_name="explorer",
            objective="Task 2",
            status=DelegationStatus.COMPLETED,
        )
        
        running = delegator.get_running_tasks()
        
        assert len(running) == 1
        assert running[0].task_id == "t1"
    
    def test_get_task_status(self):
        """Test getting task status."""
        delegator = SubagentDelegator()
        
        delegator._tasks["t1"] = DelegationTask(
            task_id="t1",
            agent_name="explorer",
            objective="Task 1",
            status=DelegationStatus.COMPLETED,
        )
        
        status = delegator.get_task_status("t1")
        assert status == DelegationStatus.COMPLETED
        
        status = delegator.get_task_status("nonexistent")
        assert status is None


class TestDelegateParallel:
    """Tests for parallel delegation."""
    
    @pytest.mark.asyncio
    async def test_delegate_parallel_basic(self):
        """Test basic parallel delegation."""
        mock_agent = Mock()
        mock_agent.chat = Mock(return_value="Done")
        
        delegator = SubagentDelegator(
            agent_factory=lambda n: mock_agent,
        )
        
        results = await delegator.delegate_parallel([
            ("explorer", "Task 1"),
            ("explorer", "Task 2"),
        ])
        
        assert len(results) == 2
        assert all(r.success for r in results)
    
    @pytest.mark.asyncio
    async def test_delegate_parallel_with_context(self):
        """Test parallel delegation with context."""
        mock_agent = Mock()
        mock_agent.chat = Mock(return_value="Done")
        
        delegator = SubagentDelegator(
            agent_factory=lambda n: mock_agent,
        )
        
        results = await delegator.delegate_parallel([
            ("explorer", "Task 1", {"key": "value1"}),
            ("explorer", "Task 2", {"key": "value2"}),
        ])
        
        assert len(results) == 2


class TestDelegateToAgentFunction:
    """Tests for convenience function."""
    
    @pytest.mark.asyncio
    async def test_delegate_to_agent_basic(self):
        """Test delegate_to_agent convenience function."""
        # This will fail without a real agent, but tests the interface
        result = await delegate_to_agent(
            agent_name="nonexistent",
            objective="Test",
            timeout_seconds=1.0,
        )
        
        # Should return a result (even if failed)
        assert isinstance(result, DelegationResult)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
