"""
Tests for the Message Parts module.

TDD: Tests written before implementation verification.
"""

import pytest
import time

from praisonaiagents.session.parts import (
    PartType,
    ToolStatus,
    TextPart,
    ToolPart,
    ReasoningPart,
    FilePart,
    ImagePart,
    CompactionPart,
    ErrorPart,
    StructuredMessage,
    part_from_dict,
)


class TestPartType:
    """Tests for PartType enum."""
    
    def test_part_type_values(self):
        """Test that part types have correct values."""
        assert PartType.TEXT.value == "text"
        assert PartType.TOOL.value == "tool"
        assert PartType.REASONING.value == "reasoning"
        assert PartType.FILE.value == "file"
        assert PartType.IMAGE.value == "image"
        assert PartType.COMPACTION.value == "compaction"
        assert PartType.ERROR.value == "error"


class TestToolStatus:
    """Tests for ToolStatus enum."""
    
    def test_tool_status_values(self):
        """Test that tool statuses have correct values."""
        assert ToolStatus.PENDING.value == "pending"
        assert ToolStatus.RUNNING.value == "running"
        assert ToolStatus.COMPLETED.value == "completed"
        assert ToolStatus.ERROR.value == "error"


class TestTextPart:
    """Tests for TextPart."""
    
    def test_text_part_creation(self):
        """Test basic text part creation."""
        part = TextPart(text="Hello, world!")
        
        assert part.type == PartType.TEXT
        assert part.text == "Hello, world!"
        assert part.id is not None
        assert part.created_at > 0
    
    def test_text_part_to_dict(self):
        """Test text part serialization."""
        part = TextPart(text="Test content")
        d = part.to_dict()
        
        assert d["type"] == "text"
        assert d["text"] == "Test content"
        assert "id" in d
    
    def test_text_part_from_dict(self):
        """Test text part deserialization."""
        d = {"type": "text", "text": "Test content", "id": "test-id"}
        part = TextPart.from_dict(d)
        
        assert part.text == "Test content"
        assert part.id == "test-id"


class TestToolPart:
    """Tests for ToolPart."""
    
    def test_tool_part_creation(self):
        """Test basic tool part creation."""
        part = ToolPart(
            tool_name="bash",
            tool_call_id="call_123",
            input={"command": "ls -la"}
        )
        
        assert part.type == PartType.TOOL
        assert part.tool_name == "bash"
        assert part.tool_call_id == "call_123"
        assert part.status == ToolStatus.PENDING
        assert part.input == {"command": "ls -la"}
    
    def test_tool_part_start(self):
        """Test starting a tool."""
        part = ToolPart(tool_name="bash", tool_call_id="call_123")
        original_updated = part.updated_at
        
        time.sleep(0.01)
        part.start()
        
        assert part.status == ToolStatus.RUNNING
        assert part.updated_at > original_updated
    
    def test_tool_part_complete(self):
        """Test completing a tool."""
        part = ToolPart(tool_name="bash", tool_call_id="call_123")
        part.start()
        
        part.complete(
            output="file1.txt\nfile2.txt",
            title="Listed files",
            metadata={"file_count": 2}
        )
        
        assert part.status == ToolStatus.COMPLETED
        assert part.output == "file1.txt\nfile2.txt"
        assert part.title == "Listed files"
        assert part.metadata["file_count"] == 2
    
    def test_tool_part_fail(self):
        """Test failing a tool."""
        part = ToolPart(tool_name="bash", tool_call_id="call_123")
        part.start()
        
        part.fail("Command not found")
        
        assert part.status == ToolStatus.ERROR
        assert part.error == "Command not found"
    
    def test_tool_part_to_dict(self):
        """Test tool part serialization."""
        part = ToolPart(
            tool_name="bash",
            tool_call_id="call_123",
            status=ToolStatus.COMPLETED,
            input={"command": "ls"},
            output="files",
            title="List files"
        )
        
        d = part.to_dict()
        
        assert d["type"] == "tool"
        assert d["tool_name"] == "bash"
        assert d["status"] == "completed"
        assert d["input"] == {"command": "ls"}
        assert d["output"] == "files"
    
    def test_tool_part_from_dict(self):
        """Test tool part deserialization."""
        d = {
            "type": "tool",
            "tool_name": "bash",
            "tool_call_id": "call_123",
            "status": "running",
            "input": {"command": "ls"}
        }
        
        part = ToolPart.from_dict(d)
        
        assert part.tool_name == "bash"
        assert part.status == ToolStatus.RUNNING


class TestReasoningPart:
    """Tests for ReasoningPart."""
    
    def test_reasoning_part_creation(self):
        """Test reasoning part creation."""
        part = ReasoningPart(text="Let me think about this...")
        
        assert part.type == PartType.REASONING
        assert part.text == "Let me think about this..."
    
    def test_reasoning_part_serialization(self):
        """Test reasoning part round-trip."""
        part = ReasoningPart(text="Thinking...")
        d = part.to_dict()
        restored = ReasoningPart.from_dict(d)
        
        assert restored.text == part.text


class TestFilePart:
    """Tests for FilePart."""
    
    def test_file_part_creation(self):
        """Test file part creation."""
        part = FilePart(
            path="/path/to/file.txt",
            name="file.txt",
            mime_type="text/plain",
            size=1024
        )
        
        assert part.type == PartType.FILE
        assert part.path == "/path/to/file.txt"
        assert part.name == "file.txt"
        assert part.mime_type == "text/plain"
        assert part.size == 1024
    
    def test_file_part_serialization(self):
        """Test file part round-trip."""
        part = FilePart(path="/test.txt", name="test.txt")
        d = part.to_dict()
        restored = FilePart.from_dict(d)
        
        assert restored.path == part.path
        assert restored.name == part.name


class TestImagePart:
    """Tests for ImagePart."""
    
    def test_image_part_with_url(self):
        """Test image part with URL."""
        part = ImagePart(url="https://example.com/image.png")
        
        assert part.type == PartType.IMAGE
        assert part.url == "https://example.com/image.png"
    
    def test_image_part_with_base64(self):
        """Test image part with base64."""
        part = ImagePart(base64="iVBORw0KGgo...", mime_type="image/png")
        
        assert part.base64 == "iVBORw0KGgo..."
        assert part.mime_type == "image/png"


class TestCompactionPart:
    """Tests for CompactionPart."""
    
    def test_compaction_part_creation(self):
        """Test compaction part creation."""
        part = CompactionPart(
            summary="Conversation about coding...",
            original_tokens=50000,
            compacted_tokens=10000,
            messages_removed=20
        )
        
        assert part.type == PartType.COMPACTION
        assert part.summary == "Conversation about coding..."
        assert part.original_tokens == 50000
        assert part.compacted_tokens == 10000
        assert part.messages_removed == 20


class TestErrorPart:
    """Tests for ErrorPart."""
    
    def test_error_part_creation(self):
        """Test error part creation."""
        part = ErrorPart(
            error_type="ValueError",
            message="Invalid input",
            stack_trace="Traceback..."
        )
        
        assert part.type == PartType.ERROR
        assert part.error_type == "ValueError"
        assert part.message == "Invalid input"
        assert part.stack_trace == "Traceback..."


class TestPartFromDict:
    """Tests for part_from_dict factory function."""
    
    def test_text_part_from_dict(self):
        """Test creating text part from dict."""
        d = {"type": "text", "text": "Hello"}
        part = part_from_dict(d)
        
        assert isinstance(part, TextPart)
        assert part.text == "Hello"
    
    def test_tool_part_from_dict(self):
        """Test creating tool part from dict."""
        d = {"type": "tool", "tool_name": "bash", "tool_call_id": "123"}
        part = part_from_dict(d)
        
        assert isinstance(part, ToolPart)
        assert part.tool_name == "bash"
    
    def test_unknown_type_defaults_to_text(self):
        """Test that unknown types default to text."""
        d = {"type": "unknown", "text": "Hello"}
        part = part_from_dict(d)
        
        assert isinstance(part, TextPart)


class TestStructuredMessage:
    """Tests for StructuredMessage."""
    
    def test_message_creation(self):
        """Test basic message creation."""
        msg = StructuredMessage(role="assistant")
        
        assert msg.role == "assistant"
        assert msg.parts == []
        assert msg.id is not None
    
    def test_add_text(self):
        """Test adding text part."""
        msg = StructuredMessage(role="assistant")
        part = msg.add_text("Hello, world!")
        
        assert len(msg.parts) == 1
        assert isinstance(part, TextPart)
        assert part.text == "Hello, world!"
    
    def test_add_tool(self):
        """Test adding tool part."""
        msg = StructuredMessage(role="assistant")
        part = msg.add_tool(
            tool_name="bash",
            tool_call_id="call_123",
            input={"command": "ls"}
        )
        
        assert len(msg.parts) == 1
        assert isinstance(part, ToolPart)
        assert part.tool_name == "bash"
    
    def test_add_reasoning(self):
        """Test adding reasoning part."""
        msg = StructuredMessage(role="assistant")
        part = msg.add_reasoning("Let me think...")
        
        assert isinstance(part, ReasoningPart)
    
    def test_add_file(self):
        """Test adding file part."""
        msg = StructuredMessage(role="assistant")
        part = msg.add_file(path="/test.txt", name="test.txt")
        
        assert isinstance(part, FilePart)
    
    def test_add_image(self):
        """Test adding image part."""
        msg = StructuredMessage(role="assistant")
        part = msg.add_image(url="https://example.com/img.png")
        
        assert isinstance(part, ImagePart)
    
    def test_add_error(self):
        """Test adding error part."""
        msg = StructuredMessage(role="assistant")
        part = msg.add_error("ValueError", "Invalid input")
        
        assert isinstance(part, ErrorPart)
    
    def test_get_part(self):
        """Test getting part by ID."""
        msg = StructuredMessage(role="assistant")
        part = msg.add_text("Hello")
        
        found = msg.get_part(part.id)
        
        assert found is part
    
    def test_get_part_not_found(self):
        """Test getting non-existent part."""
        msg = StructuredMessage(role="assistant")
        
        found = msg.get_part("nonexistent")
        
        assert found is None
    
    def test_get_parts_by_type(self):
        """Test getting parts by type."""
        msg = StructuredMessage(role="assistant")
        msg.add_text("Text 1")
        msg.add_tool("bash", "call_1")
        msg.add_text("Text 2")
        
        text_parts = msg.get_parts_by_type(PartType.TEXT)
        
        assert len(text_parts) == 2
    
    def test_get_text_content(self):
        """Test getting combined text content."""
        msg = StructuredMessage(role="assistant")
        msg.add_text("Hello")
        msg.add_tool("bash", "call_1")
        msg.add_text("World")
        
        content = msg.get_text_content()
        
        assert content == "Hello\nWorld"
    
    def test_get_tool_parts(self):
        """Test getting tool parts."""
        msg = StructuredMessage(role="assistant")
        msg.add_text("Text")
        msg.add_tool("bash", "call_1")
        msg.add_tool("read", "call_2")
        
        tools = msg.get_tool_parts()
        
        assert len(tools) == 2
        assert all(isinstance(t, ToolPart) for t in tools)
    
    def test_message_to_dict(self):
        """Test message serialization."""
        msg = StructuredMessage(
            role="assistant",
            session_id="session_123",
            agent_name="test_agent"
        )
        msg.add_text("Hello")
        
        d = msg.to_dict()
        
        assert d["role"] == "assistant"
        assert d["session_id"] == "session_123"
        assert d["agent_name"] == "test_agent"
        assert len(d["parts"]) == 1
    
    def test_message_from_dict(self):
        """Test message deserialization."""
        d = {
            "id": "msg_123",
            "role": "assistant",
            "parts": [
                {"type": "text", "text": "Hello"},
                {"type": "tool", "tool_name": "bash", "tool_call_id": "call_1"}
            ],
            "session_id": "session_123"
        }
        
        msg = StructuredMessage.from_dict(d)
        
        assert msg.id == "msg_123"
        assert msg.role == "assistant"
        assert len(msg.parts) == 2
        assert msg.session_id == "session_123"
    
    def test_message_to_llm_message(self):
        """Test converting to LLM format."""
        msg = StructuredMessage(role="assistant")
        msg.add_text("Hello")
        msg.add_tool("bash", "call_1")
        msg.add_text("World")
        
        llm_msg = msg.to_llm_message()
        
        assert llm_msg["role"] == "assistant"
        assert llm_msg["content"] == "Hello\nWorld"
    
    def test_message_updates_timestamp(self):
        """Test that adding parts updates timestamp."""
        msg = StructuredMessage(role="assistant")
        original = msg.updated_at
        
        time.sleep(0.01)
        msg.add_text("Hello")
        
        assert msg.updated_at > original
