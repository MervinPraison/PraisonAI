"""
Unit tests for the Checkpoints module.

Tests cover:
- CheckpointConfig creation and validation
- Checkpoint data types
- CheckpointService initialization
- Save, restore, and diff operations
"""

import pytest
import asyncio
import os
import tempfile
import shutil
from datetime import datetime

from praisonaiagents.checkpoints.types import (
    CheckpointConfig, Checkpoint, CheckpointDiff, FileDiff,
    CheckpointResult, CheckpointEvent
)
from praisonaiagents.checkpoints.service import CheckpointService


# =============================================================================
# CheckpointConfig Tests
# =============================================================================

class TestCheckpointConfig:
    """Tests for CheckpointConfig class."""
    
    def test_config_creation(self):
        """Test creating a config."""
        config = CheckpointConfig(workspace_dir="/tmp/test")
        assert config.workspace_dir == "/tmp/test"
        assert config.enabled
        assert config.auto_checkpoint
        assert config.max_checkpoints == 100
    
    def test_config_expands_paths(self):
        """Test that paths are expanded."""
        config = CheckpointConfig(
            workspace_dir="~/test",
            storage_dir="~/.praison/checkpoints"
        )
        assert not config.workspace_dir.startswith("~")
        assert not config.storage_dir.startswith("~")
    
    def test_config_default_storage(self):
        """Test default storage directory."""
        config = CheckpointConfig(workspace_dir="/tmp/test")
        # Uses centralized paths module - .praisonai/checkpoints
        assert ".praisonai/checkpoints" in config.storage_dir or "checkpoints" in config.storage_dir
    
    def test_config_exclude_patterns(self):
        """Test default exclude patterns."""
        config = CheckpointConfig(workspace_dir="/tmp/test")
        assert ".git" in config.exclude_patterns
        assert "__pycache__" in config.exclude_patterns
        assert "node_modules" in config.exclude_patterns
    
    def test_get_checkpoint_dir(self):
        """Test checkpoint directory generation."""
        config = CheckpointConfig(workspace_dir="/tmp/test")
        checkpoint_dir = config.get_checkpoint_dir()
        assert config.storage_dir in checkpoint_dir
        # Should be a hash-based subdirectory
        assert len(os.path.basename(checkpoint_dir)) == 12


# =============================================================================
# Checkpoint Data Type Tests
# =============================================================================

class TestCheckpointTypes:
    """Tests for checkpoint data types."""
    
    def test_checkpoint_creation(self):
        """Test creating a checkpoint."""
        checkpoint = Checkpoint(
            id="abc123def456",
            short_id="abc123de",
            message="Test checkpoint",
            timestamp=datetime.now()
        )
        assert checkpoint.id == "abc123def456"
        assert checkpoint.short_id == "abc123de"
        assert checkpoint.message == "Test checkpoint"
    
    def test_checkpoint_from_git_commit(self):
        """Test creating checkpoint from git commit."""
        checkpoint = Checkpoint.from_git_commit(
            commit_hash="abc123def456789",
            message="Test message",
            timestamp="2024-01-01T00:00:00"
        )
        assert checkpoint.id == "abc123def456789"
        assert checkpoint.short_id == "abc123de"
        assert checkpoint.message == "Test message"
    
    def test_checkpoint_to_dict(self):
        """Test checkpoint serialization."""
        checkpoint = Checkpoint(
            id="abc123",
            short_id="abc1",
            message="Test",
            timestamp=datetime(2024, 1, 1)
        )
        data = checkpoint.to_dict()
        assert data["id"] == "abc123"
        assert data["message"] == "Test"
        assert "timestamp" in data
    
    def test_file_diff(self):
        """Test FileDiff creation."""
        diff = FileDiff(
            path="test.py",
            absolute_path="/tmp/test.py",
            status="modified",
            additions=10,
            deletions=5
        )
        assert diff.path == "test.py"
        assert diff.status == "modified"
        assert diff.additions == 10
    
    def test_checkpoint_diff(self):
        """Test CheckpointDiff creation."""
        files = [
            FileDiff("a.py", "/tmp/a.py", "added", 10, 0),
            FileDiff("b.py", "/tmp/b.py", "modified", 5, 3)
        ]
        diff = CheckpointDiff(
            from_checkpoint="abc123",
            to_checkpoint="def456",
            files=files
        )
        assert diff.total_additions == 15
        assert diff.total_deletions == 3
    
    def test_checkpoint_result_ok(self):
        """Test successful checkpoint result."""
        checkpoint = Checkpoint(
            id="abc123",
            short_id="abc1",
            message="Test",
            timestamp=datetime.now()
        )
        result = CheckpointResult.ok(checkpoint)
        assert result.success
        assert result.checkpoint == checkpoint
        assert result.error is None
    
    def test_checkpoint_result_fail(self):
        """Test failed checkpoint result."""
        result = CheckpointResult.fail("Something went wrong")
        assert not result.success
        assert result.checkpoint is None
        assert result.error == "Something went wrong"


# =============================================================================
# CheckpointService Tests
# =============================================================================

class TestCheckpointService:
    """Tests for CheckpointService class."""
    
    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace directory."""
        workspace = tempfile.mkdtemp(prefix="praison_test_")
        yield workspace
        # Cleanup
        if os.path.exists(workspace):
            shutil.rmtree(workspace)
    
    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage directory."""
        storage = tempfile.mkdtemp(prefix="praison_checkpoints_")
        yield storage
        # Cleanup
        if os.path.exists(storage):
            shutil.rmtree(storage)
    
    def test_service_creation(self, temp_workspace, temp_storage):
        """Test creating a checkpoint service."""
        service = CheckpointService(
            workspace_dir=temp_workspace,
            storage_dir=temp_storage
        )
        assert service.workspace_dir == temp_workspace
        assert not service.is_initialized
    
    @pytest.mark.asyncio
    async def test_service_initialize(self, temp_workspace, temp_storage):
        """Test initializing the service."""
        service = CheckpointService(
            workspace_dir=temp_workspace,
            storage_dir=temp_storage
        )
        
        result = await service.initialize()
        
        assert result
        assert service.is_initialized
        assert os.path.exists(service.git_dir)
    
    @pytest.mark.asyncio
    async def test_service_save_checkpoint(self, temp_workspace, temp_storage):
        """Test saving a checkpoint."""
        service = CheckpointService(
            workspace_dir=temp_workspace,
            storage_dir=temp_storage
        )
        await service.initialize()
        
        # Create a file
        test_file = os.path.join(temp_workspace, "test.txt")
        with open(test_file, "w") as f:
            f.write("Hello, World!")
        
        # Save checkpoint
        result = await service.save("First checkpoint")
        
        assert result.success
        assert result.checkpoint is not None
        assert result.checkpoint.message == "First checkpoint"
    
    @pytest.mark.asyncio
    async def test_service_save_no_changes(self, temp_workspace, temp_storage):
        """Test saving checkpoint with no changes."""
        service = CheckpointService(
            workspace_dir=temp_workspace,
            storage_dir=temp_storage
        )
        await service.initialize()
        
        # Try to save without changes
        result = await service.save("Empty checkpoint")
        
        assert not result.success
        assert "No changes" in result.error
    
    @pytest.mark.asyncio
    async def test_service_save_allow_empty(self, temp_workspace, temp_storage):
        """Test saving empty checkpoint when allowed."""
        service = CheckpointService(
            workspace_dir=temp_workspace,
            storage_dir=temp_storage
        )
        await service.initialize()
        
        # Save empty checkpoint
        result = await service.save("Empty checkpoint", allow_empty=True)
        
        assert result.success
    
    @pytest.mark.asyncio
    async def test_service_restore(self, temp_workspace, temp_storage):
        """Test restoring to a checkpoint."""
        service = CheckpointService(
            workspace_dir=temp_workspace,
            storage_dir=temp_storage
        )
        await service.initialize()
        
        # Create initial file
        test_file = os.path.join(temp_workspace, "test.txt")
        with open(test_file, "w") as f:
            f.write("Version 1")
        
        # Save checkpoint
        result1 = await service.save("Version 1")
        checkpoint_id = result1.checkpoint.id
        
        # Modify file
        with open(test_file, "w") as f:
            f.write("Version 2")
        
        # Restore to checkpoint
        result = await service.restore(checkpoint_id)
        
        assert result.success
        
        # Verify file content
        with open(test_file, "r") as f:
            content = f.read()
        assert content == "Version 1"
    
    @pytest.mark.asyncio
    async def test_service_list_checkpoints(self, temp_workspace, temp_storage):
        """Test listing checkpoints."""
        service = CheckpointService(
            workspace_dir=temp_workspace,
            storage_dir=temp_storage
        )
        await service.initialize()
        
        # Create some checkpoints
        test_file = os.path.join(temp_workspace, "test.txt")
        
        with open(test_file, "w") as f:
            f.write("v1")
        await service.save("Checkpoint 1")
        
        with open(test_file, "w") as f:
            f.write("v2")
        await service.save("Checkpoint 2")
        
        # List checkpoints
        checkpoints = await service.list_checkpoints()
        
        # Should have initial + 2 checkpoints
        assert len(checkpoints) >= 2
    
    @pytest.mark.asyncio
    async def test_service_diff(self, temp_workspace, temp_storage):
        """Test getting diff between checkpoints."""
        service = CheckpointService(
            workspace_dir=temp_workspace,
            storage_dir=temp_storage
        )
        await service.initialize()
        
        # Create file and checkpoint
        test_file = os.path.join(temp_workspace, "test.txt")
        with open(test_file, "w") as f:
            f.write("Hello")
        await service.save("Initial")
        
        # Modify file
        with open(test_file, "w") as f:
            f.write("Hello World")
        
        # Get diff
        diff = await service.diff()
        
        assert diff.from_checkpoint != ""
        assert len(diff.files) > 0
    
    @pytest.mark.asyncio
    async def test_service_protected_path(self, temp_storage):
        """Test that protected paths are rejected."""
        service = CheckpointService(
            workspace_dir=os.path.expanduser("~"),
            storage_dir=temp_storage
        )
        
        result = await service.initialize()
        
        assert not result
        assert not service.is_initialized
    
    @pytest.mark.asyncio
    async def test_service_event_handlers(self, temp_workspace, temp_storage):
        """Test event handlers."""
        service = CheckpointService(
            workspace_dir=temp_workspace,
            storage_dir=temp_storage
        )
        
        events_received = []
        
        def on_initialized(data):
            events_received.append(("initialized", data))
        
        def on_checkpoint(data):
            events_received.append(("checkpoint", data))
        
        service.on(CheckpointEvent.INITIALIZED, on_initialized)
        service.on(CheckpointEvent.CHECKPOINT_CREATED, on_checkpoint)
        
        await service.initialize()
        
        test_file = os.path.join(temp_workspace, "test.txt")
        with open(test_file, "w") as f:
            f.write("test")
        await service.save("Test")
        
        assert len(events_received) == 2
        assert events_received[0][0] == "initialized"
        assert events_received[1][0] == "checkpoint"
    
    @pytest.mark.asyncio
    async def test_service_cleanup(self, temp_workspace, temp_storage):
        """Test service cleanup."""
        service = CheckpointService(
            workspace_dir=temp_workspace,
            storage_dir=temp_storage
        )
        await service.initialize()
        
        await service.cleanup()
        
        assert not service.is_initialized
    
    @pytest.mark.asyncio
    async def test_service_delete_all(self, temp_workspace, temp_storage):
        """Test deleting all checkpoints."""
        service = CheckpointService(
            workspace_dir=temp_workspace,
            storage_dir=temp_storage
        )
        await service.initialize()
        
        checkpoint_dir = service.checkpoint_dir
        assert os.path.exists(checkpoint_dir)
        
        result = await service.delete_all()
        
        assert result
        assert not os.path.exists(checkpoint_dir)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
