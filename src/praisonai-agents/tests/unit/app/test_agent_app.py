"""
Tests for AgentApp protocol and configuration.

TDD: These tests define the expected behavior for the AgentApp feature.
"""
import warnings


class TestAgentAppProtocol:
    """Test that AgentAppProtocol is importable from core SDK."""
    
    def test_agent_app_protocol_importable(self):
        """AgentAppProtocol should be importable from praisonaiagents."""
        from praisonaiagents import AgentAppProtocol
        assert AgentAppProtocol is not None
    
    def test_agent_app_config_importable(self):
        """AgentAppConfig should be importable from praisonaiagents."""
        from praisonaiagents import AgentAppConfig
        assert AgentAppConfig is not None


class TestAgentAppProtocolInterface:
    """Test the AgentAppProtocol interface definition."""
    
    def test_protocol_has_serve_method(self):
        """AgentAppProtocol should define a serve method."""
        from praisonaiagents import AgentAppProtocol
        import inspect
        
        # Check that serve is defined in the protocol
        assert hasattr(AgentAppProtocol, 'serve')
    
    def test_protocol_has_get_app_method(self):
        """AgentAppProtocol should define a get_app method."""
        from praisonaiagents import AgentAppProtocol
        
        assert hasattr(AgentAppProtocol, 'get_app')


class TestAgentAppConfig:
    """Test AgentAppConfig dataclass."""
    
    def test_config_default_values(self):
        """AgentAppConfig should have sensible defaults."""
        from praisonaiagents import AgentAppConfig
        
        config = AgentAppConfig()
        assert config.host == "0.0.0.0"
        assert config.port == 8000
        assert config.reload is False
    
    def test_config_custom_values(self):
        """AgentAppConfig should accept custom values."""
        from praisonaiagents import AgentAppConfig
        
        config = AgentAppConfig(
            name="My App",
            host="127.0.0.1",
            port=9000,
            reload=True
        )
        assert config.name == "My App"
        assert config.host == "127.0.0.1"
        assert config.port == 9000
        assert config.reload is True
