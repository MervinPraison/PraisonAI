"""
Tests for A2UI Extension Module

TDD: Write tests first, then implement the extension.
"""


class TestA2UIExtension:
    """Test A2UI extension helpers for A2A integration."""

    def test_a2ui_mime_type(self):
        """Test A2UI MIME type constant."""
        from praisonaiagents.ui.a2ui.extension import A2UI_MIME_TYPE
        
        assert A2UI_MIME_TYPE == "application/json+a2ui"

    def test_a2ui_extension_uri(self):
        """Test A2UI extension URI constant."""
        from praisonaiagents.ui.a2ui.extension import A2UI_EXTENSION_URI
        
        assert "a2ui" in A2UI_EXTENSION_URI.lower()

    def test_create_a2ui_part(self):
        """Test create_a2ui_part wraps A2UI data in A2A DataPart."""
        from praisonaiagents.ui.a2ui.extension import create_a2ui_part, A2UI_MIME_TYPE
        
        a2ui_data = {
            "createSurface": {
                "surfaceId": "main",
                "catalogId": "https://a2ui.dev/standard"
            }
        }
        
        part = create_a2ui_part(a2ui_data)
        
        # Should return a Part with DataPart root
        assert part is not None
        assert hasattr(part, 'data')
        assert part.data == a2ui_data
        assert part.metadata is not None
        assert part.metadata.get("mimeType") == A2UI_MIME_TYPE

    def test_is_a2ui_part_true(self):
        """Test is_a2ui_part returns True for A2UI parts."""
        from praisonaiagents.ui.a2ui.extension import create_a2ui_part, is_a2ui_part
        
        a2ui_data = {"createSurface": {"surfaceId": "main", "catalogId": "test"}}
        part = create_a2ui_part(a2ui_data)
        
        assert is_a2ui_part(part) is True

    def test_is_a2ui_part_false(self):
        """Test is_a2ui_part returns False for non-A2UI parts."""
        from praisonaiagents.ui.a2ui.extension import is_a2ui_part
        from praisonaiagents.ui.a2ui.types import A2UIDataPart
        
        # Create a regular data part without A2UI mime type
        part = A2UIDataPart(data={"foo": "bar"}, metadata={"mimeType": "application/json"})
        
        assert is_a2ui_part(part) is False

    def test_get_a2ui_agent_extension(self):
        """Test get_a2ui_agent_extension returns AgentExtension config."""
        from praisonaiagents.ui.a2ui.extension import get_a2ui_agent_extension
        
        ext = get_a2ui_agent_extension()
        
        assert ext is not None
        assert hasattr(ext, 'uri')
        assert "a2ui" in ext.uri.lower()
        assert hasattr(ext, 'description')

    def test_get_a2ui_agent_extension_with_inline_catalog(self):
        """Test get_a2ui_agent_extension with inline catalog support."""
        from praisonaiagents.ui.a2ui.extension import get_a2ui_agent_extension
        
        ext = get_a2ui_agent_extension(accepts_inline_custom_catalog=True)
        
        assert ext.params is not None
        assert ext.params.get("acceptsInlineCustomCatalog") is True

    def test_standard_catalog_id(self):
        """Test standard catalog ID constant."""
        from praisonaiagents.ui.a2ui.extension import STANDARD_CATALOG_ID
        
        assert "standard_catalog" in STANDARD_CATALOG_ID.lower() or "a2ui" in STANDARD_CATALOG_ID.lower()


class TestA2UIDataPart:
    """Test A2UI DataPart type."""

    def test_a2ui_data_part_creation(self):
        """Test A2UIDataPart creation."""
        from praisonaiagents.ui.a2ui.types import A2UIDataPart
        
        part = A2UIDataPart(
            data={"test": "value"},
            metadata={"mimeType": "application/json+a2ui"}
        )
        
        assert part.data == {"test": "value"}
        assert part.metadata["mimeType"] == "application/json+a2ui"

    def test_a2ui_data_part_to_dict(self):
        """Test A2UIDataPart serialization."""
        from praisonaiagents.ui.a2ui.types import A2UIDataPart
        
        part = A2UIDataPart(
            data={"createSurface": {"surfaceId": "main"}},
            metadata={"mimeType": "application/json+a2ui"}
        )
        
        data = part.to_dict()
        assert "data" in data
        assert "metadata" in data
