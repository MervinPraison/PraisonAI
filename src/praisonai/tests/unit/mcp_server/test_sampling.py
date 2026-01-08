"""
Unit tests for MCP Sampling API

Tests for SamplingRequest, SamplingResponse, and SamplingHandler classes.
"""

import asyncio


class TestToolChoiceType:
    """Tests for ToolChoiceType (ToolChoiceMode) enum."""
    
    def test_tool_choice_types(self):
        """Test tool choice type values per MCP 2025-11-25 spec."""
        from praisonai.mcp_server.sampling import ToolChoiceType
        
        assert ToolChoiceType.AUTO.value == "auto"
        assert ToolChoiceType.NONE.value == "none"
        assert ToolChoiceType.ANY.value == "any"
        assert ToolChoiceType.TOOL.value == "tool"


class TestToolDefinition:
    """Tests for ToolDefinition dataclass."""
    
    def test_tool_definition(self):
        """Test tool definition creation."""
        from praisonai.mcp_server.sampling import ToolDefinition
        
        tool = ToolDefinition(
            name="search",
            description="Search the web",
            input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
        )
        
        assert tool.name == "search"
        assert tool.description == "Search the web"
    
    def test_tool_definition_to_dict(self):
        """Test tool definition serialization."""
        from praisonai.mcp_server.sampling import ToolDefinition
        
        tool = ToolDefinition(
            name="search",
            description="Search",
            input_schema={"type": "object"},
        )
        
        result = tool.to_dict()
        
        assert result["name"] == "search"
        assert result["inputSchema"] == {"type": "object"}


class TestToolChoice:
    """Tests for ToolChoice dataclass."""
    
    def test_tool_choice_auto(self):
        """Test auto tool choice."""
        from praisonai.mcp_server.sampling import ToolChoice, ToolChoiceType
        
        choice = ToolChoice.auto()
        result = choice.to_dict()
        
        assert result["mode"] == "auto"
    
    def test_tool_choice_specific(self):
        """Test specific tool choice (TOOL mode)."""
        from praisonai.mcp_server.sampling import ToolChoice, ToolChoiceType
        
        choice = ToolChoice.tool("search")
        result = choice.to_dict()
        
        assert result["mode"] == "tool"
        assert result["name"] == "search"


class TestSamplingMessage:
    """Tests for SamplingMessage dataclass."""
    
    def test_message_creation(self):
        """Test message creation."""
        from praisonai.mcp_server.sampling import SamplingMessage
        
        msg = SamplingMessage(role="user", content="Hello")
        
        assert msg.role == "user"
        assert msg.content == "Hello"
    
    def test_message_to_dict(self):
        """Test message serialization."""
        from praisonai.mcp_server.sampling import SamplingMessage
        
        msg = SamplingMessage(role="user", content="Hello")
        result = msg.to_dict()
        
        assert result["role"] == "user"
        assert result["content"]["type"] == "text"
        assert result["content"]["text"] == "Hello"


class TestModelPreferences:
    """Tests for ModelPreferences dataclass."""
    
    def test_model_preferences(self):
        """Test model preferences creation."""
        from praisonai.mcp_server.sampling import ModelPreferences
        
        prefs = ModelPreferences(
            hints=[{"name": "gpt-4"}],
            cost_priority=0.5,
        )
        
        assert prefs.hints == [{"name": "gpt-4"}]
        assert prefs.cost_priority == 0.5
    
    def test_model_preferences_to_dict(self):
        """Test model preferences serialization."""
        from praisonai.mcp_server.sampling import ModelPreferences
        
        prefs = ModelPreferences(
            cost_priority=0.3,
            speed_priority=0.7,
        )
        result = prefs.to_dict()
        
        assert result["costPriority"] == 0.3
        assert result["speedPriority"] == 0.7


class TestSamplingRequest:
    """Tests for SamplingRequest dataclass."""
    
    def test_basic_request(self):
        """Test basic sampling request."""
        from praisonai.mcp_server.sampling import SamplingRequest, SamplingMessage
        
        request = SamplingRequest(
            messages=[SamplingMessage(role="user", content="Hello")],
            max_tokens=100,
        )
        
        assert len(request.messages) == 1
        assert request.max_tokens == 100
    
    def test_request_with_tools(self):
        """Test request with tools."""
        from praisonai.mcp_server.sampling import (
            SamplingRequest, SamplingMessage, ToolDefinition, ToolChoice, ToolChoiceType
        )
        
        request = SamplingRequest(
            messages=[SamplingMessage(role="user", content="Search for AI")],
            tools=[ToolDefinition(name="search", description="Search", input_schema={})],
            tool_choice=ToolChoice.auto(),
        )
        
        assert len(request.tools) == 1
        assert request.tool_choice.mode == ToolChoiceType.AUTO
    
    def test_request_to_dict(self):
        """Test request serialization."""
        from praisonai.mcp_server.sampling import SamplingRequest, SamplingMessage
        
        request = SamplingRequest(
            messages=[SamplingMessage(role="user", content="Hello")],
            system_prompt="You are helpful",
            max_tokens=100,
            temperature=0.7,
        )
        
        result = request.to_dict()
        
        assert len(result["messages"]) == 1
        assert result["systemPrompt"] == "You are helpful"
        assert result["maxTokens"] == 100
        assert result["temperature"] == 0.7


class TestToolCall:
    """Tests for ToolCall dataclass."""
    
    def test_tool_call_from_dict(self):
        """Test tool call from dictionary."""
        from praisonai.mcp_server.sampling import ToolCall
        
        data = {
            "id": "call-123",
            "name": "search",
            "arguments": {"query": "AI"},
        }
        
        call = ToolCall.from_dict(data)
        
        assert call.id == "call-123"
        assert call.name == "search"
        assert call.arguments == {"query": "AI"}


class TestSamplingResponse:
    """Tests for SamplingResponse dataclass."""
    
    def test_basic_response(self):
        """Test basic sampling response."""
        from praisonai.mcp_server.sampling import SamplingResponse
        
        response = SamplingResponse(
            role="assistant",
            content="Hello! How can I help?",
            model="gpt-4",
            stop_reason="end_turn",
        )
        
        assert response.role == "assistant"
        assert response.content == "Hello! How can I help?"
        assert response.model == "gpt-4"
    
    def test_response_with_tool_calls(self):
        """Test response with tool calls."""
        from praisonai.mcp_server.sampling import SamplingResponse, ToolCall
        
        response = SamplingResponse(
            role="assistant",
            content="",
            tool_calls=[ToolCall(id="call-1", name="search", arguments={"q": "AI"})],
        )
        
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "search"
    
    def test_response_to_dict(self):
        """Test response serialization."""
        from praisonai.mcp_server.sampling import SamplingResponse
        
        response = SamplingResponse(
            role="assistant",
            content="Hello",
            model="gpt-4",
        )
        
        result = response.to_dict()
        
        assert result["role"] == "assistant"
        assert result["content"]["text"] == "Hello"
        assert result["model"] == "gpt-4"
    
    def test_response_from_dict(self):
        """Test response from dictionary."""
        from praisonai.mcp_server.sampling import SamplingResponse
        
        data = {
            "role": "assistant",
            "content": {"type": "text", "text": "Hello"},
            "model": "gpt-4",
            "stopReason": "end_turn",
        }
        
        response = SamplingResponse.from_dict(data)
        
        assert response.role == "assistant"
        assert response.content == "Hello"
        assert response.stop_reason == "end_turn"


class TestSamplingHandler:
    """Tests for SamplingHandler class."""
    
    def test_handler_init(self):
        """Test handler initialization."""
        from praisonai.mcp_server.sampling import SamplingHandler
        
        handler = SamplingHandler(default_model="gpt-4")
        
        assert handler._default_model == "gpt-4"
    
    def test_handler_with_callback(self):
        """Test handler with custom callback."""
        from praisonai.mcp_server.sampling import (
            SamplingHandler, SamplingRequest, SamplingMessage, SamplingResponse
        )
        
        async def custom_callback(request):
            return SamplingResponse(
                role="assistant",
                content="Custom response",
            )
        
        handler = SamplingHandler(callback=custom_callback)
        
        request = SamplingRequest(
            messages=[SamplingMessage(role="user", content="Hello")],
        )
        
        response = asyncio.run(handler.create_message(request))
        
        assert response.content == "Custom response"
    
    def test_set_callback(self):
        """Test setting callback."""
        from praisonai.mcp_server.sampling import (
            SamplingHandler, SamplingResponse
        )
        
        async def callback(request):
            return SamplingResponse(role="assistant", content="Test")
        
        handler = SamplingHandler()
        handler.set_callback(callback)
        
        assert handler._callback is not None


class TestSamplingHelpers:
    """Tests for sampling helper functions."""
    
    def test_create_sampling_request(self):
        """Test create_sampling_request helper."""
        from praisonai.mcp_server.sampling import create_sampling_request
        
        request = create_sampling_request(
            prompt="Hello",
            system_prompt="You are helpful",
            max_tokens=100,
        )
        
        assert len(request.messages) == 1
        assert request.messages[0].content == "Hello"
        assert request.system_prompt == "You are helpful"
        assert request.max_tokens == 100
    
    def test_create_sampling_request_with_tools(self):
        """Test create_sampling_request with tools."""
        from praisonai.mcp_server.sampling import create_sampling_request, ToolChoiceType
        
        request = create_sampling_request(
            prompt="Search for AI",
            tools=[{"name": "search", "description": "Search", "inputSchema": {}}],
            tool_choice="auto",
        )
        
        assert len(request.tools) == 1
        assert request.tools[0].name == "search"
        assert request.tool_choice.type == ToolChoiceType.AUTO
    
    def test_create_sampling_request_specific_tool(self):
        """Test create_sampling_request with specific tool choice."""
        from praisonai.mcp_server.sampling import create_sampling_request, ToolChoiceType
        
        request = create_sampling_request(
            prompt="Search",
            tools=[{"name": "search", "description": "Search", "inputSchema": {}}],
            tool_choice="search",
        )
        
        assert request.tool_choice.mode == ToolChoiceType.TOOL
        assert request.tool_choice.name == "search"


class TestGlobalSamplingHandler:
    """Tests for global sampling handler functions."""
    
    def test_get_sampling_handler(self):
        """Test getting global handler."""
        from praisonai.mcp_server.sampling import get_sampling_handler, SamplingHandler
        
        handler = get_sampling_handler()
        
        assert isinstance(handler, SamplingHandler)
    
    def test_set_sampling_handler(self):
        """Test setting global handler."""
        from praisonai.mcp_server.sampling import (
            get_sampling_handler, set_sampling_handler, SamplingHandler
        )
        
        custom_handler = SamplingHandler(default_model="custom-model")
        set_sampling_handler(custom_handler)
        
        retrieved = get_sampling_handler()
        
        assert retrieved is custom_handler
        assert retrieved._default_model == "custom-model"
