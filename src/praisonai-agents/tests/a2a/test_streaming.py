"""
Tests for A2A Streaming Events
"""


class TestA2AEventEncoder:
    """Tests for A2AEventEncoder."""
    
    def test_encode_event(self):
        """Test encoding a generic event."""
        from praisonaiagents.ui.a2a.streaming import A2AEventEncoder
        
        result = A2AEventEncoder.encode_event("test", {"key": "value"})
        
        assert "event: test" in result
        assert "data:" in result
        assert "key" in result
    
    def test_encode_task_status(self):
        """Test encoding TaskStatusUpdateEvent."""
        from praisonaiagents.ui.a2a.streaming import A2AEventEncoder
        from praisonaiagents.ui.a2a.types import TaskStatusUpdateEvent, TaskStatus, TaskState
        
        event = TaskStatusUpdateEvent(
            task_id="task-123",
            status=TaskStatus(state=TaskState.WORKING),
            final=False,
        )
        
        result = A2AEventEncoder.encode_task_status(event)
        
        assert "event: task.status" in result
        assert "task-123" in result
    
    def test_encode_task_artifact(self):
        """Test encoding TaskArtifactUpdateEvent."""
        from praisonaiagents.ui.a2a.streaming import A2AEventEncoder
        from praisonaiagents.ui.a2a.types import TaskArtifactUpdateEvent, Artifact, TextPart
        
        artifact = Artifact(
            artifact_id="art-1",
            parts=[TextPart(text="Result")]
        )
        event = TaskArtifactUpdateEvent(
            task_id="task-456",
            artifact=artifact,
            last_chunk=True,
        )
        
        result = A2AEventEncoder.encode_task_artifact(event)
        
        assert "event: task.artifact" in result
        assert "art-1" in result
    
    def test_encode_done(self):
        """Test encoding done event."""
        from praisonaiagents.ui.a2a.streaming import A2AEventEncoder
        
        result = A2AEventEncoder.encode_done()
        
        assert "event: done" in result


class TestCreateEvents:
    """Tests for event creation helpers."""
    
    def test_create_status_event(self):
        """Test creating status event."""
        from praisonaiagents.ui.a2a.streaming import create_status_event
        from praisonaiagents.ui.a2a.types import TaskState
        
        event = create_status_event(
            task_id="task-1",
            state=TaskState.WORKING,
        )
        
        assert event.task_id == "task-1"
        assert event.status.state == TaskState.WORKING
    
    def test_create_status_event_final(self):
        """Test creating final status event."""
        from praisonaiagents.ui.a2a.streaming import create_status_event
        from praisonaiagents.ui.a2a.types import TaskState
        
        event = create_status_event(
            task_id="task-2",
            state=TaskState.COMPLETED,
            final=True,
        )
        
        assert event.final is True
    
    def test_create_artifact_event(self):
        """Test creating artifact event."""
        from praisonaiagents.ui.a2a.streaming import create_artifact_event
        
        event = create_artifact_event(
            task_id="task-3",
            content="Generated content",
        )
        
        assert event.task_id == "task-3"
        assert event.artifact is not None
        assert len(event.artifact.parts) == 1
    
    def test_create_artifact_event_last_chunk(self):
        """Test creating last chunk artifact event."""
        from praisonaiagents.ui.a2a.streaming import create_artifact_event
        
        event = create_artifact_event(
            task_id="task-4",
            content="Final content",
            last_chunk=True,
        )
        
        assert event.last_chunk is True
