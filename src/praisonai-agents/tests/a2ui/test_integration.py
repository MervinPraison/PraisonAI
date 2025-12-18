"""
End-to-End Integration Tests for A2UI

Tests the complete A2UI workflow from agent to JSON output.
"""

import json
import os
import pytest


class TestA2UIEndToEnd:
    """End-to-end integration tests."""

    def test_complete_surface_workflow(self):
        """Test complete workflow: create surface, add components, generate JSON."""
        from praisonaiagents.ui.a2ui import (
            Surface,
            PathBinding,
        )
        
        # Create surface
        surface = Surface(surface_id="test-surface")
        
        # Add components using fluent API
        surface.text(id="title", text="Welcome", usage_hint="h1")
        surface.text(id="subtitle", text=PathBinding(path="/subtitle"), usage_hint="h2")
        surface.button(
            id="action-btn",
            child="btn-text",
            action_name="do_action",
            action_context=[{"key": "id", "value": "123"}],
            primary=True
        )
        surface.text(id="btn-text", text="Click Me")
        surface.column(id="root", children=["title", "subtitle", "action-btn"])
        
        # Set data
        surface.set_data("subtitle", "Hello World")
        
        # Generate messages
        messages = surface.to_messages()
        
        # Verify structure
        assert len(messages) == 3  # createSurface, updateComponents, updateDataModel
        
        # Verify createSurface
        assert "createSurface" in messages[0]
        assert messages[0]["createSurface"]["surfaceId"] == "test-surface"
        
        # Verify updateComponents
        assert "updateComponents" in messages[1]
        components = messages[1]["updateComponents"]["components"]
        assert len(components) == 5  # title, subtitle, btn, btn-text, root
        
        # Verify updateDataModel
        assert "updateDataModel" in messages[2]
        assert messages[2]["updateDataModel"]["value"]["subtitle"] == "Hello World"
        
        # Verify JSON output
        json_str = surface.to_json()
        parsed = json.loads(json_str)
        assert len(parsed) == 3

    def test_a2ui_agent_render_workflow(self):
        """Test A2UIAgent rendering workflow."""
        from praisonaiagents import Agent
        from praisonaiagents.ui.a2ui import A2UIAgent
        
        agent = Agent(
            name="TestAgent",
            role="Test assistant",
            goal="Help with testing"
        )
        
        a2ui_agent = A2UIAgent(agent=agent, surface_id="agent-surface")
        
        # Render text
        messages = a2ui_agent.render_text(
            text="This is a test response",
            title="Test Title"
        )
        
        # Verify structure
        assert len(messages) >= 2
        assert "createSurface" in messages[0]
        
        # Verify JSON export
        json_str = a2ui_agent.to_json()
        parsed = json.loads(json_str)
        assert isinstance(parsed, list)

    def test_template_workflow(self):
        """Test template-based workflow."""
        from praisonaiagents.ui.a2ui import (
            ChatTemplate,
            ListTemplate,
            FormTemplate,
            DashboardTemplate,
        )
        
        # Chat template
        chat = ChatTemplate(surface_id="chat")
        chat.add_user_message("Hello!")
        chat.add_agent_message("Hi there!")
        chat_messages = chat.to_messages()
        assert len(chat_messages) >= 2
        
        # List template
        list_template = ListTemplate(surface_id="list", title="Items")
        list_template.add_item(title="Item 1", description="First")
        list_template.add_item(title="Item 2", description="Second")
        list_messages = list_template.to_messages()
        assert len(list_messages) >= 2
        
        # Form template
        form = FormTemplate(surface_id="form", title="Contact")
        form.add_text_field(id="name", label="Name")
        form.add_email_field(id="email", label="Email")
        form.set_submit_action("submit", "Send")
        form_messages = form.to_messages()
        assert len(form_messages) >= 2
        
        # Dashboard template
        dashboard = DashboardTemplate(surface_id="dashboard", title="Dashboard")
        dashboard.add_panel(id="stats", title="Stats", content="100 items")
        dashboard.add_panel(id="chart", title="Chart", content="[Chart]")
        dashboard_messages = dashboard.to_messages()
        assert len(dashboard_messages) >= 2

    def test_a2a_integration(self):
        """Test A2A protocol integration."""
        from praisonaiagents.ui.a2ui import (
            Surface,
            create_a2ui_part,
            is_a2ui_part,
            A2UI_MIME_TYPE,
        )
        
        # Create surface
        surface = Surface(surface_id="a2a-test")
        surface.text(id="msg", text="Hello from A2A")
        surface.column(id="root", children=["msg"])
        
        # Get messages
        messages = surface.to_messages()
        
        # Wrap in A2A DataPart
        part = create_a2ui_part({"messages": messages})
        
        # Verify A2UI part
        assert is_a2ui_part(part)
        assert part.metadata["mimeType"] == A2UI_MIME_TYPE
        assert "messages" in part.data
        assert len(part.data["messages"]) >= 2

    def test_data_binding_workflow(self):
        """Test data binding with path references."""
        from praisonaiagents.ui.a2ui import (
            Surface,
            PathBinding,
            ChildrenTemplate,
        )
        
        surface = Surface(surface_id="data-binding-test")
        
        # Add components with data binding
        surface.text(id="title", text=PathBinding(path="/title"), usage_hint="h1")
        surface.text(id="item-template", text=PathBinding(path="/name"))
        
        # Add list with template
        surface.list(
            id="items",
            children=ChildrenTemplate(component_id="item-template", path="/items"),
            direction="vertical"
        )
        
        surface.column(id="root", children=["title", "items"])
        
        # Set data
        surface.set_data("title", "My List")
        surface.set_data("items", [
            {"name": "Item 1"},
            {"name": "Item 2"},
            {"name": "Item 3"},
        ])
        
        messages = surface.to_messages()
        
        # Verify data model
        data_msg = next((m for m in messages if "updateDataModel" in m), None)
        assert data_msg is not None
        assert data_msg["updateDataModel"]["value"]["title"] == "My List"
        assert len(data_msg["updateDataModel"]["value"]["items"]) == 3


@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set"
)
class TestA2UIWithLLM:
    """Tests that require LLM API calls."""

    def test_agent_chat_and_render(self):
        """Test agent chat followed by UI rendering."""
        from praisonaiagents import Agent
        from praisonaiagents.ui.a2ui import A2UIAgent
        
        agent = Agent(
            name="UIAgent",
            role="UI Generator",
            goal="Generate helpful responses",
            llm="gpt-4o-mini"
        )
        
        a2ui_agent = A2UIAgent(agent=agent)
        
        # Chat with agent
        response = a2ui_agent.chat("What is 2+2?")
        
        # Render response as UI
        messages = a2ui_agent.render_text(response, title="Answer")
        
        assert len(messages) >= 2
        assert "createSurface" in messages[0]
