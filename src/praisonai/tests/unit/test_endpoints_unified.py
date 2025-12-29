"""
Unit tests for unified endpoints module.

Tests discovery schema, provider adapters, registry, and CLI.
"""

import pytest
from unittest.mock import patch, MagicMock


class TestDiscoverySchema:
    """Tests for discovery schema."""
    
    def test_discovery_document_creation(self):
        """Test creating a discovery document."""
        from praisonai.endpoints.discovery import (
            DiscoveryDocument,
            create_discovery_document,
            SCHEMA_VERSION,
        )
        
        doc = create_discovery_document(server_name="test-server")
        
        assert doc.server_name == "test-server"
        assert doc.schema_version == SCHEMA_VERSION
        assert isinstance(doc.providers, list)
        assert isinstance(doc.endpoints, list)
    
    def test_endpoint_info_creation(self):
        """Test creating endpoint info."""
        from praisonai.endpoints.discovery import EndpointInfo
        
        endpoint = EndpointInfo(
            name="test-endpoint",
            description="Test endpoint",
            provider_type="recipe",
            tags=["test", "demo"],
        )
        
        assert endpoint.name == "test-endpoint"
        assert endpoint.provider_type == "recipe"
        assert "test" in endpoint.tags
    
    def test_provider_info_creation(self):
        """Test creating provider info."""
        from praisonai.endpoints.discovery import ProviderInfo
        
        provider = ProviderInfo(
            type="agents-api",
            name="Agents API",
            capabilities=["invoke", "health"],
        )
        
        assert provider.type == "agents-api"
        assert "invoke" in provider.capabilities
    
    def test_discovery_document_to_dict(self):
        """Test converting discovery document to dict."""
        from praisonai.endpoints.discovery import (
            DiscoveryDocument,
            EndpointInfo,
            ProviderInfo,
        )
        
        doc = DiscoveryDocument(server_name="test")
        doc.add_provider(ProviderInfo(type="recipe", name="Recipe"))
        doc.add_endpoint(EndpointInfo(name="test-ep", provider_type="recipe"))
        
        data = doc.to_dict()
        
        assert data["server_name"] == "test"
        assert len(data["providers"]) == 1
        assert len(data["endpoints"]) == 1
        assert data["providers"][0]["type"] == "recipe"
    
    def test_get_endpoints_by_type(self):
        """Test filtering endpoints by type."""
        from praisonai.endpoints.discovery import DiscoveryDocument, EndpointInfo
        
        doc = DiscoveryDocument()
        doc.add_endpoint(EndpointInfo(name="ep1", provider_type="recipe"))
        doc.add_endpoint(EndpointInfo(name="ep2", provider_type="agents-api"))
        doc.add_endpoint(EndpointInfo(name="ep3", provider_type="recipe"))
        
        recipe_eps = doc.get_endpoints_by_type("recipe")
        
        assert len(recipe_eps) == 2
        assert all(ep.provider_type == "recipe" for ep in recipe_eps)
    
    def test_get_endpoint_by_name(self):
        """Test getting endpoint by name."""
        from praisonai.endpoints.discovery import DiscoveryDocument, EndpointInfo
        
        doc = DiscoveryDocument()
        doc.add_endpoint(EndpointInfo(name="my-endpoint", description="Test"))
        
        ep = doc.get_endpoint_by_name("my-endpoint")
        
        assert ep is not None
        assert ep.name == "my-endpoint"
        
        missing = doc.get_endpoint_by_name("nonexistent")
        assert missing is None


class TestProviderRegistry:
    """Tests for provider registry."""
    
    def test_list_provider_types(self):
        """Test listing provider types."""
        from praisonai.endpoints.registry import list_provider_types
        
        types = list_provider_types()
        
        assert "recipe" in types
        assert "agents-api" in types
        assert "mcp" in types
        assert "a2a" in types
        assert "a2u" in types
    
    def test_get_provider(self):
        """Test getting a provider instance."""
        from praisonai.endpoints.registry import get_provider
        
        provider = get_provider("recipe", base_url="http://localhost:8000")
        
        assert provider is not None
        assert provider.provider_type == "recipe"
        assert provider.base_url == "http://localhost:8000"
    
    def test_get_unknown_provider(self):
        """Test getting unknown provider returns None."""
        from praisonai.endpoints.registry import get_provider
        
        provider = get_provider("unknown-type")
        
        assert provider is None
    
    def test_provider_registry_class(self):
        """Test ProviderRegistry class."""
        from praisonai.endpoints.registry import ProviderRegistry
        
        registry = ProviderRegistry()
        
        assert "recipe" in registry.list_types()
        
        provider = registry.get("agents-api")
        assert provider is not None


class TestRecipeProvider:
    """Tests for recipe provider."""
    
    def test_provider_info(self):
        """Test recipe provider info."""
        from praisonai.endpoints.providers.recipe import RecipeProvider
        
        provider = RecipeProvider()
        info = provider.get_provider_info()
        
        assert info.type == "recipe"
        assert "invoke" in info.capabilities
    
    @patch('praisonai.endpoints.providers.base.BaseProvider._make_request')
    def test_list_endpoints(self, mock_request):
        """Test listing recipe endpoints."""
        from praisonai.endpoints.providers.recipe import RecipeProvider
        
        mock_request.return_value = {
            "data": {
                "recipes": [
                    {"name": "recipe1", "description": "Test 1"},
                    {"name": "recipe2", "description": "Test 2"},
                ]
            }
        }
        
        provider = RecipeProvider()
        endpoints = provider.list_endpoints()
        
        assert len(endpoints) == 2
        assert endpoints[0].name == "recipe1"
    
    @patch('praisonai.endpoints.providers.base.BaseProvider._make_request')
    def test_health_check(self, mock_request):
        """Test recipe health check."""
        from praisonai.endpoints.providers.recipe import RecipeProvider
        
        mock_request.return_value = {
            "data": {"status": "healthy", "service": "recipe-runner"}
        }
        
        provider = RecipeProvider()
        health = provider.health()
        
        assert health.healthy is True
        assert health.status == "healthy"


class TestAgentsAPIProvider:
    """Tests for agents-api provider."""
    
    def test_provider_info(self):
        """Test agents-api provider info."""
        from praisonai.endpoints.providers.agents_api import AgentsAPIProvider
        
        provider = AgentsAPIProvider()
        info = provider.get_provider_info()
        
        assert info.type == "agents-api"
    
    @patch('praisonai.endpoints.providers.base.BaseProvider._make_request')
    def test_invoke(self, mock_request):
        """Test invoking agents-api endpoint."""
        from praisonai.endpoints.providers.agents_api import AgentsAPIProvider
        
        mock_request.return_value = {
            "status": 200,
            "data": {"response": "Hello!"}
        }
        
        provider = AgentsAPIProvider()
        result = provider.invoke("test-agent", {"query": "Hi"})
        
        assert result.ok is True
        assert result.data == "Hello!"


class TestA2AProvider:
    """Tests for A2A provider."""
    
    def test_provider_info(self):
        """Test A2A provider info."""
        from praisonai.endpoints.providers.a2a import A2AProvider
        
        provider = A2AProvider()
        info = provider.get_provider_info()
        
        assert info.type == "a2a"
        assert "agent-card" in info.capabilities


class TestA2UProvider:
    """Tests for A2U provider."""
    
    def test_provider_info(self):
        """Test A2U provider info."""
        from praisonai.endpoints.providers.a2u import A2UProvider
        
        provider = A2UProvider()
        info = provider.get_provider_info()
        
        assert info.type == "a2u"
        assert "subscribe" in info.capabilities


class TestEndpointsCLI:
    """Tests for endpoints CLI."""
    
    def test_handler_initialization(self):
        """Test CLI handler initialization."""
        from praisonai.cli.features.endpoints import EndpointsHandler
        
        handler = EndpointsHandler()
        
        assert handler.base_url == "http://localhost:8765"
    
    def test_help_command(self):
        """Test help command."""
        from praisonai.cli.features.endpoints import EndpointsHandler
        
        handler = EndpointsHandler()
        result = handler.handle(["help"])
        
        assert result == 0
    
    def test_types_command(self):
        """Test types command."""
        from praisonai.cli.features.endpoints import EndpointsHandler
        
        handler = EndpointsHandler()
        result = handler.cmd_types(["--format", "json"])
        
        assert result == 0
    
    def test_parse_args(self):
        """Test argument parsing."""
        from praisonai.cli.features.endpoints import EndpointsHandler
        
        handler = EndpointsHandler()
        spec = {
            "name": {"positional": True, "default": ""},
            "url": {"default": None},
            "json": {"flag": True, "default": False},
        }
        
        parsed = handler._parse_args(["my-endpoint", "--url", "http://test", "--json"], spec)
        
        assert parsed["name"] == "my-endpoint"
        assert parsed["url"] == "http://test"
        assert parsed["json"] is True


class TestServeCLI:
    """Tests for serve CLI."""
    
    def test_handler_initialization(self):
        """Test serve handler initialization."""
        from praisonai.cli.features.serve import ServeHandler
        
        handler = ServeHandler()
        
        assert handler.DEFAULT_PORT == 8765
    
    def test_help_command(self):
        """Test help command."""
        from praisonai.cli.features.serve import ServeHandler
        
        handler = ServeHandler()
        result = handler.handle(["help"])
        
        assert result == 0
    
    def test_parse_args(self):
        """Test argument parsing."""
        from praisonai.cli.features.serve import ServeHandler
        
        handler = ServeHandler()
        spec = {
            "host": {"default": "127.0.0.1"},
            "port": {"default": 8765, "type": "int"},
            "reload": {"flag": True, "default": False},
        }
        
        parsed = handler._parse_args(["--host", "0.0.0.0", "--port", "9000", "--reload"], spec)
        
        assert parsed["host"] == "0.0.0.0"
        assert parsed["port"] == 9000
        assert parsed["reload"] is True


class TestA2UServer:
    """Tests for A2U server components."""
    
    def test_event_creation(self):
        """Test A2U event creation."""
        from praisonai.endpoints.a2u_server import A2UEvent
        
        event = A2UEvent(event_type="test", data={"key": "value"})
        
        assert event.event_type == "test"
        assert event.data["key"] == "value"
        assert event.event_id is not None
    
    def test_event_to_sse(self):
        """Test converting event to SSE format."""
        from praisonai.endpoints.a2u_server import A2UEvent
        
        event = A2UEvent(event_type="message", data={"text": "hello"})
        sse = event.to_sse()
        
        assert "event: message" in sse
        assert "data:" in sse
        assert "hello" in sse
    
    def test_subscription_creation(self):
        """Test A2U subscription creation."""
        from praisonai.endpoints.a2u_server import A2USubscription
        
        sub = A2USubscription(
            subscription_id="sub-123",
            stream_name="events",
            filters=["agent.started", "agent.completed"],
        )
        
        assert sub.subscription_id == "sub-123"
        assert sub.stream_name == "events"
        assert len(sub.filters) == 2
    
    def test_subscription_matches_event(self):
        """Test subscription event matching."""
        from praisonai.endpoints.a2u_server import A2USubscription, A2UEvent
        
        sub = A2USubscription(
            subscription_id="sub-123",
            stream_name="events",
            filters=["agent.started"],
        )
        
        event1 = A2UEvent(event_type="agent.started", data={})
        event2 = A2UEvent(event_type="agent.completed", data={})
        
        assert sub.matches_event(event1) is True
        assert sub.matches_event(event2) is False
    
    def test_subscription_matches_all_without_filters(self):
        """Test subscription matches all events without filters."""
        from praisonai.endpoints.a2u_server import A2USubscription, A2UEvent
        
        sub = A2USubscription(
            subscription_id="sub-123",
            stream_name="events",
        )
        
        event = A2UEvent(event_type="any.event", data={})
        
        assert sub.matches_event(event) is True
    
    def test_event_bus_subscribe(self):
        """Test event bus subscription."""
        from praisonai.endpoints.a2u_server import A2UEventBus
        
        bus = A2UEventBus()
        sub = bus.subscribe("events", ["agent.started"])
        
        assert sub.subscription_id.startswith("sub-")
        assert sub.stream_name == "events"
    
    def test_event_bus_unsubscribe(self):
        """Test event bus unsubscription."""
        from praisonai.endpoints.a2u_server import A2UEventBus
        
        bus = A2UEventBus()
        sub = bus.subscribe("events")
        
        result = bus.unsubscribe(sub.subscription_id)
        assert result is True
        
        result = bus.unsubscribe("nonexistent")
        assert result is False
    
    def test_emit_helpers(self):
        """Test emit helper functions."""
        from praisonai.endpoints.a2u_server import (
            emit_agent_started,
            emit_agent_thinking,
            emit_agent_response,
            emit_agent_completed,
            emit_agent_error,
        )
        
        # These should not raise
        emit_agent_started("agent-1", "TestAgent")
        emit_agent_thinking("agent-1", "Processing...")
        emit_agent_response("agent-1", "Hello!")
        emit_agent_completed("agent-1", {"result": "done"})
        emit_agent_error("agent-1", "Something went wrong")


class TestServerUtilities:
    """Tests for server utilities."""
    
    def test_add_discovery_routes(self):
        """Test adding discovery routes to app."""
        from praisonai.endpoints.server import add_discovery_routes
        from praisonai.endpoints.discovery import create_discovery_document
        
        # Mock FastAPI app
        mock_app = MagicMock()
        mock_app.add_api_route = MagicMock()
        
        discovery = create_discovery_document()
        add_discovery_routes(mock_app, discovery)
        
        # Should have added routes
        assert mock_app.add_api_route.called


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
