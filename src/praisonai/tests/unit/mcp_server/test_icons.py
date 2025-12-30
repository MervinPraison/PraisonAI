"""
Unit tests for MCP Icons and Rich Metadata

Tests for IconMetadata, RichMetadata, and helper functions.
"""


class TestIconMetadata:
    """Tests for IconMetadata dataclass."""
    
    def test_icon_from_url(self):
        """Test icon from URL."""
        from praisonai.mcp_server.icons import IconMetadata
        
        icon = IconMetadata.from_url("https://example.com/icon.svg")
        
        assert icon.url == "https://example.com/icon.svg"
        assert icon.is_valid() is True
    
    def test_icon_from_data_uri(self):
        """Test icon from data URI."""
        from praisonai.mcp_server.icons import IconMetadata
        
        data_uri = "data:image/svg+xml;base64,PHN2Zz4="
        icon = IconMetadata.from_url(data_uri)
        
        assert icon.data_uri == data_uri
        assert icon.url is None
        assert icon.is_valid() is True
    
    def test_icon_from_name(self):
        """Test icon from name."""
        from praisonai.mcp_server.icons import IconMetadata
        
        icon = IconMetadata.from_name("search", alt_text="Search icon")
        
        assert icon.icon_name == "search"
        assert icon.alt_text == "Search icon"
        assert icon.is_valid() is True
    
    def test_icon_to_dict_url(self):
        """Test icon serialization with URL."""
        from praisonai.mcp_server.icons import IconMetadata
        
        icon = IconMetadata(url="https://example.com/icon.png", alt_text="Icon")
        result = icon.to_dict()
        
        assert result["url"] == "https://example.com/icon.png"
        assert result["alt"] == "Icon"
    
    def test_icon_to_dict_name(self):
        """Test icon serialization with name."""
        from praisonai.mcp_server.icons import IconMetadata
        
        icon = IconMetadata(icon_name="settings")
        result = icon.to_dict()
        
        assert result["name"] == "settings"
    
    def test_icon_from_dict(self):
        """Test icon from dictionary."""
        from praisonai.mcp_server.icons import IconMetadata
        
        data = {"url": "https://example.com/icon.svg", "alt": "My Icon"}
        icon = IconMetadata.from_dict(data)
        
        assert icon.url == "https://example.com/icon.svg"
        assert icon.alt_text == "My Icon"
    
    def test_invalid_icon(self):
        """Test invalid icon."""
        from praisonai.mcp_server.icons import IconMetadata
        
        icon = IconMetadata()
        
        assert icon.is_valid() is False


class TestValidateIconUrl:
    """Tests for validate_icon_url function."""
    
    def test_valid_http_url(self):
        """Test valid HTTP URL."""
        from praisonai.mcp_server.icons import validate_icon_url
        
        assert validate_icon_url("https://example.com/icon.png") is True
        assert validate_icon_url("http://example.com/icon.svg") is True
    
    def test_valid_data_uri(self):
        """Test valid data URI."""
        from praisonai.mcp_server.icons import validate_icon_url
        
        assert validate_icon_url("data:image/png;base64,abc123") is True
        assert validate_icon_url("data:image/svg+xml;base64,xyz") is True
    
    def test_invalid_url(self):
        """Test invalid URLs."""
        from praisonai.mcp_server.icons import validate_icon_url
        
        assert validate_icon_url("") is False
        assert validate_icon_url("ftp://example.com/icon.png") is False
        assert validate_icon_url("not-a-url") is False


class TestValidateIconFormat:
    """Tests for validate_icon_format function."""
    
    def test_format_from_extension(self):
        """Test format detection from extension."""
        from praisonai.mcp_server.icons import validate_icon_format
        
        assert validate_icon_format("https://example.com/icon.svg") == "svg"
        assert validate_icon_format("https://example.com/icon.png") == "png"
        assert validate_icon_format("https://example.com/icon.jpg") == "jpg"
    
    def test_format_from_data_uri(self):
        """Test format detection from data URI."""
        from praisonai.mcp_server.icons import validate_icon_format
        
        assert validate_icon_format("data:image/png;base64,abc") == "png"
        assert validate_icon_format("data:image/svg;base64,xyz") == "svg"
    
    def test_unknown_format(self):
        """Test unknown format."""
        from praisonai.mcp_server.icons import validate_icon_format
        
        assert validate_icon_format("https://example.com/icon") is None
        assert validate_icon_format("") is None


class TestRichMetadata:
    """Tests for RichMetadata dataclass."""
    
    def test_rich_metadata_creation(self):
        """Test rich metadata creation."""
        from praisonai.mcp_server.icons import RichMetadata, IconMetadata
        
        icon = IconMetadata.from_name("tool")
        metadata = RichMetadata(
            icon=icon,
            author="PraisonAI",
            version="1.0.0",
            tags=["ai", "tool"],
        )
        
        assert metadata.icon is not None
        assert metadata.author == "PraisonAI"
        assert metadata.version == "1.0.0"
        assert metadata.tags == ["ai", "tool"]
    
    def test_rich_metadata_to_dict(self):
        """Test rich metadata serialization."""
        from praisonai.mcp_server.icons import RichMetadata, IconMetadata
        
        metadata = RichMetadata(
            icon=IconMetadata.from_url("https://example.com/icon.svg"),
            documentation_url="https://docs.example.com",
            license="Apache-2.0",
        )
        
        result = metadata.to_dict()
        
        assert "icon" in result
        assert result["documentationUrl"] == "https://docs.example.com"
        assert result["license"] == "Apache-2.0"
    
    def test_rich_metadata_from_dict(self):
        """Test rich metadata from dictionary."""
        from praisonai.mcp_server.icons import RichMetadata
        
        data = {
            "icon": {"url": "https://example.com/icon.svg"},
            "author": "Test",
            "version": "2.0.0",
        }
        
        metadata = RichMetadata.from_dict(data)
        
        assert metadata.icon is not None
        assert metadata.author == "Test"
        assert metadata.version == "2.0.0"


class TestSchemaHelpers:
    """Tests for schema helper functions."""
    
    def test_add_icon_to_schema(self):
        """Test adding icon to schema."""
        from praisonai.mcp_server.icons import add_icon_to_schema, IconMetadata
        
        schema = {"name": "test-tool"}
        icon = IconMetadata.from_name("wrench")
        
        result = add_icon_to_schema(schema, icon)
        
        assert "icon" in result
        assert result["icon"]["name"] == "wrench"
    
    def test_add_metadata_to_schema(self):
        """Test adding metadata to schema."""
        from praisonai.mcp_server.icons import add_metadata_to_schema, RichMetadata
        
        schema = {"name": "test-tool"}
        metadata = RichMetadata(author="Test", version="1.0.0")
        
        result = add_metadata_to_schema(schema, metadata)
        
        assert "_meta" in result
        assert result["_meta"]["author"] == "Test"


class TestStandardIcons:
    """Tests for standard icon functions."""
    
    def test_get_standard_icon(self):
        """Test getting standard icons."""
        from praisonai.mcp_server.icons import get_standard_icon
        
        assert get_standard_icon("run") == "play"
        assert get_standard_icon("search") == "search"
        assert get_standard_icon("settings") == "settings"
        assert get_standard_icon("delete") == "trash"
    
    def test_get_standard_icon_partial_match(self):
        """Test partial match for standard icons."""
        from praisonai.mcp_server.icons import get_standard_icon
        
        assert get_standard_icon("run_task") == "play"
        assert get_standard_icon("search_web") == "search"
    
    def test_get_standard_icon_not_found(self):
        """Test icon not found."""
        from praisonai.mcp_server.icons import get_standard_icon
        
        assert get_standard_icon("unknown_operation") is None
