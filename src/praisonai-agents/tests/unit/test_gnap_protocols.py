"""
Unit tests for GNAP (Git-Native Agent Protocol) protocols.

Tests the protocol interfaces in the Core SDK to ensure they follow
PraisonAI's protocol-driven architecture correctly.
"""

import pytest
from typing import Any, Dict, List, Optional

from praisonaiagents.gnap.protocols import (
    GNAPProtocol,
    GNAPRepositoryProtocol,
    GNAPTaskProtocol,
    GNAPTaskSpec,
    GNAPTaskStatus,
)
from praisonaiagents.gnap.models import (
    GNAPTask,
    GNAPConfig,
    TaskDependency,
)


class TestGNAPTaskStatus:
    """Test GNAP task status enum."""
    
    def test_terminal_states(self):
        """Test terminal state identification."""
        assert GNAPTaskStatus.COMPLETED.is_terminal()
        assert GNAPTaskStatus.FAILED.is_terminal()
        assert GNAPTaskStatus.CANCELLED.is_terminal()
        
        assert not GNAPTaskStatus.PENDING.is_terminal()
        assert not GNAPTaskStatus.CLAIMED.is_terminal()
        assert not GNAPTaskStatus.IN_PROGRESS.is_terminal()
    
    def test_active_states(self):
        """Test active state identification."""
        assert GNAPTaskStatus.PENDING.is_active()
        assert GNAPTaskStatus.CLAIMED.is_active()
        assert GNAPTaskStatus.IN_PROGRESS.is_active()
        
        assert not GNAPTaskStatus.COMPLETED.is_active()
        assert not GNAPTaskStatus.FAILED.is_active()
        assert not GNAPTaskStatus.CANCELLED.is_active()


class TestGNAPTask:
    """Test GNAP task model."""
    
    def test_task_creation(self):
        """Test basic task creation."""
        task = GNAPTask(
            agent_spec={"name": "test_agent", "instructions": "Be helpful"},
            input_data={"prompt": "Hello world"}
        )
        
        assert task.id is not None
        assert len(task.id) == 12  # UUID hex[:12]
        assert task.status == GNAPTaskStatus.PENDING
        assert task.agent_spec["name"] == "test_agent"
        assert task.input_data["prompt"] == "Hello world"
        assert task.is_ready  # No dependencies
    
    def test_task_serialization(self):
        """Test task to/from dict conversion."""
        original = GNAPTask(
            agent_spec={"name": "test_agent"},
            input_data={"prompt": "Test prompt"},
            priority=2,
            dependencies=["task-1", "task-2"]
        )
        
        # Convert to dict and back
        data = original.to_dict()
        restored = GNAPTask.from_dict(data)
        
        assert restored.id == original.id
        assert restored.status == original.status
        assert restored.agent_spec == original.agent_spec
        assert restored.input_data == original.input_data
        assert restored.priority == original.priority
        assert restored.dependencies == original.dependencies
    
    def test_task_with_dependencies(self):
        """Test task with dependencies."""
        task = GNAPTask(
            agent_spec={"name": "test_agent"},
            input_data={"prompt": "Test"},
            dependencies=["dep-1", "dep-2"]
        )
        
        # Task with dependencies is not ready (simplified logic)
        assert not task.is_ready
    
    def test_retry_logic(self):
        """Test task retry logic."""
        task = GNAPTask(
            status=GNAPTaskStatus.FAILED,
            retry_count=1,
            max_retries=3
        )
        
        assert task.can_retry()
        
        # Exceeded retries
        task.retry_count = 3
        assert not task.can_retry()
        
        # Completed task cannot retry
        task.status = GNAPTaskStatus.COMPLETED
        task.retry_count = 0
        assert not task.can_retry()


class TestGNAPConfig:
    """Test GNAP configuration."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = GNAPConfig()
        
        assert config.repo_path == ".gnap"
        assert config.branch == "tasks"
        assert config.worker_id is not None
        assert config.poll_interval_seconds == 5.0
        assert config.auto_sync is True
    
    def test_config_serialization(self):
        """Test config to/from dict conversion."""
        original = GNAPConfig(
            repo_path="/custom/path",
            remote_url="https://github.com/user/repo.git",
            branch="custom-tasks",
            poll_interval_seconds=10.0
        )
        
        # Convert to dict and back
        data = original.to_dict()
        restored = GNAPConfig.from_dict(data)
        
        assert restored.repo_path == original.repo_path
        assert restored.remote_url == original.remote_url
        assert restored.branch == original.branch
        assert restored.poll_interval_seconds == original.poll_interval_seconds


class TestTaskDependency:
    """Test task dependency model."""
    
    def test_dependency_creation(self):
        """Test basic dependency creation."""
        dep = TaskDependency(
            task_id="task-1",
            dependency_id="task-0",
            dependency_type="completion"
        )
        
        assert dep.task_id == "task-1"
        assert dep.dependency_id == "task-0"
        assert dep.dependency_type == "completion"
    
    def test_dependency_serialization(self):
        """Test dependency to/from dict conversion."""
        original = TaskDependency(
            task_id="task-1",
            dependency_id="task-0",
            dependency_type="output"
        )
        
        data = original.to_dict()
        restored = TaskDependency.from_dict(data)
        
        assert restored.task_id == original.task_id
        assert restored.dependency_id == original.dependency_id
        assert restored.dependency_type == original.dependency_type


class MockGNAPRepository:
    """Mock implementation of GNAPRepositoryProtocol for testing."""
    
    def __init__(self):
        self.tasks: Dict[str, GNAPTask] = {}
        self.initialized = False
    
    def init_repository(self, path: str, branch: str = "tasks") -> None:
        self.initialized = True
        self.path = path
        self.branch = branch
    
    def clone_repository(self, url: str, path: str, branch: str = "tasks") -> None:
        self.initialized = True
        self.path = path
        self.branch = branch
        self.url = url
    
    def commit_task(self, task_spec: GNAPTaskSpec) -> str:
        self.tasks[task_spec.id] = task_spec
        return f"commit-{task_spec.id}"
    
    def read_task(self, task_id: str) -> Optional[GNAPTaskSpec]:
        return self.tasks.get(task_id)
    
    def list_tasks(
        self, 
        status: Optional[GNAPTaskStatus] = None,
        agent_id: Optional[str] = None
    ) -> List[GNAPTaskSpec]:
        tasks = list(self.tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        if agent_id:
            tasks = [t for t in tasks if t.agent_spec.get("name") == agent_id]
        return tasks
    
    def sync_with_remote(self) -> None:
        pass
    
    def get_task_history(self, task_id: str) -> List[Dict[str, Any]]:
        return []


class TestGNAPProtocolCompliance:
    """Test that mock implementations satisfy protocol contracts."""
    
    def test_repository_protocol_compliance(self):
        """Test that MockGNAPRepository satisfies GNAPRepositoryProtocol."""
        repo = MockGNAPRepository()
        
        # Protocol compliance check
        assert isinstance(repo, GNAPRepositoryProtocol)
        
        # Test basic operations
        repo.init_repository("/test/path", "test-branch")
        assert repo.initialized
        assert repo.path == "/test/path"
        assert repo.branch == "test-branch"
        
        # Test task operations
        task = GNAPTask(
            agent_spec={"name": "test_agent"},
            input_data={"prompt": "Test"}
        )
        
        commit_hash = repo.commit_task(task)
        assert commit_hash == f"commit-{task.id}"
        
        retrieved_task = repo.read_task(task.id)
        assert retrieved_task is not None
        assert retrieved_task.id == task.id
        
        tasks = repo.list_tasks(status=GNAPTaskStatus.PENDING)
        assert len(tasks) == 1
        assert tasks[0].id == task.id
    
    def test_task_spec_protocol_compliance(self):
        """Test that GNAPTask satisfies GNAPTaskSpec protocol."""
        task = GNAPTask(
            agent_spec={"name": "test_agent", "model": "gpt-4o-mini"},
            input_data={"prompt": "Hello world", "context": {}},
            dependencies=["dep-1"]
        )
        
        # Protocol compliance check
        assert isinstance(task, GNAPTaskSpec)
        
        # Test protocol properties
        assert isinstance(task.id, str)
        assert isinstance(task.status, GNAPTaskStatus)
        assert isinstance(task.created_at, str)
        assert isinstance(task.agent_spec, dict)
        assert isinstance(task.input_data, dict)
        assert isinstance(task.dependencies, list)
        
        # Test serialization methods
        data = task.to_dict()
        assert isinstance(data, dict)
        assert "id" in data
        assert "status" in data
        
        restored = GNAPTask.from_dict(data)
        assert isinstance(restored, GNAPTaskSpec)
        assert restored.id == task.id


class TestProtocolImports:
    """Test that protocols are properly imported and accessible."""
    
    def test_core_imports(self):
        """Test that all core GNAP types are importable."""
        from praisonaiagents.gnap import (
            GNAPProtocol,
            GNAPRepositoryProtocol,
            GNAPTaskProtocol,
            GNAPTaskSpec,
            GNAPTaskStatus,
            GNAPTask,
            GNAPConfig,
            TaskDependency,
        )
        
        # Verify types exist
        assert GNAPProtocol is not None
        assert GNAPRepositoryProtocol is not None
        assert GNAPTaskProtocol is not None
        assert GNAPTaskSpec is not None
        assert GNAPTaskStatus is not None
        assert GNAPTask is not None
        assert GNAPConfig is not None
        assert TaskDependency is not None
    
    def test_main_package_imports(self):
        """Test that GNAP types are accessible from main package."""
        # These should work via __getattr__ in main __init__.py
        try:
            from praisonaiagents import GNAPProtocol, GNAPTask, GNAPConfig
            assert GNAPProtocol is not None
            assert GNAPTask is not None
            assert GNAPConfig is not None
        except ImportError:
            pytest.fail("GNAP types not accessible from main package")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])