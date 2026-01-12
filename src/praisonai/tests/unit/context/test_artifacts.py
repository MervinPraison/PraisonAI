"""
Unit tests for Dynamic Context Discovery - Artifacts.

Tests:
- ArtifactRef creation and serialization
- FileSystemArtifactStore operations
- OutputQueue middleware (for queuing large outputs)
- Secret redaction
"""

import tempfile
import pytest
from pathlib import Path


class TestArtifactRef:
    """Tests for ArtifactRef dataclass."""
    
    def test_create_artifact_ref(self):
        """Test creating an ArtifactRef."""
        from praisonaiagents.context.artifacts import ArtifactRef
        
        ref = ArtifactRef(
            path="/tmp/test.json",
            summary="Test artifact",
            size_bytes=1024,
            mime_type="application/json",
        )
        
        assert ref.path == "/tmp/test.json"
        assert ref.summary == "Test artifact"
        assert ref.size_bytes == 1024
        assert ref.mime_type == "application/json"
    
    def test_to_inline(self):
        """Test inline representation."""
        from praisonaiagents.context.artifacts import ArtifactRef
        
        ref = ArtifactRef(
            path="/tmp/test.json",
            summary="API response data",
            size_bytes=50000,
            tool_name="api_call",
        )
        
        inline = ref.to_inline()
        assert "Artifact" in inline
        assert "api_call" in inline
        assert "/tmp/test.json" in inline
        assert "48.8 KB" in inline
    
    def test_to_dict_and_from_dict(self):
        """Test serialization round-trip."""
        from praisonaiagents.context.artifacts import ArtifactRef
        
        ref = ArtifactRef(
            path="/tmp/test.json",
            summary="Test",
            size_bytes=100,
            artifact_id="abc123",
            agent_id="agent1",
            run_id="run1",
        )
        
        data = ref.to_dict()
        restored = ArtifactRef.from_dict(data)
        
        assert restored.path == ref.path
        assert restored.artifact_id == ref.artifact_id
        assert restored.agent_id == ref.agent_id
    
    def test_format_size(self):
        """Test size formatting."""
        from praisonaiagents.context.artifacts import ArtifactRef
        
        assert ArtifactRef._format_size(500) == "500 B"
        assert ArtifactRef._format_size(1024) == "1.0 KB"
        assert ArtifactRef._format_size(1024 * 1024) == "1.0 MB"
        assert ArtifactRef._format_size(1024 * 1024 * 1024) == "1.0 GB"


class TestQueueConfig:
    """Tests for QueueConfig."""
    
    def test_default_config(self):
        """Test default configuration."""
        from praisonaiagents.context.artifacts import QueueConfig
        
        config = QueueConfig()
        
        assert config.enabled is True
        assert config.inline_max_bytes == 32 * 1024
        assert config.redact_secrets is True
        assert len(config.secret_patterns) > 0
    
    def test_custom_config(self):
        """Test custom configuration."""
        from praisonaiagents.context.artifacts import QueueConfig
        
        config = QueueConfig(
            enabled=False,
            inline_max_bytes=16 * 1024,
            redact_secrets=False,
        )
        
        assert config.enabled is False
        assert config.inline_max_bytes == 16 * 1024
        assert config.redact_secrets is False


class TestFileSystemArtifactStore:
    """Tests for FileSystemArtifactStore."""
    
    @pytest.fixture
    def temp_store(self):
        """Create a temporary artifact store."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from praisonai.context import FileSystemArtifactStore
            store = FileSystemArtifactStore(base_dir=tmpdir)
            yield store
    
    def test_store_json(self, temp_store):
        """Test storing JSON content."""
        from praisonaiagents.context.artifacts import ArtifactMetadata
        
        content = {"key": "value", "numbers": [1, 2, 3]}
        metadata = ArtifactMetadata(
            agent_id="agent1",
            run_id="run1",
            tool_name="test_tool",
        )
        
        ref = temp_store.store(content, metadata)
        
        assert ref.path.endswith(".json")
        assert ref.mime_type == "application/json"
        assert ref.size_bytes > 0
        assert ref.checksum != ""
        assert "test_tool" in ref.path
    
    def test_store_text(self, temp_store):
        """Test storing text content."""
        from praisonaiagents.context.artifacts import ArtifactMetadata
        
        content = "Hello, world!\nThis is a test."
        metadata = ArtifactMetadata(agent_id="agent1", run_id="run1")
        
        ref = temp_store.store(content, metadata)
        
        assert ref.path.endswith(".txt")
        assert ref.mime_type == "text/plain"
    
    def test_load(self, temp_store):
        """Test loading stored content."""
        from praisonaiagents.context.artifacts import ArtifactMetadata
        
        original = {"data": [1, 2, 3]}
        metadata = ArtifactMetadata(agent_id="agent1", run_id="run1")
        
        ref = temp_store.store(original, metadata)
        loaded = temp_store.load(ref)
        
        assert loaded == original
    
    def test_tail(self, temp_store):
        """Test tail operation."""
        from praisonaiagents.context.artifacts import ArtifactMetadata
        
        lines = "\n".join([f"Line {i}" for i in range(100)])
        metadata = ArtifactMetadata(agent_id="agent1", run_id="run1")
        
        ref = temp_store.store(lines, metadata)
        tail = temp_store.tail(ref, lines=5)
        
        assert "Line 95" in tail
        assert "Line 99" in tail
    
    def test_head(self, temp_store):
        """Test head operation."""
        from praisonaiagents.context.artifacts import ArtifactMetadata
        
        lines = "\n".join([f"Line {i}" for i in range(100)])
        metadata = ArtifactMetadata(agent_id="agent1", run_id="run1")
        
        ref = temp_store.store(lines, metadata)
        head = temp_store.head(ref, lines=5)
        
        assert "Line 0" in head
        assert "Line 4" in head
        assert "Line 5" not in head
    
    def test_grep(self, temp_store):
        """Test grep operation."""
        from praisonaiagents.context.artifacts import ArtifactMetadata
        
        content = "Error: Something went wrong\nInfo: All good\nError: Another error"
        metadata = ArtifactMetadata(agent_id="agent1", run_id="run1")
        
        ref = temp_store.store(content, metadata)
        matches = temp_store.grep(ref, pattern="Error")
        
        assert len(matches) == 2
        assert matches[0].line_number == 1
        assert "Something went wrong" in matches[0].line_content
    
    def test_chunk(self, temp_store):
        """Test chunk operation."""
        from praisonaiagents.context.artifacts import ArtifactMetadata
        
        lines = "\n".join([f"Line {i}" for i in range(100)])
        metadata = ArtifactMetadata(agent_id="agent1", run_id="run1")
        
        ref = temp_store.store(lines, metadata)
        chunk = temp_store.chunk(ref, start_line=10, end_line=15)
        
        assert "Line 9" in chunk
        assert "Line 14" in chunk
        assert "Line 15" not in chunk
    
    def test_list_artifacts(self, temp_store):
        """Test listing artifacts."""
        from praisonaiagents.context.artifacts import ArtifactMetadata
        
        # Store multiple artifacts
        for i in range(3):
            metadata = ArtifactMetadata(
                agent_id="agent1",
                run_id="run1",
                tool_name=f"tool{i}",
            )
            temp_store.store(f"Content {i}", metadata)
        
        artifacts = temp_store.list_artifacts(run_id="run1")
        
        assert len(artifacts) == 3
    
    def test_delete(self, temp_store):
        """Test deleting artifacts."""
        from praisonaiagents.context.artifacts import ArtifactMetadata
        
        metadata = ArtifactMetadata(agent_id="agent1", run_id="run1")
        ref = temp_store.store("Test content", metadata)
        
        assert Path(ref.path).exists()
        
        result = temp_store.delete(ref)
        
        assert result is True
        assert not Path(ref.path).exists()
    
    def test_secret_redaction(self, temp_store):
        """Test that secrets are redacted."""
        from praisonaiagents.context.artifacts import ArtifactMetadata
        
        content = 'api_key="sk-1234567890abcdef" password="secret123"'
        metadata = ArtifactMetadata(agent_id="agent1", run_id="run1")
        
        ref = temp_store.store(content, metadata)
        loaded = temp_store.load(ref)
        
        assert "sk-1234567890abcdef" not in loaded
        assert "secret123" not in loaded
        assert "[REDACTED]" in loaded


class TestOutputQueue:
    """Tests for OutputQueue."""
    
    @pytest.fixture
    def temp_queue(self):
        """Create a temporary output queue."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from praisonai.context import OutputQueue
            queue = OutputQueue(base_dir=tmpdir)
            yield queue
    
    def test_small_output_not_queued(self, temp_queue):
        """Test that small outputs are not queued."""
        from praisonaiagents.context.artifacts import ArtifactMetadata, ArtifactRef
        
        content = "Small output"
        metadata = ArtifactMetadata(agent_id="agent1", run_id="run1")
        
        result = temp_queue.process(content, metadata)
        
        assert not isinstance(result, ArtifactRef)
        assert result == content
    
    def test_large_output_queued(self, temp_queue):
        """Test that large outputs are queued."""
        from praisonaiagents.context.artifacts import ArtifactMetadata, ArtifactRef
        
        # Create content larger than threshold (32KB default)
        content = "x" * (40 * 1024)
        metadata = ArtifactMetadata(agent_id="agent1", run_id="run1")
        
        result = temp_queue.process(content, metadata)
        
        assert isinstance(result, ArtifactRef)
        assert result.size_bytes > 0
    
    def test_should_queue(self, temp_queue):
        """Test should_queue logic."""
        small = "small"
        large = "x" * (40 * 1024)
        
        assert temp_queue.should_queue(small) is False
        assert temp_queue.should_queue(large) is True


class TestHelperFunctions:
    """Tests for helper functions."""
    
    def test_compute_checksum(self):
        """Test checksum computation."""
        from praisonaiagents.context.artifacts import compute_checksum
        
        content = "Hello, world!"
        checksum = compute_checksum(content)
        
        assert len(checksum) == 64  # SHA256 hex digest
        
        # Same content should produce same checksum
        assert compute_checksum(content) == checksum
        
        # Different content should produce different checksum
        assert compute_checksum("Different") != checksum
    
    def test_generate_summary_dict(self):
        """Test summary generation for dict."""
        from praisonaiagents.context.artifacts import generate_summary
        
        content = {"key1": "value1", "key2": "value2", "key3": "value3"}
        summary = generate_summary(content)
        
        assert "Dict" in summary
        assert "key1" in summary
    
    def test_generate_summary_list(self):
        """Test summary generation for list."""
        from praisonaiagents.context.artifacts import generate_summary
        
        content = [1, 2, 3, 4, 5]
        summary = generate_summary(content)
        
        assert "List" in summary
        assert "5" in summary
    
    def test_generate_summary_string(self):
        """Test summary generation for string."""
        from praisonaiagents.context.artifacts import generate_summary
        
        content = "A" * 300
        summary = generate_summary(content, max_chars=100)
        
        assert len(summary) <= 100
        assert summary.endswith("...")
