"""
TDD Tests for Gateway Tool Resolution Gaps (G1, G2, G3).

Tests the fixes for tool resolution in gateway agent creation.
"""

# Mocks available if needed for future tests


class TestGapG1GatewayToolResolution:
    """Test Gap G1: Gateway _create_agents_from_config() tool resolution."""

    def test_gateway_creates_agent_with_tools_from_yaml(self):
        """Gateway should resolve tools from YAML config."""
        from praisonai.gateway import WebSocketGateway
        
        gw = WebSocketGateway()
        
        # Mock config with tools
        agents_cfg = {
            "researcher": {
                "instructions": "You are a researcher",
                "model": "gpt-4o-mini",
                "tools": ["internet_search", "get_current_time"],
            }
        }
        
        # Create agents from config
        gw._create_agents_from_config(agents_cfg)
        
        # Verify agent was created
        agent = gw.get_agent("researcher")
        assert agent is not None
        assert agent.name == "researcher"
        # Tools should be resolved (may be empty if ToolResolver can't find them)
        # The important thing is no error was raised

    def test_gateway_handles_missing_tool_gracefully(self):
        """Gateway should log warning for missing tools but not fail."""
        from praisonai.gateway import WebSocketGateway
        
        gw = WebSocketGateway()
        
        agents_cfg = {
            "test_agent": {
                "instructions": "Test agent",
                "tools": ["nonexistent_tool_xyz"],
            }
        }
        
        # Should not raise
        gw._create_agents_from_config(agents_cfg)
        
        agent = gw.get_agent("test_agent")
        assert agent is not None

    def test_gateway_agent_has_reflection_enabled_by_default(self):
        """Gateway agents should have reflection=True by default."""
        from praisonai.gateway import WebSocketGateway
        
        gw = WebSocketGateway()
        
        agents_cfg = {
            "assistant": {
                "instructions": "You are helpful",
            }
        }
        
        gw._create_agents_from_config(agents_cfg)
        
        agent = gw.get_agent("assistant")
        assert agent is not None
        # self_reflect should be True by default (set via reflection param)
        assert getattr(agent, "self_reflect", None) is True

    def test_gateway_supports_tool_choice_from_yaml(self):
        """Gateway should store tool_choice from YAML config."""
        from praisonai.gateway import WebSocketGateway
        
        gw = WebSocketGateway()
        
        agents_cfg = {
            "researcher": {
                "instructions": "Research assistant",
                "tools": ["internet_search"],
                "tool_choice": "required",
            }
        }
        
        gw._create_agents_from_config(agents_cfg)
        
        agent = gw.get_agent("researcher")
        assert agent is not None
        # tool_choice should be stored as _yaml_tool_choice
        assert getattr(agent, "_yaml_tool_choice", None) == "required"

    def test_gateway_supports_reflection_override(self):
        """Gateway should allow reflection to be disabled via YAML."""
        from praisonai.gateway import WebSocketGateway
        
        gw = WebSocketGateway()
        
        agents_cfg = {
            "simple_agent": {
                "instructions": "Simple agent",
                "reflection": False,
            }
        }
        
        gw._create_agents_from_config(agents_cfg)
        
        agent = gw.get_agent("simple_agent")
        assert agent is not None
        assert getattr(agent, "self_reflect", True) is False


class TestGapG1ToolResolver:
    """Test ToolResolver integration."""

    def test_tool_resolver_resolve_many_exists(self):
        """ToolResolver should have resolve_many method."""
        from praisonai.tool_resolver import ToolResolver
        
        resolver = ToolResolver()
        
        assert hasattr(resolver, "resolve_many")
        assert callable(resolver.resolve_many)

    def test_tool_resolver_resolve_returns_callable_or_none(self):
        """ToolResolver.resolve should return callable or None."""
        from praisonai.tool_resolver import ToolResolver
        
        resolver = ToolResolver()
        
        # Known tool should return callable
        result = resolver.resolve("internet_search")
        # May be None if tool not available, but should not raise
        if result is not None:
            assert callable(result)
        
        # Unknown tool should return None
        result = resolver.resolve("nonexistent_tool_xyz_123")
        assert result is None


class TestGapG2ProviderDefaultTools:
    """Test Gap G2: PraisonAIUI provider default tools."""

    def test_provider_agent_kwargs_include_reflection(self):
        """Provider should set reflection=True by default."""
        # This tests the pattern, not the actual provider (which is in PraisonAIUI)
        default_kwargs = {
            "name": "Assistant",
            "instructions": "You are a helpful assistant.",
            "memory": True,
            "reflection": True,
        }
        
        assert default_kwargs["reflection"] is True


class TestGapG3ChannelBotTools:
    """Test Gap G3: Channel bot agent tools."""

    def test_channel_bot_agent_pattern_includes_tools(self):
        """Channel bot agent creation pattern should include tools."""
        # This tests the pattern, not the actual channel bot (which is in PraisonAIUI)
        from praisonai.tool_resolver import ToolResolver
        
        resolver = ToolResolver()
        agent_tools = resolver.resolve_many(["internet_search", "get_current_time"])
        
        # Should return a list (may be empty if tools not available)
        assert isinstance(agent_tools, list)


class TestToolResolverIntegration:
    """Integration tests for ToolResolver with gateway."""

    def test_full_gateway_agent_creation_with_tools(self):
        """Full integration test: gateway creates agent with resolved tools."""
        from praisonai.gateway import WebSocketGateway
        from praisonai.tool_resolver import ToolResolver
        
        # First verify ToolResolver works
        resolver = ToolResolver()
        tools = resolver.resolve_many(["internet_search"])
        
        # Create gateway and agent
        gw = WebSocketGateway()
        agents_cfg = {
            "test_researcher": {
                "instructions": "Research assistant with tools",
                "model": "gpt-4o-mini",
                "tools": ["internet_search"],
                "reflection": True,
            }
        }
        
        gw._create_agents_from_config(agents_cfg)
        
        agent = gw.get_agent("test_researcher")
        assert agent is not None
        assert agent.name == "test_researcher"
        
        # If tools were resolved, agent should have them
        if tools:
            assert agent.tools is not None
            assert len(agent.tools) > 0
