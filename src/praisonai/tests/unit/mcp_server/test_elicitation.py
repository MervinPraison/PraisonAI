"""
Unit tests for MCP Elicitation API

Tests for ElicitationHandler, ElicitationRequest, and ElicitationResult classes.
"""


class TestElicitationMode:
    """Tests for ElicitationMode enum."""
    
    def test_elicitation_modes(self):
        """Test elicitation mode values."""
        from praisonai.mcp_server.elicitation import ElicitationMode
        
        assert ElicitationMode.FORM.value == "form"
        assert ElicitationMode.URL.value == "url"


class TestElicitationStatus:
    """Tests for ElicitationStatus enum."""
    
    def test_elicitation_statuses(self):
        """Test elicitation status values (maps to ElicitationAction)."""
        from praisonai.mcp_server.elicitation import ElicitationStatus
        
        # ElicitationStatus is deprecated and maps to ElicitationAction values
        assert ElicitationStatus.COMPLETED.value == "accept"
        assert ElicitationStatus.CANCELLED.value == "cancel"
        assert ElicitationStatus.TIMEOUT.value == "cancel"
        assert ElicitationStatus.ERROR.value == "decline"


class TestElicitationSchema:
    """Tests for ElicitationSchema dataclass."""
    
    def test_schema_creation(self):
        """Test schema creation."""
        from praisonai.mcp_server.elicitation import ElicitationSchema
        
        schema = ElicitationSchema(
            properties={"name": {"type": "string"}},
            required=["name"],
            title="User Info",
        )
        
        assert schema.type == "object"
        assert "name" in schema.properties
        assert "name" in schema.required
        assert schema.title == "User Info"
    
    def test_schema_to_dict(self):
        """Test schema serialization."""
        from praisonai.mcp_server.elicitation import ElicitationSchema
        
        schema = ElicitationSchema(
            properties={"name": {"type": "string"}},
            required=["name"],
        )
        
        result = schema.to_dict()
        
        assert result["type"] == "object"
        assert "properties" in result
        assert "required" in result


class TestElicitationRequest:
    """Tests for ElicitationRequest dataclass per MCP 2025-11-25 spec."""
    
    def test_form_request(self):
        """Test form mode request."""
        from praisonai.mcp_server.elicitation import (
            ElicitationRequest, ElicitationMode, ElicitationSchema
        )
        
        schema = ElicitationSchema(properties={"name": {"type": "string"}})
        request = ElicitationRequest(
            elicitation_id="elicit-123",
            mode=ElicitationMode.FORM,
            message="Please provide your name",
            requested_schema=schema,
        )
        
        assert request.id == "elicit-123"
        assert request.mode == ElicitationMode.FORM
        assert request.schema is not None
    
    def test_url_request(self):
        """Test URL mode request."""
        from praisonai.mcp_server.elicitation import ElicitationRequest, ElicitationMode
        
        request = ElicitationRequest(
            elicitation_id="elicit-456",
            mode=ElicitationMode.URL,
            message="Please authenticate",
            url="https://auth.example.com/login",
        )
        
        assert request.mode == ElicitationMode.URL
        assert request.url == "https://auth.example.com/login"
    
    def test_request_to_dict(self):
        """Test request serialization."""
        from praisonai.mcp_server.elicitation import ElicitationRequest, ElicitationMode
        
        request = ElicitationRequest(
            elicitation_id="elicit-789",
            mode=ElicitationMode.URL,
            message="Test",
            url="https://example.com",
            timeout=60,
        )
        
        result = request.to_dict()
        
        assert result["message"] == "Test"
        assert result["mode"] == "url"
        assert result["url"] == "https://example.com"


class TestElicitationResult:
    """Tests for ElicitationResult dataclass per MCP 2025-11-25 spec."""
    
    def test_completed_result(self):
        """Test completed (accept) result."""
        from praisonai.mcp_server.elicitation import ElicitationResult, ElicitationAction
        
        result = ElicitationResult.accept({"name": "John"})
        
        assert result.action == ElicitationAction.ACCEPT
        assert result.content == {"name": "John"}
    
    def test_error_result(self):
        """Test error (decline) result."""
        from praisonai.mcp_server.elicitation import ElicitationResult, ElicitationAction
        
        result = ElicitationResult.decline("Validation failed")
        
        assert result.action == ElicitationAction.DECLINE
        assert result.validation_error == "Validation failed"
    
    def test_result_to_dict(self):
        """Test result serialization."""
        from praisonai.mcp_server.elicitation import ElicitationResult
        
        result = ElicitationResult.accept({"confirmed": True})
        
        output = result.to_dict()
        
        assert output["action"] == "accept"
        assert output["content"] == {"confirmed": True}


class TestElicitationHandler:
    """Tests for ElicitationHandler class."""
    
    def test_handler_init(self):
        """Test handler initialization."""
        from praisonai.mcp_server.elicitation import ElicitationHandler
        
        handler = ElicitationHandler(interactive=False, ci_mode=True)
        
        assert handler.interactive is False
        assert handler.ci_mode is True
    
    def test_handler_ci_mode_with_defaults(self):
        """Test CI mode with default values."""
        from praisonai.mcp_server.elicitation import (
            ElicitationHandler, ElicitationRequest, ElicitationMode,
            ElicitationSchema, ElicitationAction
        )
        import asyncio
        
        handler = ElicitationHandler(ci_mode=True, ci_defaults={"name": "CI User"})
        
        schema = ElicitationSchema(
            properties={"name": {"type": "string"}},
            required=["name"],
        )
        request = ElicitationRequest(
            elicitation_id="test",
            mode=ElicitationMode.FORM,
            message="Enter name",
            requested_schema=schema,
        )
        
        result = asyncio.run(handler.elicit(request))
        
        assert result.action == ElicitationAction.ACCEPT
        assert result.content["name"] == "CI User"
    
    def test_handler_ci_mode_url_fails(self):
        """Test CI mode fails for URL elicitation."""
        from praisonai.mcp_server.elicitation import (
            ElicitationHandler, ElicitationRequest, ElicitationMode,
            ElicitationAction
        )
        import asyncio
        
        handler = ElicitationHandler(ci_mode=True)
        
        request = ElicitationRequest(
            elicitation_id="test",
            mode=ElicitationMode.URL,
            message="Auth required",
            url="https://example.com",
        )
        
        result = asyncio.run(handler.elicit(request))
        
        assert result.action == ElicitationAction.DECLINE
    
    def test_handler_cancel(self):
        """Test cancelling pending request."""
        from praisonai.mcp_server.elicitation import ElicitationHandler
        
        handler = ElicitationHandler()
        
        # Add a fake pending request
        handler._pending_requests["test-id"] = None
        
        result = handler.cancel("test-id")
        
        assert result is True
        assert "test-id" not in handler._pending_requests
    
    def test_custom_handler(self):
        """Test custom elicitation handler."""
        from praisonai.mcp_server.elicitation import (
            ElicitationHandler, ElicitationRequest, ElicitationMode,
            ElicitationResult
        )
        import asyncio
        
        async def custom_handler(request):
            return ElicitationResult.accept({"custom": True})
        
        handler = ElicitationHandler()
        handler.set_custom_handler(custom_handler)
        
        request = ElicitationRequest(
            elicitation_id="test",
            mode=ElicitationMode.FORM,
            message="Test",
        )
        
        result = asyncio.run(handler.elicit(request))
        
        assert result.content["custom"] is True


class TestElicitationHelpers:
    """Tests for elicitation helper functions."""
    
    def test_create_form_request(self):
        """Test create_form_request helper."""
        from praisonai.mcp_server.elicitation import create_form_request, ElicitationMode
        
        request = create_form_request(
            message="Enter details",
            properties={"name": {"type": "string"}},
            required=["name"],
            title="User Form",
        )
        
        assert request.mode == ElicitationMode.FORM
        assert request.message == "Enter details"
        assert request.schema is not None
    
    def test_create_url_request(self):
        """Test create_url_request helper."""
        from praisonai.mcp_server.elicitation import create_url_request, ElicitationMode
        
        request = create_url_request(
            message="Please authenticate",
            url="https://auth.example.com",
            timeout=120,
        )
        
        assert request.mode == ElicitationMode.URL
        assert request.url == "https://auth.example.com"
        assert request.timeout == 120


class TestGlobalElicitationHandler:
    """Tests for global elicitation handler functions."""
    
    def test_get_elicitation_handler(self):
        """Test getting global handler."""
        from praisonai.mcp_server.elicitation import get_elicitation_handler, ElicitationHandler
        
        handler = get_elicitation_handler()
        
        assert isinstance(handler, ElicitationHandler)
    
    def test_set_elicitation_handler(self):
        """Test setting global handler."""
        from praisonai.mcp_server.elicitation import (
            get_elicitation_handler, set_elicitation_handler, ElicitationHandler
        )
        
        custom_handler = ElicitationHandler(ci_mode=True)
        set_elicitation_handler(custom_handler)
        
        retrieved = get_elicitation_handler()
        
        assert retrieved is custom_handler
        assert retrieved.ci_mode is True
