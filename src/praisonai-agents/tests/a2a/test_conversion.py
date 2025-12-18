"""
Tests for A2A Message Conversion

TDD: Write tests first, then implement conversion module.
"""


class TestA2AToPraisonAI:
    """Tests for converting A2A messages to PraisonAI format."""
    
    def test_convert_user_message(self):
        """Test converting A2A user message to PraisonAI format."""
        from praisonaiagents.ui.a2a.conversion import a2a_to_praisonai_messages
        from praisonaiagents.ui.a2a.types import Message, Role, TextPart
        
        a2a_msg = Message(
            message_id="msg-1",
            role=Role.USER,
            parts=[TextPart(text="Hello, how are you?")]
        )
        
        result = a2a_to_praisonai_messages([a2a_msg])
        
        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "Hello, how are you?"
    
    def test_convert_agent_message(self):
        """Test converting A2A agent message to PraisonAI format."""
        from praisonaiagents.ui.a2a.conversion import a2a_to_praisonai_messages
        from praisonaiagents.ui.a2a.types import Message, Role, TextPart
        
        a2a_msg = Message(
            message_id="msg-2",
            role=Role.AGENT,
            parts=[TextPart(text="I'm doing well, thanks!")]
        )
        
        result = a2a_to_praisonai_messages([a2a_msg])
        
        assert len(result) == 1
        assert result[0]["role"] == "assistant"
        assert result[0]["content"] == "I'm doing well, thanks!"
    
    def test_convert_multiple_parts(self):
        """Test converting message with multiple text parts."""
        from praisonaiagents.ui.a2a.conversion import a2a_to_praisonai_messages
        from praisonaiagents.ui.a2a.types import Message, Role, TextPart
        
        a2a_msg = Message(
            message_id="msg-3",
            role=Role.USER,
            parts=[
                TextPart(text="First part."),
                TextPart(text="Second part.")
            ]
        )
        
        result = a2a_to_praisonai_messages([a2a_msg])
        
        assert "First part" in result[0]["content"]
        assert "Second part" in result[0]["content"]
    
    def test_convert_conversation_history(self):
        """Test converting full conversation history."""
        from praisonaiagents.ui.a2a.conversion import a2a_to_praisonai_messages
        from praisonaiagents.ui.a2a.types import Message, Role, TextPart
        
        messages = [
            Message(message_id="m1", role=Role.USER, parts=[TextPart(text="Hi")]),
            Message(message_id="m2", role=Role.AGENT, parts=[TextPart(text="Hello!")]),
            Message(message_id="m3", role=Role.USER, parts=[TextPart(text="How are you?")]),
        ]
        
        result = a2a_to_praisonai_messages(messages)
        
        assert len(result) == 3
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "assistant"
        assert result[2]["role"] == "user"


class TestPraisonAIToA2A:
    """Tests for converting PraisonAI responses to A2A format."""
    
    def test_convert_string_response(self):
        """Test converting string response to A2A Message."""
        from praisonaiagents.ui.a2a.conversion import praisonai_to_a2a_message
        
        response = "This is the agent's response."
        
        result = praisonai_to_a2a_message(response)
        
        assert result.role.value == "agent"
        assert len(result.parts) == 1
        assert result.parts[0].text == response
    
    def test_convert_response_with_context(self):
        """Test converting response with context_id."""
        from praisonaiagents.ui.a2a.conversion import praisonai_to_a2a_message
        
        response = "Response text"
        
        result = praisonai_to_a2a_message(response, context_id="ctx-123")
        
        assert result.context_id == "ctx-123"
    
    def test_convert_response_with_task(self):
        """Test converting response with task_id."""
        from praisonaiagents.ui.a2a.conversion import praisonai_to_a2a_message
        
        response = "Response text"
        
        result = praisonai_to_a2a_message(response, task_id="task-456")
        
        assert result.task_id == "task-456"


class TestArtifactConversion:
    """Tests for converting responses to A2A Artifacts."""
    
    def test_create_artifact_from_response(self):
        """Test creating Artifact from response."""
        from praisonaiagents.ui.a2a.conversion import create_artifact
        
        response = "Generated content here."
        
        artifact = create_artifact(response)
        
        assert artifact.artifact_id is not None
        assert len(artifact.parts) == 1
        assert artifact.parts[0].text == response
    
    def test_create_artifact_with_name(self):
        """Test creating Artifact with name."""
        from praisonaiagents.ui.a2a.conversion import create_artifact
        
        response = "Report content"
        
        artifact = create_artifact(response, name="Report", description="Generated report")
        
        assert artifact.name == "Report"
        assert artifact.description == "Generated report"


class TestExtractUserInput:
    """Tests for extracting user input from A2A messages."""
    
    def test_extract_from_single_message(self):
        """Test extracting user input from single message."""
        from praisonaiagents.ui.a2a.conversion import extract_user_input
        from praisonaiagents.ui.a2a.types import Message, Role, TextPart
        
        msg = Message(
            message_id="m1",
            role=Role.USER,
            parts=[TextPart(text="What is AI?")]
        )
        
        result = extract_user_input([msg])
        
        assert result == "What is AI?"
    
    def test_extract_from_conversation(self):
        """Test extracting last user input from conversation."""
        from praisonaiagents.ui.a2a.conversion import extract_user_input
        from praisonaiagents.ui.a2a.types import Message, Role, TextPart
        
        messages = [
            Message(message_id="m1", role=Role.USER, parts=[TextPart(text="First question")]),
            Message(message_id="m2", role=Role.AGENT, parts=[TextPart(text="Answer")]),
            Message(message_id="m3", role=Role.USER, parts=[TextPart(text="Follow up question")]),
        ]
        
        result = extract_user_input(messages)
        
        assert result == "Follow up question"
    
    def test_extract_empty_when_no_user_message(self):
        """Test extracting returns empty when no user message."""
        from praisonaiagents.ui.a2a.conversion import extract_user_input
        from praisonaiagents.ui.a2a.types import Message, Role, TextPart
        
        messages = [
            Message(message_id="m1", role=Role.AGENT, parts=[TextPart(text="Hello")]),
        ]
        
        result = extract_user_input(messages)
        
        assert result == ""
