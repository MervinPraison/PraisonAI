"""
Tests for A2UI Surface Builder

TDD: Write tests first, then implement the Surface class.
"""


class TestSurface:
    """Test Surface builder class."""

    def test_surface_creation(self):
        """Test Surface creation with ID and catalog."""
        from praisonaiagents.ui.a2ui.surface import Surface
        
        surface = Surface(surface_id="main")
        
        assert surface.surface_id == "main"
        assert surface.catalog_id is not None  # Should have default

    def test_surface_with_custom_catalog(self):
        """Test Surface with custom catalog ID."""
        from praisonaiagents.ui.a2ui.surface import Surface
        
        surface = Surface(
            surface_id="main",
            catalog_id="https://custom.catalog/v1"
        )
        
        assert surface.catalog_id == "https://custom.catalog/v1"

    def test_add_component(self):
        """Test adding a component to the surface."""
        from praisonaiagents.ui.a2ui.surface import Surface
        from praisonaiagents.ui.a2ui.types import TextComponent
        
        surface = Surface(surface_id="main")
        text = TextComponent(id="title", text="Hello World", usage_hint="h1")
        
        surface.add(text)
        
        assert len(surface.components) == 1
        assert surface.components[0].id == "title"

    def test_add_multiple_components(self):
        """Test adding multiple components."""
        from praisonaiagents.ui.a2ui.surface import Surface
        from praisonaiagents.ui.a2ui.types import TextComponent, ButtonComponent
        
        surface = Surface(surface_id="main")
        surface.add(TextComponent(id="title", text="Hello"))
        surface.add(ButtonComponent(id="btn", child="btn-text"))
        
        assert len(surface.components) == 2

    def test_set_data(self):
        """Test setting data model values."""
        from praisonaiagents.ui.a2ui.surface import Surface
        
        surface = Surface(surface_id="main")
        surface.set_data("title", "Hello World")
        surface.set_data("count", 42)
        
        assert surface.data["title"] == "Hello World"
        assert surface.data["count"] == 42

    def test_set_nested_data(self):
        """Test setting nested data model values."""
        from praisonaiagents.ui.a2ui.surface import Surface
        
        surface = Surface(surface_id="main")
        surface.set_data("user", {"name": "John", "age": 30})
        
        assert surface.data["user"]["name"] == "John"

    def test_to_messages_creates_surface(self):
        """Test to_messages generates CreateSurface message."""
        from praisonaiagents.ui.a2ui.surface import Surface
        from praisonaiagents.ui.a2ui.types import TextComponent
        
        surface = Surface(surface_id="main")
        surface.add(TextComponent(id="title", text="Hello"))
        
        messages = surface.to_messages()
        
        assert len(messages) >= 1
        assert "createSurface" in messages[0]
        assert messages[0]["createSurface"]["surfaceId"] == "main"

    def test_to_messages_includes_components(self):
        """Test to_messages includes UpdateComponents message."""
        from praisonaiagents.ui.a2ui.surface import Surface
        from praisonaiagents.ui.a2ui.types import TextComponent
        
        surface = Surface(surface_id="main")
        surface.add(TextComponent(id="title", text="Hello"))
        
        messages = surface.to_messages()
        
        # Should have createSurface and updateComponents
        assert len(messages) >= 2
        update_msg = next((m for m in messages if "updateComponents" in m), None)
        assert update_msg is not None
        assert len(update_msg["updateComponents"]["components"]) == 1

    def test_to_messages_includes_data_model(self):
        """Test to_messages includes UpdateDataModel message when data is set."""
        from praisonaiagents.ui.a2ui.surface import Surface
        from praisonaiagents.ui.a2ui.types import TextComponent
        
        surface = Surface(surface_id="main")
        surface.add(TextComponent(id="title", text="Hello"))
        surface.set_data("title", "Hello World")
        
        messages = surface.to_messages()
        
        # Should have createSurface, updateComponents, and updateDataModel
        assert len(messages) == 3
        data_msg = next((m for m in messages if "updateDataModel" in m), None)
        assert data_msg is not None
        assert data_msg["updateDataModel"]["value"]["title"] == "Hello World"

    def test_to_json(self):
        """Test to_json returns JSON string."""
        from praisonaiagents.ui.a2ui.surface import Surface
        from praisonaiagents.ui.a2ui.types import TextComponent
        import json
        
        surface = Surface(surface_id="main")
        surface.add(TextComponent(id="title", text="Hello"))
        
        json_str = surface.to_json()
        
        # Should be valid JSON
        parsed = json.loads(json_str)
        assert isinstance(parsed, list)
        assert len(parsed) >= 2


class TestSurfaceChaining:
    """Test Surface method chaining."""

    def test_add_returns_self(self):
        """Test add() returns self for chaining."""
        from praisonaiagents.ui.a2ui.surface import Surface
        from praisonaiagents.ui.a2ui.types import TextComponent
        
        surface = Surface(surface_id="main")
        result = surface.add(TextComponent(id="title", text="Hello"))
        
        assert result is surface

    def test_set_data_returns_self(self):
        """Test set_data() returns self for chaining."""
        from praisonaiagents.ui.a2ui.surface import Surface
        
        surface = Surface(surface_id="main")
        result = surface.set_data("key", "value")
        
        assert result is surface

    def test_fluent_api(self):
        """Test fluent API for building surfaces."""
        from praisonaiagents.ui.a2ui.surface import Surface
        from praisonaiagents.ui.a2ui.types import TextComponent, ButtonComponent
        
        surface = (
            Surface(surface_id="main")
            .add(TextComponent(id="title", text="Hello"))
            .add(ButtonComponent(id="btn", child="btn-text"))
            .set_data("title", "Hello World")
        )
        
        assert len(surface.components) == 2
        assert surface.data["title"] == "Hello World"


class TestSurfaceHelpers:
    """Test Surface helper methods."""

    def test_text_helper(self):
        """Test text() helper method."""
        from praisonaiagents.ui.a2ui.surface import Surface
        
        surface = Surface(surface_id="main")
        surface.text(id="title", text="Hello", usage_hint="h1")
        
        assert len(surface.components) == 1
        assert surface.components[0].id == "title"

    def test_button_helper(self):
        """Test button() helper method."""
        from praisonaiagents.ui.a2ui.surface import Surface
        
        surface = Surface(surface_id="main")
        surface.button(id="submit", child="submit-text", action_name="submit")
        
        assert len(surface.components) == 1
        assert surface.components[0].id == "submit"

    def test_card_helper(self):
        """Test card() helper method."""
        from praisonaiagents.ui.a2ui.surface import Surface
        
        surface = Surface(surface_id="main")
        surface.card(id="card-1", child="card-content")
        
        assert len(surface.components) == 1
        assert surface.components[0].id == "card-1"

    def test_row_helper(self):
        """Test row() helper method."""
        from praisonaiagents.ui.a2ui.surface import Surface
        
        surface = Surface(surface_id="main")
        surface.row(id="row-1", children=["col-1", "col-2"])
        
        assert len(surface.components) == 1
        assert surface.components[0].id == "row-1"

    def test_column_helper(self):
        """Test column() helper method."""
        from praisonaiagents.ui.a2ui.surface import Surface
        
        surface = Surface(surface_id="main")
        surface.column(id="col-1", children=["item-1", "item-2"])
        
        assert len(surface.components) == 1
        assert surface.components[0].id == "col-1"
