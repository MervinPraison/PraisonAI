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
        """Test elicitation status values."""
        from praisonai.mcp_server.elicitation import ElicitationStatus
        
        assert ElicitationStatus.COMPLETED.value == "completed"
        assert ElicitationStatus.CANCELLED.value == "cancelled"
        assert ElicitationStatus.TIMEOUT.value == "timeout"
        assert ElicitationStatus.ERROR.value == "error"


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
    """Tests for ElicitationRequest dataclass."""
    
    def test_form_request(self):
        """Test form mode request."""
        from praisonai.mcp_server.elicitation import (
            ElicitationRequest, ElicitationMode, ElicitationSchema
        )
        
        schema = ElicitationSchema(properties={"name": {"type": "string"}})
        request = ElicitationRequest(
            id="elicit-123",
            mode=ElicitationMode.FORM,
            message="Please provide your name",
            schema=schema,
        )
        
        assert request.id == "elicit-123"
        assert request.mode == ElicitationMode.FORM
        assert request.schema is not None
    
    def test_url_request(self):
        """Test URL mode request."""
        from praisonai.mcp_server.elicitation import ElicitationRequest, ElicitationMode
        
        request = ElicitationRequest(
            id="elicit-456",
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
            id="elicit-789",
            mode=ElicitationMode.URL,
            message="Test",
            url="https://example.com",
            timeout=60,
        )
        
        result = request.to_dict()
        
        assert result["id"] == "elicit-789"
        assert result["mode"] == "url"
        assert result["url"] == "https://example.com"
        assert result["timeout"] == 60


class TestElicitationResult:
    """Tests for ElicitationResult dataclass."""
    
    def test_completed_result(self):
        """Test completed result."""
        from praisonai.mcp_server.elicitation import ElicitationResult, ElicitationStatus
        
        result = ElicitationResult(
            id="elicit-123",
            status=ElicitationStatus.COMPLETED,
            data={"name": "John"},
        )
        
        assert result.status == ElicitationStatus.COMPLETED
        assert result.data == {"name": "John"}
    
    def test_error_result(self):
        """Test error result."""
        from praisonai.mcp_server.elicitation import ElicitationResult, ElicitationStatus
        
        result = ElicitationResult(
            id="elicit-123",
            status=ElicitationStatus.ERROR,
            error="Validation failed",
        )
        
        assert result.status == ElicitationStatus.ERROR
        assert result.error == "Validation failed"
    
    def test_result_to_dict(self):
        """Test result serialization."""
        from praisonai.mcp_server.elicitation import ElicitationResult, ElicitationStatus
        
        result = ElicitationResult(
            id="elicit-123",
            status=ElicitationStatus.COMPLETED,
            data={"confirmed": True},
        )
        
        output = result.to_dict()
        
        assert output["id"] == "elicit-123"
        assert output["status"] == "completed"
        assert output["data"] == {"confirmed": True}


class TestElicitationHandler:
    """Tests for ElicitationHandler class."""
    
    def test_handler_init(self):
        """Test handler initialization."""
        from praisonai.mcp_server.elicitation import ElicitationHandler
        
        handler = ElicitationHandler(interactive=False, ci_mode=True)
        
        assert handler.interactive is False
        assert handler.ci_mode is True
    
    def test_handler_ci_mode_with_defaults(self):
        """Test CI mode with defaults."""
        from praisonai.mcp_server.elicitation import (
            ElicitationHandler, ElicitationRequest, ElicitationMode,
            ElicitationSchema, ElicitationStatus
        )
        import asyncio
        
        handler = ElicitationHandler(
            ci_mode=True,
            ci_defaults={"name": "CI User"},
        )
        
        schema = ElicitationSchema(
            properties={"name": {"type": "string"}},
            required=["name"],
        )
        request = ElicitationRequest(
            id="test",
            mode=ElicitationMode.FORM,
            message="Enter name",
            schema=schema,
        )
        
        result = asyncio.run(handler.elicit(request))
        
        assert result.status == ElicitationStatus.COMPLETED
        assert result.data["name"] == "CI User"
    
    def test_handler_ci_mode_url_fails(self):
        """Test CI mode fails for URL elicitation."""
        from praisonai.mcp_server.elicitation import (
            ElicitationHandler, ElicitationRequest, ElicitationMode,
            ElicitationStatus
        )
        import asyncio
        
        handler = ElicitationHandler(ci_mode=True)
        
        request = ElicitationRequest(
            id="test",
            mode=ElicitationMode.URL,
            message="Auth required",
            url="https://example.com",
        )
        
        result = asyncio.run(handler.elicit(request))
        
        assert result.status == ElicitationStatus.ERROR
    
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
            ElicitationResult, ElicitationStatus
        )
        import asyncio
        
        async def custom_handler(request):
            return ElicitationResult(
                id=request.id,
                status=ElicitationStatus.COMPLETED,
                data={"custom": True},
            )
        
        handler = ElicitationHandler()
        handler.set_custom_handler(custom_handler)
        
        request = ElicitationRequest(
            id="test",
            mode=ElicitationMode.FORM,
            message="Test",
        )
        
        result = asyncio.run(handler.elicit(request))
        
        assert result.data["custom"] is True


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
        assert request.id.startswith("elicit-")
    
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
