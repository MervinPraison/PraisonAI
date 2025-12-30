"""
Unit tests for MCP tool annotations.

Tests MCP 2025-11-25 tool annotation hints:
- readOnlyHint
- destructiveHint
- idempotentHint
- openWorldHint
"""

from praisonai.mcp_server.registry import MCPToolDefinition, MCPToolRegistry


class TestMCPToolDefinition:
    """Test MCPToolDefinition with annotations."""
    
    def test_default_annotations(self):
        """Test default annotation values per MCP 2025-11-25 spec."""
        tool = MCPToolDefinition(
            name="test.tool",
            description="Test tool",
            handler=lambda: None,
            input_schema={"type": "object"},
        )
        
        # Default values per spec
        assert tool.read_only_hint is False
        assert tool.destructive_hint is True
        assert tool.idempotent_hint is False
        assert tool.open_world_hint is True
    
    def test_custom_annotations(self):
        """Test custom annotation values."""
        tool = MCPToolDefinition(
            name="test.read_only",
            description="Read-only tool",
            handler=lambda: None,
            input_schema={"type": "object"},
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
        
        assert tool.read_only_hint is True
        assert tool.destructive_hint is False
        assert tool.idempotent_hint is True
        assert tool.open_world_hint is False
    
    def test_to_mcp_schema_includes_annotations(self):
        """Test that to_mcp_schema includes all annotation hints."""
        tool = MCPToolDefinition(
            name="test.tool",
            description="Test tool",
            handler=lambda: None,
            input_schema={"type": "object"},
            read_only_hint=True,
            destructive_hint=False,
        )
        
        schema = tool.to_mcp_schema()
        
        assert "annotations" in schema
        annotations = schema["annotations"]
        assert annotations["readOnlyHint"] is True
        assert annotations["destructiveHint"] is False
        assert annotations["idempotentHint"] is False
        assert annotations["openWorldHint"] is True
    
    def test_to_mcp_schema_with_title(self):
        """Test that title is included in annotations."""
        tool = MCPToolDefinition(
            name="test.tool",
            description="Test tool",
            handler=lambda: None,
            input_schema={"type": "object"},
            title="My Test Tool",
        )
        
        schema = tool.to_mcp_schema()
        assert schema["annotations"]["title"] == "My Test Tool"
    
    def test_to_mcp_schema_preserves_custom_annotations(self):
        """Test that custom annotations are preserved."""
        tool = MCPToolDefinition(
            name="test.tool",
            description="Test tool",
            handler=lambda: None,
            input_schema={"type": "object"},
            annotations={"customKey": "customValue"},
        )
        
        schema = tool.to_mcp_schema()
        assert schema["annotations"]["customKey"] == "customValue"
        # Standard hints should still be present
        assert "readOnlyHint" in schema["annotations"]
    
    def test_category_and_tags(self):
        """Test category and tags fields."""
        tool = MCPToolDefinition(
            name="test.tool",
            description="Test tool",
            handler=lambda: None,
            input_schema={"type": "object"},
            category="testing",
            tags=["unit", "test"],
        )
        
        assert tool.category == "testing"
        assert tool.tags == ["unit", "test"]


class TestToolRegistryWithAnnotations:
    """Test MCPToolRegistry with annotated tools."""
    
    def test_register_tool_with_annotations(self):
        """Test registering a tool with annotations."""
        registry = MCPToolRegistry()
        
        registry._tools["annotated.tool"] = MCPToolDefinition(
            name="annotated.tool",
            description="Annotated tool",
            handler=lambda: None,
            input_schema={"type": "object"},
            read_only_hint=True,
            category="test",
        )
        
        tool = registry.get("annotated.tool")
        assert tool is not None
        assert tool.read_only_hint is True
        assert tool.category == "test"
    
    def test_list_schemas_includes_annotations(self):
        """Test that list_schemas includes annotations."""
        registry = MCPToolRegistry()
        
        registry._tools["test.tool"] = MCPToolDefinition(
            name="test.tool",
            description="Test tool",
            handler=lambda: None,
            input_schema={"type": "object"},
            read_only_hint=True,
        )
        
        schemas = registry.list_schemas()
        assert len(schemas) == 1
        assert "annotations" in schemas[0]
        assert schemas[0]["annotations"]["readOnlyHint"] is True


class TestAnnotationInference:
    """Test annotation inference from tool names."""
    
    def test_read_only_inference(self):
        """Test that read-only tools are inferred from name patterns."""
        from praisonai.mcp_server.adapters.tools_bridge import _infer_tool_hints
        
        # Read-only patterns
        for pattern in ["show", "list", "get", "read", "search", "find", "query"]:
            hints = _infer_tool_hints(f"test.{pattern}")
            assert hints["read_only_hint"] is True, f"Pattern '{pattern}' should be read-only"
            assert hints["destructive_hint"] is False
    
    def test_destructive_default(self):
        """Test that unknown tools default to destructive."""
        from praisonai.mcp_server.adapters.tools_bridge import _infer_tool_hints
        
        hints = _infer_tool_hints("test.unknown_action")
        assert hints["destructive_hint"] is True
    
    def test_idempotent_inference(self):
        """Test idempotent inference from name patterns."""
        from praisonai.mcp_server.adapters.tools_bridge import _infer_tool_hints
        
        for pattern in ["set", "update", "configure"]:
            hints = _infer_tool_hints(f"test.{pattern}")
            assert hints["idempotent_hint"] is True, f"Pattern '{pattern}' should be idempotent"
    
    def test_closed_world_inference(self):
        """Test closed-world inference from name patterns."""
        from praisonai.mcp_server.adapters.tools_bridge import _infer_tool_hints
        
        for pattern in ["memory", "session", "config", "local"]:
            hints = _infer_tool_hints(f"test.{pattern}.action")
            assert hints["open_world_hint"] is False, f"Pattern '{pattern}' should be closed-world"
