"""
Tests for A2UI Types Module

TDD: Write tests first, then implement the types.
"""



class TestA2UIMessageTypes:
    """Test A2UI message types: CreateSurface, UpdateComponents, UpdateDataModel, DeleteSurface."""

    def test_create_surface_message(self):
        """Test CreateSurface message creation."""
        from praisonaiagents.ui.a2ui.types import CreateSurfaceMessage
        
        msg = CreateSurfaceMessage(
            surface_id="main",
            catalog_id="https://a2ui.dev/standard"
        )
        
        assert msg.surface_id == "main"
        assert msg.catalog_id == "https://a2ui.dev/standard"
        
        # Test serialization
        data = msg.to_dict()
        assert "createSurface" in data
        assert data["createSurface"]["surfaceId"] == "main"
        assert data["createSurface"]["catalogId"] == "https://a2ui.dev/standard"

    def test_update_components_message(self):
        """Test UpdateComponents message creation."""
        from praisonaiagents.ui.a2ui.types import UpdateComponentsMessage, TextComponent
        
        text = TextComponent(id="title", text="Hello World", usage_hint="h1")
        msg = UpdateComponentsMessage(
            surface_id="main",
            components=[text]
        )
        
        assert msg.surface_id == "main"
        assert len(msg.components) == 1
        
        # Test serialization
        data = msg.to_dict()
        assert "updateComponents" in data
        assert data["updateComponents"]["surfaceId"] == "main"
        assert len(data["updateComponents"]["components"]) == 1

    def test_update_data_model_message(self):
        """Test UpdateDataModel message creation."""
        from praisonaiagents.ui.a2ui.types import UpdateDataModelMessage
        
        msg = UpdateDataModelMessage(
            surface_id="main",
            path="/",
            op="replace",
            value={"title": "Hello", "items": []}
        )
        
        assert msg.surface_id == "main"
        assert msg.path == "/"
        assert msg.op == "replace"
        assert msg.value == {"title": "Hello", "items": []}
        
        # Test serialization
        data = msg.to_dict()
        assert "updateDataModel" in data
        assert data["updateDataModel"]["surfaceId"] == "main"

    def test_delete_surface_message(self):
        """Test DeleteSurface message creation."""
        from praisonaiagents.ui.a2ui.types import DeleteSurfaceMessage
        
        msg = DeleteSurfaceMessage(surface_id="main")
        
        assert msg.surface_id == "main"
        
        # Test serialization
        data = msg.to_dict()
        assert "deleteSurface" in data
        assert data["deleteSurface"]["surfaceId"] == "main"


class TestA2UIComponentTypes:
    """Test A2UI component types."""

    def test_text_component(self):
        """Test Text component creation."""
        from praisonaiagents.ui.a2ui.types import TextComponent
        
        text = TextComponent(id="title", text="Hello World", usage_hint="h1")
        
        assert text.id == "title"
        assert text.text == "Hello World"
        assert text.usage_hint == "h1"
        
        # Test serialization
        data = text.to_dict()
        assert data["id"] == "title"
        assert data["component"] == "Text"
        assert data["text"] == "Hello World"
        assert data["usageHint"] == "h1"

    def test_text_component_with_path(self):
        """Test Text component with data binding path."""
        from praisonaiagents.ui.a2ui.types import TextComponent, PathBinding
        
        text = TextComponent(id="title", text=PathBinding(path="/title"))
        
        data = text.to_dict()
        assert data["text"] == {"path": "/title"}

    def test_image_component(self):
        """Test Image component creation."""
        from praisonaiagents.ui.a2ui.types import ImageComponent
        
        img = ImageComponent(
            id="hero",
            url="https://example.com/image.jpg",
            fit="cover",
            usage_hint="header"
        )
        
        assert img.id == "hero"
        assert img.url == "https://example.com/image.jpg"
        assert img.fit == "cover"
        
        data = img.to_dict()
        assert data["component"] == "Image"
        assert data["url"] == "https://example.com/image.jpg"

    def test_button_component(self):
        """Test Button component creation."""
        from praisonaiagents.ui.a2ui.types import ButtonComponent, Action, ActionContext
        
        action = Action(
            name="submit",
            context=[
                ActionContext(key="value", value="test")
            ]
        )
        btn = ButtonComponent(
            id="submit-btn",
            child="submit-text",
            primary=True,
            action=action
        )
        
        assert btn.id == "submit-btn"
        assert btn.child == "submit-text"
        assert btn.primary is True
        
        data = btn.to_dict()
        assert data["component"] == "Button"
        assert data["action"]["name"] == "submit"

    def test_card_component(self):
        """Test Card component creation."""
        from praisonaiagents.ui.a2ui.types import CardComponent
        
        card = CardComponent(id="card-1", child="card-content")
        
        assert card.id == "card-1"
        assert card.child == "card-content"
        
        data = card.to_dict()
        assert data["component"] == "Card"
        assert data["child"] == "card-content"

    def test_row_component(self):
        """Test Row component creation."""
        from praisonaiagents.ui.a2ui.types import RowComponent
        
        row = RowComponent(id="row-1", children=["col-1", "col-2"])
        
        assert row.id == "row-1"
        assert row.children == ["col-1", "col-2"]
        
        data = row.to_dict()
        assert data["component"] == "Row"
        assert data["children"] == ["col-1", "col-2"]

    def test_column_component(self):
        """Test Column component creation."""
        from praisonaiagents.ui.a2ui.types import ColumnComponent
        
        col = ColumnComponent(id="col-1", children=["item-1", "item-2"])
        
        assert col.id == "col-1"
        assert col.children == ["item-1", "item-2"]
        
        data = col.to_dict()
        assert data["component"] == "Column"

    def test_list_component(self):
        """Test List component creation."""
        from praisonaiagents.ui.a2ui.types import ListComponent, ChildrenTemplate
        
        template = ChildrenTemplate(component_id="item-template", path="/items")
        lst = ListComponent(id="item-list", direction="vertical", children=template)
        
        assert lst.id == "item-list"
        assert lst.direction == "vertical"
        
        data = lst.to_dict()
        assert data["component"] == "List"
        assert data["children"]["componentId"] == "item-template"
        assert data["children"]["path"] == "/items"

    def test_text_field_component(self):
        """Test TextField component creation."""
        from praisonaiagents.ui.a2ui.types import TextFieldComponent, PathBinding
        
        field = TextFieldComponent(
            id="name-field",
            label="Name",
            text=PathBinding(path="/name"),
            field_type="text"
        )
        
        assert field.id == "name-field"
        assert field.label == "Name"
        
        data = field.to_dict()
        assert data["component"] == "TextField"
        assert data["label"] == "Name"
        assert data["text"] == {"path": "/name"}

    def test_checkbox_component(self):
        """Test CheckBox component creation."""
        from praisonaiagents.ui.a2ui.types import CheckBoxComponent, PathBinding
        
        cb = CheckBoxComponent(
            id="agree-cb",
            label="I agree",
            checked=PathBinding(path="/agreed")
        )
        
        data = cb.to_dict()
        assert data["component"] == "CheckBox"
        assert data["label"] == "I agree"

    def test_slider_component(self):
        """Test Slider component creation."""
        from praisonaiagents.ui.a2ui.types import SliderComponent
        
        slider = SliderComponent(
            id="volume",
            min_value=0,
            max_value=100,
            value=50
        )
        
        data = slider.to_dict()
        assert data["component"] == "Slider"
        assert data["min"] == 0
        assert data["max"] == 100


class TestDataBindingTypes:
    """Test data binding types."""

    def test_path_binding(self):
        """Test PathBinding for data model references."""
        from praisonaiagents.ui.a2ui.types import PathBinding
        
        path = PathBinding(path="/user/name")
        
        assert path.path == "/user/name"
        assert path.to_dict() == {"path": "/user/name"}

    def test_string_or_path_literal(self):
        """Test StringOrPath with literal string."""
        from praisonaiagents.ui.a2ui.types import resolve_string_or_path
        
        result = resolve_string_or_path("Hello")
        assert result == "Hello"

    def test_string_or_path_binding(self):
        """Test StringOrPath with path binding."""
        from praisonaiagents.ui.a2ui.types import resolve_string_or_path, PathBinding
        
        result = resolve_string_or_path(PathBinding(path="/title"))
        assert result == {"path": "/title"}


class TestActionTypes:
    """Test action types for button events."""

    def test_action_creation(self):
        """Test Action creation."""
        from praisonaiagents.ui.a2ui.types import Action, ActionContext
        
        action = Action(
            name="book_restaurant",
            context=[
                ActionContext(key="restaurantName", value="The Fancy Place"),
                ActionContext(key="address", value="123 Main St")
            ]
        )
        
        assert action.name == "book_restaurant"
        assert len(action.context) == 2
        
        data = action.to_dict()
        assert data["name"] == "book_restaurant"
        assert len(data["context"]) == 2
        assert data["context"][0]["key"] == "restaurantName"

    def test_action_context_with_path(self):
        """Test ActionContext with path binding."""
        from praisonaiagents.ui.a2ui.types import ActionContext, PathBinding
        
        ctx = ActionContext(key="name", value=PathBinding(path="/restaurant/name"))
        
        data = ctx.to_dict()
        assert data["key"] == "name"
        assert data["value"] == {"path": "/restaurant/name"}
