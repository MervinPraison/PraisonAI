"""
Tests for A2A Protocol Types

TDD: Write tests first, then implement types.
"""

import json
from datetime import datetime


class TestTaskState:
    """Tests for TaskState enum."""
    
    def test_task_state_submitted(self):
        """Test SUBMITTED state exists."""
        from praisonaiagents.ui.a2a.types import TaskState
        assert TaskState.SUBMITTED == "submitted"
    
    def test_task_state_working(self):
        """Test WORKING state exists."""
        from praisonaiagents.ui.a2a.types import TaskState
        assert TaskState.WORKING == "working"
    
    def test_task_state_completed(self):
        """Test COMPLETED state exists."""
        from praisonaiagents.ui.a2a.types import TaskState
        assert TaskState.COMPLETED == "completed"
    
    def test_task_state_failed(self):
        """Test FAILED state exists."""
        from praisonaiagents.ui.a2a.types import TaskState
        assert TaskState.FAILED == "failed"
    
    def test_task_state_cancelled(self):
        """Test CANCELLED state exists."""
        from praisonaiagents.ui.a2a.types import TaskState
        assert TaskState.CANCELLED == "cancelled"
    
    def test_task_state_input_required(self):
        """Test INPUT_REQUIRED state exists."""
        from praisonaiagents.ui.a2a.types import TaskState
        assert TaskState.INPUT_REQUIRED == "input_required"
    
    def test_task_state_auth_required(self):
        """Test AUTH_REQUIRED state exists."""
        from praisonaiagents.ui.a2a.types import TaskState
        assert TaskState.AUTH_REQUIRED == "auth_required"


class TestRole:
    """Tests for Role enum."""
    
    def test_role_user(self):
        """Test USER role exists."""
        from praisonaiagents.ui.a2a.types import Role
        assert Role.USER == "user"
    
    def test_role_agent(self):
        """Test AGENT role exists."""
        from praisonaiagents.ui.a2a.types import Role
        assert Role.AGENT == "agent"


class TestPart:
    """Tests for Part models."""
    
    def test_text_part_creation(self):
        """Test TextPart can be created."""
        from praisonaiagents.ui.a2a.types import TextPart
        part = TextPart(text="Hello, world!")
        assert part.text == "Hello, world!"
    
    def test_file_part_with_uri(self):
        """Test FilePart with URI."""
        from praisonaiagents.ui.a2a.types import FilePart
        part = FilePart(
            file_uri="https://example.com/file.pdf",
            media_type="application/pdf",
            name="document.pdf"
        )
        assert part.file_uri == "https://example.com/file.pdf"
        assert part.media_type == "application/pdf"
    
    def test_file_part_with_bytes(self):
        """Test FilePart with bytes."""
        from praisonaiagents.ui.a2a.types import FilePart
        part = FilePart(
            file_bytes=b"file content",
            media_type="text/plain",
            name="test.txt"
        )
        assert part.file_bytes == b"file content"
    
    def test_data_part_creation(self):
        """Test DataPart can be created."""
        from praisonaiagents.ui.a2a.types import DataPart
        part = DataPart(data={"key": "value", "count": 42})
        assert part.data == {"key": "value", "count": 42}


class TestMessage:
    """Tests for Message model."""
    
    def test_message_creation(self):
        """Test Message can be created."""
        from praisonaiagents.ui.a2a.types import Message, Role, TextPart
        msg = Message(
            message_id="msg-123",
            role=Role.USER,
            parts=[TextPart(text="Hello")]
        )
        assert msg.message_id == "msg-123"
        assert msg.role == Role.USER
        assert len(msg.parts) == 1
    
    def test_message_with_context(self):
        """Test Message with context_id."""
        from praisonaiagents.ui.a2a.types import Message, Role, TextPart
        msg = Message(
            message_id="msg-456",
            role=Role.AGENT,
            parts=[TextPart(text="Response")],
            context_id="ctx-789"
        )
        assert msg.context_id == "ctx-789"
    
    def test_message_with_task(self):
        """Test Message with task_id."""
        from praisonaiagents.ui.a2a.types import Message, Role, TextPart
        msg = Message(
            message_id="msg-789",
            role=Role.AGENT,
            parts=[TextPart(text="Working on it")],
            task_id="task-123"
        )
        assert msg.task_id == "task-123"


class TestTaskStatus:
    """Tests for TaskStatus model."""
    
    def test_task_status_creation(self):
        """Test TaskStatus can be created."""
        from praisonaiagents.ui.a2a.types import TaskStatus, TaskState
        status = TaskStatus(state=TaskState.WORKING)
        assert status.state == TaskState.WORKING
    
    def test_task_status_with_message(self):
        """Test TaskStatus with message."""
        from praisonaiagents.ui.a2a.types import TaskStatus, TaskState, Message, Role, TextPart
        msg = Message(
            message_id="msg-1",
            role=Role.AGENT,
            parts=[TextPart(text="Processing...")]
        )
        status = TaskStatus(state=TaskState.WORKING, message=msg)
        assert status.message is not None
    
    def test_task_status_with_timestamp(self):
        """Test TaskStatus with timestamp."""
        from praisonaiagents.ui.a2a.types import TaskStatus, TaskState
        ts = datetime.utcnow().isoformat()
        status = TaskStatus(state=TaskState.COMPLETED, timestamp=ts)
        assert status.timestamp == ts


class TestTask:
    """Tests for Task model."""
    
    def test_task_creation(self):
        """Test Task can be created."""
        from praisonaiagents.ui.a2a.types import Task, TaskStatus, TaskState
        task = Task(
            id="task-123",
            status=TaskStatus(state=TaskState.SUBMITTED)
        )
        assert task.id == "task-123"
        assert task.status.state == TaskState.SUBMITTED
    
    def test_task_with_context(self):
        """Test Task with context_id."""
        from praisonaiagents.ui.a2a.types import Task, TaskStatus, TaskState
        task = Task(
            id="task-456",
            context_id="ctx-789",
            status=TaskStatus(state=TaskState.WORKING)
        )
        assert task.context_id == "ctx-789"
    
    def test_task_with_artifacts(self):
        """Test Task with artifacts."""
        from praisonaiagents.ui.a2a.types import Task, TaskStatus, TaskState, Artifact, TextPart
        artifact = Artifact(
            artifact_id="art-1",
            parts=[TextPart(text="Result")]
        )
        task = Task(
            id="task-789",
            status=TaskStatus(state=TaskState.COMPLETED),
            artifacts=[artifact]
        )
        assert len(task.artifacts) == 1
    
    def test_task_with_history(self):
        """Test Task with message history."""
        from praisonaiagents.ui.a2a.types import Task, TaskStatus, TaskState, Message, Role, TextPart
        msg1 = Message(message_id="m1", role=Role.USER, parts=[TextPart(text="Q")])
        msg2 = Message(message_id="m2", role=Role.AGENT, parts=[TextPart(text="A")])
        task = Task(
            id="task-abc",
            status=TaskStatus(state=TaskState.COMPLETED),
            history=[msg1, msg2]
        )
        assert len(task.history) == 2


class TestArtifact:
    """Tests for Artifact model."""
    
    def test_artifact_creation(self):
        """Test Artifact can be created."""
        from praisonaiagents.ui.a2a.types import Artifact, TextPart
        artifact = Artifact(
            artifact_id="art-123",
            parts=[TextPart(text="Generated content")]
        )
        assert artifact.artifact_id == "art-123"
    
    def test_artifact_with_name(self):
        """Test Artifact with name and description."""
        from praisonaiagents.ui.a2a.types import Artifact, TextPart
        artifact = Artifact(
            artifact_id="art-456",
            name="Report",
            description="Generated report",
            parts=[TextPart(text="Report content")]
        )
        assert artifact.name == "Report"
        assert artifact.description == "Generated report"


class TestAgentSkill:
    """Tests for AgentSkill model."""
    
    def test_agent_skill_creation(self):
        """Test AgentSkill can be created."""
        from praisonaiagents.ui.a2a.types import AgentSkill
        skill = AgentSkill(
            id="search",
            name="Web Search",
            description="Search the web for information"
        )
        assert skill.id == "search"
        assert skill.name == "Web Search"
    
    def test_agent_skill_with_tags(self):
        """Test AgentSkill with tags."""
        from praisonaiagents.ui.a2a.types import AgentSkill
        skill = AgentSkill(
            id="calc",
            name="Calculator",
            description="Perform calculations",
            tags=["math", "utility"]
        )
        assert skill.tags == ["math", "utility"]
    
    def test_agent_skill_with_examples(self):
        """Test AgentSkill with examples."""
        from praisonaiagents.ui.a2a.types import AgentSkill
        skill = AgentSkill(
            id="translate",
            name="Translator",
            description="Translate text",
            examples=["Translate hello to Spanish", "What is bonjour in English?"]
        )
        assert len(skill.examples) == 2


class TestAgentCapabilities:
    """Tests for AgentCapabilities model."""
    
    def test_capabilities_creation(self):
        """Test AgentCapabilities can be created."""
        from praisonaiagents.ui.a2a.types import AgentCapabilities
        caps = AgentCapabilities(streaming=True)
        assert caps.streaming is True
    
    def test_capabilities_defaults(self):
        """Test AgentCapabilities defaults."""
        from praisonaiagents.ui.a2a.types import AgentCapabilities
        caps = AgentCapabilities()
        assert caps.streaming is False
        assert caps.push_notifications is False


class TestAgentCard:
    """Tests for AgentCard model."""
    
    def test_agent_card_creation(self):
        """Test AgentCard can be created."""
        from praisonaiagents.ui.a2a.types import AgentCard, AgentCapabilities
        card = AgentCard(
            name="Research Agent",
            url="http://localhost:8000/a2a",
            version="1.0.0",
            capabilities=AgentCapabilities(streaming=True)
        )
        assert card.name == "Research Agent"
        assert card.url == "http://localhost:8000/a2a"
    
    def test_agent_card_with_skills(self):
        """Test AgentCard with skills."""
        from praisonaiagents.ui.a2a.types import AgentCard, AgentCapabilities, AgentSkill
        skill = AgentSkill(id="search", name="Search", description="Search web")
        card = AgentCard(
            name="Search Agent",
            url="http://localhost:8000/a2a",
            version="1.0.0",
            capabilities=AgentCapabilities(),
            skills=[skill]
        )
        assert len(card.skills) == 1
    
    def test_agent_card_json_serialization(self):
        """Test AgentCard can be serialized to JSON."""
        from praisonaiagents.ui.a2a.types import AgentCard, AgentCapabilities
        card = AgentCard(
            name="Test Agent",
            url="http://localhost:8000/a2a",
            version="1.0.0",
            capabilities=AgentCapabilities()
        )
        json_str = card.model_dump_json()
        data = json.loads(json_str)
        assert data["name"] == "Test Agent"


class TestSendMessageRequest:
    """Tests for SendMessageRequest model."""
    
    def test_send_message_request_creation(self):
        """Test SendMessageRequest can be created."""
        from praisonaiagents.ui.a2a.types import SendMessageRequest, Message, Role, TextPart
        msg = Message(
            message_id="msg-1",
            role=Role.USER,
            parts=[TextPart(text="Hello")]
        )
        req = SendMessageRequest(message=msg)
        assert req.message.message_id == "msg-1"
    
    def test_send_message_request_with_config(self):
        """Test SendMessageRequest with configuration."""
        from praisonaiagents.ui.a2a.types import SendMessageRequest, Message, Role, TextPart, MessageConfig
        msg = Message(
            message_id="msg-2",
            role=Role.USER,
            parts=[TextPart(text="Search for AI")]
        )
        config = MessageConfig(
            accept_content_types=["text/plain", "application/json"]
        )
        req = SendMessageRequest(message=msg, configuration=config)
        assert req.configuration is not None


class TestStreamingEvents:
    """Tests for streaming event models."""
    
    def test_task_status_update_event(self):
        """Test TaskStatusUpdateEvent creation."""
        from praisonaiagents.ui.a2a.types import TaskStatusUpdateEvent, TaskStatus, TaskState
        event = TaskStatusUpdateEvent(
            task_id="task-123",
            status=TaskStatus(state=TaskState.WORKING),
            final=False
        )
        assert event.task_id == "task-123"
        assert event.final is False
    
    def test_task_artifact_update_event(self):
        """Test TaskArtifactUpdateEvent creation."""
        from praisonaiagents.ui.a2a.types import TaskArtifactUpdateEvent, Artifact, TextPart
        artifact = Artifact(
            artifact_id="art-1",
            parts=[TextPart(text="Partial result")]
        )
        event = TaskArtifactUpdateEvent(
            task_id="task-456",
            artifact=artifact,
            append=True,
            last_chunk=False
        )
        assert event.append is True
        assert event.last_chunk is False
