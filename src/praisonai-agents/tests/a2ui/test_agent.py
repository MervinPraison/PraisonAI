"""
Tests for A2UI Agent Integration

TDD: Write tests first, then implement the A2UIAgent class.
"""

import os
import pytest


# Skip tests if no API key
pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set"
)


class TestA2UIAgent:
    """Test A2UIAgent wrapper class."""

    def test_a2ui_agent_creation(self):
        """Test A2UIAgent creation with an agent."""
        from praisonaiagents import Agent
        from praisonaiagents.ui.a2ui.agent import A2UIAgent
        
        agent = Agent(
            name="TestAgent",
            role="Test assistant",
            goal="Help with testing"
        )
        
        a2ui_agent = A2UIAgent(agent=agent)
        
        assert a2ui_agent.agent is agent
        assert a2ui_agent.surface_id is not None

    def test_a2ui_agent_with_custom_surface_id(self):
        """Test A2UIAgent with custom surface ID."""
        from praisonaiagents import Agent
        from praisonaiagents.ui.a2ui.agent import A2UIAgent
        
        agent = Agent(name="TestAgent", role="Test", goal="Test")
        a2ui_agent = A2UIAgent(agent=agent, surface_id="custom-surface")
        
        assert a2ui_agent.surface_id == "custom-surface"

    def test_render_text_response(self):
        """Test rendering a simple text response as A2UI."""
        from praisonaiagents import Agent
        from praisonaiagents.ui.a2ui.agent import A2UIAgent
        
        agent = Agent(name="TestAgent", role="Test", goal="Test")
        a2ui_agent = A2UIAgent(agent=agent)
        
        # Render a simple text response
        messages = a2ui_agent.render_text("Hello, World!")
        
        assert isinstance(messages, list)
        assert len(messages) >= 2  # createSurface + updateComponents
        
        # Check createSurface
        assert "createSurface" in messages[0]
        
        # Check updateComponents has a text component
        update_msg = next((m for m in messages if "updateComponents" in m), None)
        assert update_msg is not None
        components = update_msg["updateComponents"]["components"]
        assert any(c.get("component") == "Text" for c in components)

    def test_render_list_response(self):
        """Test rendering a list of items as A2UI cards."""
        from praisonaiagents import Agent
        from praisonaiagents.ui.a2ui.agent import A2UIAgent
        
        agent = Agent(name="TestAgent", role="Test", goal="Test")
        a2ui_agent = A2UIAgent(agent=agent)
        
        items = [
            {"title": "Item 1", "description": "First item"},
            {"title": "Item 2", "description": "Second item"},
        ]
        
        messages = a2ui_agent.render_list(
            title="My Items",
            items=items,
            item_title_key="title",
            item_description_key="description"
        )
        
        assert isinstance(messages, list)
        assert len(messages) >= 2

    def test_render_form(self):
        """Test rendering a form as A2UI."""
        from praisonaiagents import Agent
        from praisonaiagents.ui.a2ui.agent import A2UIAgent
        
        agent = Agent(name="TestAgent", role="Test", goal="Test")
        a2ui_agent = A2UIAgent(agent=agent)
        
        fields = [
            {"id": "name", "label": "Name", "type": "text"},
            {"id": "email", "label": "Email", "type": "text"},
        ]
        
        messages = a2ui_agent.render_form(
            title="Contact Form",
            fields=fields,
            submit_action="submit_form"
        )
        
        assert isinstance(messages, list)
        assert len(messages) >= 2
        
        # Check for TextField components
        update_msg = next((m for m in messages if "updateComponents" in m), None)
        assert update_msg is not None
        components = update_msg["updateComponents"]["components"]
        text_fields = [c for c in components if c.get("component") == "TextField"]
        assert len(text_fields) >= 2

    def test_get_surface(self):
        """Test getting the underlying Surface object."""
        from praisonaiagents import Agent
        from praisonaiagents.ui.a2ui.agent import A2UIAgent
        from praisonaiagents.ui.a2ui.surface import Surface
        
        agent = Agent(name="TestAgent", role="Test", goal="Test")
        a2ui_agent = A2UIAgent(agent=agent)
        
        surface = a2ui_agent.get_surface()
        
        assert isinstance(surface, Surface)
        assert surface.surface_id == a2ui_agent.surface_id


class TestA2UIAgentWithLLM:
    """Test A2UIAgent with actual LLM calls."""

    @pytest.mark.asyncio
    async def test_chat_with_ui(self):
        """Test chat that returns A2UI response."""
        from praisonaiagents import Agent
        from praisonaiagents.ui.a2ui.agent import A2UIAgent
        
        agent = Agent(
            name="UIAgent",
            role="UI Generator",
            goal="Generate helpful UI responses",
            llm="gpt-4o-mini"
        )
        
        a2ui_agent = A2UIAgent(agent=agent)
        
        # This should work with the agent's chat
        response = await a2ui_agent.chat_async("Say hello")
        
        assert response is not None
        # Response should contain text
        assert isinstance(response, str) or isinstance(response, dict)


class TestA2UIAgentIntegration:
    """Integration tests for A2UIAgent with A2A."""

    def test_get_a2a_data_part(self):
        """Test getting A2UI as A2A DataPart."""
        from praisonaiagents import Agent
        from praisonaiagents.ui.a2ui.agent import A2UIAgent
        from praisonaiagents.ui.a2ui.extension import is_a2ui_part
        
        agent = Agent(name="TestAgent", role="Test", goal="Test")
        a2ui_agent = A2UIAgent(agent=agent)
        
        # Render something
        a2ui_agent.render_text("Hello")
        
        # Get as A2A DataPart
        part = a2ui_agent.to_a2a_part()
        
        assert part is not None
        assert is_a2ui_part(part)

    def test_to_json(self):
        """Test getting A2UI as JSON string."""
        from praisonaiagents import Agent
        from praisonaiagents.ui.a2ui.agent import A2UIAgent
        import json
        
        agent = Agent(name="TestAgent", role="Test", goal="Test")
        a2ui_agent = A2UIAgent(agent=agent)
        
        # Render something
        a2ui_agent.render_text("Hello")
        
        # Get as JSON
        json_str = a2ui_agent.to_json()
        
        # Should be valid JSON
        parsed = json.loads(json_str)
        assert isinstance(parsed, list)
