"""
Tests for A2UI Templates

TDD: Write tests first, then implement the templates.
"""


class TestChatTemplate:
    """Test ChatTemplate for conversational UIs."""

    def test_chat_template_creation(self):
        """Test ChatTemplate creation."""
        from praisonaiagents.ui.a2ui.templates import ChatTemplate
        
        template = ChatTemplate(surface_id="chat")
        
        assert template.surface_id == "chat"

    def test_add_user_message(self):
        """Test adding a user message."""
        from praisonaiagents.ui.a2ui.templates import ChatTemplate
        
        template = ChatTemplate(surface_id="chat")
        template.add_user_message("Hello!")
        
        assert len(template.messages) == 1
        assert template.messages[0]["role"] == "user"
        assert template.messages[0]["content"] == "Hello!"

    def test_add_agent_message(self):
        """Test adding an agent message."""
        from praisonaiagents.ui.a2ui.templates import ChatTemplate
        
        template = ChatTemplate(surface_id="chat")
        template.add_agent_message("Hi there!")
        
        assert len(template.messages) == 1
        assert template.messages[0]["role"] == "agent"

    def test_to_messages(self):
        """Test generating A2UI messages."""
        from praisonaiagents.ui.a2ui.templates import ChatTemplate
        
        template = ChatTemplate(surface_id="chat")
        template.add_user_message("Hello!")
        template.add_agent_message("Hi there!")
        
        messages = template.to_messages()
        
        assert isinstance(messages, list)
        assert len(messages) >= 2  # createSurface + updateComponents


class TestListTemplate:
    """Test ListTemplate for displaying lists of items."""

    def test_list_template_creation(self):
        """Test ListTemplate creation."""
        from praisonaiagents.ui.a2ui.templates import ListTemplate
        
        template = ListTemplate(
            surface_id="list",
            title="My Items"
        )
        
        assert template.surface_id == "list"
        assert template.title == "My Items"

    def test_add_item(self):
        """Test adding an item to the list."""
        from praisonaiagents.ui.a2ui.templates import ListTemplate
        
        template = ListTemplate(surface_id="list", title="Items")
        template.add_item(title="Item 1", description="First item")
        
        assert len(template.items) == 1
        assert template.items[0]["title"] == "Item 1"

    def test_add_item_with_image(self):
        """Test adding an item with an image."""
        from praisonaiagents.ui.a2ui.templates import ListTemplate
        
        template = ListTemplate(surface_id="list", title="Items")
        template.add_item(
            title="Item 1",
            description="First item",
            image_url="https://example.com/image.jpg"
        )
        
        assert template.items[0]["image_url"] == "https://example.com/image.jpg"

    def test_to_messages(self):
        """Test generating A2UI messages."""
        from praisonaiagents.ui.a2ui.templates import ListTemplate
        
        template = ListTemplate(surface_id="list", title="Items")
        template.add_item(title="Item 1", description="First")
        template.add_item(title="Item 2", description="Second")
        
        messages = template.to_messages()
        
        assert isinstance(messages, list)
        assert len(messages) >= 2


class TestFormTemplate:
    """Test FormTemplate for data collection forms."""

    def test_form_template_creation(self):
        """Test FormTemplate creation."""
        from praisonaiagents.ui.a2ui.templates import FormTemplate
        
        template = FormTemplate(
            surface_id="form",
            title="Contact Form"
        )
        
        assert template.surface_id == "form"
        assert template.title == "Contact Form"

    def test_add_text_field(self):
        """Test adding a text field."""
        from praisonaiagents.ui.a2ui.templates import FormTemplate
        
        template = FormTemplate(surface_id="form", title="Form")
        template.add_text_field(id="name", label="Name")
        
        assert len(template.fields) == 1
        assert template.fields[0]["id"] == "name"
        assert template.fields[0]["type"] == "text"

    def test_add_number_field(self):
        """Test adding a number field."""
        from praisonaiagents.ui.a2ui.templates import FormTemplate
        
        template = FormTemplate(surface_id="form", title="Form")
        template.add_number_field(id="age", label="Age")
        
        assert template.fields[0]["type"] == "number"

    def test_add_email_field(self):
        """Test adding an email field."""
        from praisonaiagents.ui.a2ui.templates import FormTemplate
        
        template = FormTemplate(surface_id="form", title="Form")
        template.add_email_field(id="email", label="Email")
        
        assert template.fields[0]["type"] == "email"

    def test_set_submit_action(self):
        """Test setting submit action."""
        from praisonaiagents.ui.a2ui.templates import FormTemplate
        
        template = FormTemplate(surface_id="form", title="Form")
        template.set_submit_action("submit_form", "Send")
        
        assert template.submit_action == "submit_form"
        assert template.submit_label == "Send"

    def test_to_messages(self):
        """Test generating A2UI messages."""
        from praisonaiagents.ui.a2ui.templates import FormTemplate
        
        template = FormTemplate(surface_id="form", title="Form")
        template.add_text_field(id="name", label="Name")
        template.add_email_field(id="email", label="Email")
        
        messages = template.to_messages()
        
        assert isinstance(messages, list)
        assert len(messages) >= 2


class TestDashboardTemplate:
    """Test DashboardTemplate for multi-panel dashboards."""

    def test_dashboard_template_creation(self):
        """Test DashboardTemplate creation."""
        from praisonaiagents.ui.a2ui.templates import DashboardTemplate
        
        template = DashboardTemplate(
            surface_id="dashboard",
            title="My Dashboard"
        )
        
        assert template.surface_id == "dashboard"
        assert template.title == "My Dashboard"

    def test_add_panel(self):
        """Test adding a panel."""
        from praisonaiagents.ui.a2ui.templates import DashboardTemplate
        
        template = DashboardTemplate(surface_id="dashboard", title="Dashboard")
        template.add_panel(id="panel-1", title="Panel 1", content="Some content")
        
        assert len(template.panels) == 1
        assert template.panels[0]["id"] == "panel-1"

    def test_to_messages(self):
        """Test generating A2UI messages."""
        from praisonaiagents.ui.a2ui.templates import DashboardTemplate
        
        template = DashboardTemplate(surface_id="dashboard", title="Dashboard")
        template.add_panel(id="panel-1", title="Panel 1", content="Content 1")
        template.add_panel(id="panel-2", title="Panel 2", content="Content 2")
        
        messages = template.to_messages()
        
        assert isinstance(messages, list)
        assert len(messages) >= 2
