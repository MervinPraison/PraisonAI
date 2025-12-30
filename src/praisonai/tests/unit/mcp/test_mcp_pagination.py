"""
Unit tests for MCP pagination functionality.

Tests pagination for tools/list, resources/list, and prompts/list
per MCP 2025-11-25 specification.
"""

import pytest
from praisonai.mcp_server.registry import (
    MCPToolRegistry,
    MCPResourceRegistry,
    MCPPromptRegistry,
    encode_cursor,
    decode_cursor,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
)


class TestCursorEncoding:
    """Test cursor encoding/decoding."""
    
    def test_encode_cursor_simple(self):
        """Test encoding a simple offset."""
        cursor = encode_cursor(10)
        assert cursor  # Non-empty
        assert "=" not in cursor  # No padding
    
    def test_decode_cursor_simple(self):
        """Test decoding a simple cursor."""
        cursor = encode_cursor(10)
        offset, snapshot = decode_cursor(cursor)
        assert offset == 10
        assert snapshot is None
    
    def test_encode_decode_with_snapshot(self):
        """Test encoding/decoding with snapshot hash."""
        cursor = encode_cursor(25, "abc123")
        offset, snapshot = decode_cursor(cursor)
        assert offset == 25
        assert snapshot == "abc123"
    
    def test_decode_invalid_cursor(self):
        """Test decoding invalid cursor raises ValueError."""
        with pytest.raises(ValueError):
            decode_cursor("invalid!!!")
    
    def test_encode_zero_offset(self):
        """Test encoding offset 0."""
        cursor = encode_cursor(0)
        offset, _ = decode_cursor(cursor)
        assert offset == 0
    
    def test_encode_large_offset(self):
        """Test encoding large offset."""
        cursor = encode_cursor(999999)
        offset, _ = decode_cursor(cursor)
        assert offset == 999999


class TestToolRegistryPagination:
    """Test MCPToolRegistry pagination."""
    
    @pytest.fixture
    def registry_with_tools(self):
        """Create a registry with multiple tools."""
        registry = MCPToolRegistry()
        for i in range(75):
            registry.register(
                name=f"tool_{i:03d}",
                handler=lambda: None,
                description=f"Test tool {i}",
            )
        return registry
    
    def test_list_paginated_first_page(self, registry_with_tools):
        """Test getting first page of tools."""
        tools, next_cursor = registry_with_tools.list_paginated()
        assert len(tools) == DEFAULT_PAGE_SIZE
        assert next_cursor is not None
    
    def test_list_paginated_with_cursor(self, registry_with_tools):
        """Test getting second page with cursor."""
        _, next_cursor = registry_with_tools.list_paginated()
        tools, _ = registry_with_tools.list_paginated(cursor=next_cursor)
        assert len(tools) == 25  # 75 - 50 = 25
    
    def test_list_paginated_custom_page_size(self, registry_with_tools):
        """Test custom page size."""
        tools, next_cursor = registry_with_tools.list_paginated(page_size=10)
        assert len(tools) == 10
        assert next_cursor is not None
    
    def test_list_paginated_max_page_size(self, registry_with_tools):
        """Test page size is clamped to MAX_PAGE_SIZE."""
        tools, _ = registry_with_tools.list_paginated(page_size=200)
        assert len(tools) <= MAX_PAGE_SIZE
    
    def test_list_paginated_no_more_results(self):
        """Test no nextCursor when all results returned."""
        registry = MCPToolRegistry()
        for i in range(5):
            registry.register(name=f"tool_{i}", handler=lambda: None)
        
        tools, next_cursor = registry.list_paginated()
        assert len(tools) == 5
        assert next_cursor is None
    
    def test_list_paginated_invalid_cursor(self, registry_with_tools):
        """Test invalid cursor raises ValueError."""
        with pytest.raises(ValueError):
            registry_with_tools.list_paginated(cursor="invalid!!!")
    
    def test_list_paginated_out_of_range_cursor(self, registry_with_tools):
        """Test cursor with offset beyond total raises ValueError."""
        cursor = encode_cursor(1000)  # Beyond 75 tools
        with pytest.raises(ValueError):
            registry_with_tools.list_paginated(cursor=cursor)


class TestToolRegistrySearch:
    """Test MCPToolRegistry search functionality."""
    
    @pytest.fixture
    def registry_with_varied_tools(self):
        """Create a registry with varied tools for search testing."""
        registry = MCPToolRegistry()
        
        # Read-only tools
        registry._tools["memory.show"] = type(
            "MCPToolDefinition",
            (),
            {
                "name": "memory.show",
                "description": "Show memory contents",
                "handler": lambda: None,
                "input_schema": {},
                "category": "memory",
                "tags": ["read", "memory"],
                "read_only_hint": True,
                "destructive_hint": False,
                "idempotent_hint": False,
                "open_world_hint": False,
                "title": None,
                "annotations": None,
                "output_schema": None,
                "to_mcp_schema": lambda self: {"name": self.name, "description": self.description},
            },
        )()
        
        # Destructive tools
        registry._tools["file.delete"] = type(
            "MCPToolDefinition",
            (),
            {
                "name": "file.delete",
                "description": "Delete a file",
                "handler": lambda: None,
                "input_schema": {},
                "category": "file",
                "tags": ["write", "file"],
                "read_only_hint": False,
                "destructive_hint": True,
                "idempotent_hint": False,
                "open_world_hint": True,
                "title": None,
                "annotations": None,
                "output_schema": None,
                "to_mcp_schema": lambda self: {"name": self.name, "description": self.description},
            },
        )()
        
        # Web tool
        registry._tools["web.search"] = type(
            "MCPToolDefinition",
            (),
            {
                "name": "web.search",
                "description": "Search the web",
                "handler": lambda: None,
                "input_schema": {},
                "category": "web",
                "tags": ["search", "web"],
                "read_only_hint": True,
                "destructive_hint": False,
                "idempotent_hint": True,
                "open_world_hint": True,
                "title": None,
                "annotations": None,
                "output_schema": None,
                "to_mcp_schema": lambda self: {"name": self.name, "description": self.description},
            },
        )()
        
        return registry
    
    def test_search_by_query(self, registry_with_varied_tools):
        """Test searching by query text."""
        tools, _, total = registry_with_varied_tools.search(query="memory")
        assert total == 1
        assert tools[0]["name"] == "memory.show"
    
    def test_search_by_category(self, registry_with_varied_tools):
        """Test filtering by category."""
        tools, _, total = registry_with_varied_tools.search(category="web")
        assert total == 1
        assert tools[0]["name"] == "web.search"
    
    def test_search_by_read_only(self, registry_with_varied_tools):
        """Test filtering by readOnlyHint."""
        tools, _, total = registry_with_varied_tools.search(read_only=True)
        assert total == 2  # memory.show and web.search
    
    def test_search_no_results(self, registry_with_varied_tools):
        """Test search with no matching results."""
        tools, _, total = registry_with_varied_tools.search(query="nonexistent")
        assert total == 0
        assert len(tools) == 0
    
    def test_search_pagination(self, registry_with_varied_tools):
        """Test search with pagination."""
        tools, next_cursor, total = registry_with_varied_tools.search(page_size=1)
        assert len(tools) == 1
        assert total == 3
        assert next_cursor is not None


class TestResourceRegistryPagination:
    """Test MCPResourceRegistry pagination."""
    
    @pytest.fixture
    def registry_with_resources(self):
        """Create a registry with multiple resources."""
        registry = MCPResourceRegistry()
        for i in range(30):
            registry.register(
                uri=f"resource://test/{i}",
                handler=lambda: None,
                name=f"resource_{i}",
            )
        return registry
    
    def test_list_paginated_resources(self, registry_with_resources):
        """Test paginated resource listing."""
        resources, next_cursor = registry_with_resources.list_paginated(page_size=10)
        assert len(resources) == 10
        assert next_cursor is not None


class TestPromptRegistryPagination:
    """Test MCPPromptRegistry pagination."""
    
    @pytest.fixture
    def registry_with_prompts(self):
        """Create a registry with multiple prompts."""
        registry = MCPPromptRegistry()
        for i in range(20):
            registry.register(
                name=f"prompt_{i}",
                handler=lambda: None,
                description=f"Test prompt {i}",
            )
        return registry
    
    def test_list_paginated_prompts(self, registry_with_prompts):
        """Test paginated prompt listing."""
        prompts, next_cursor = registry_with_prompts.list_paginated(page_size=10)
        assert len(prompts) == 10
        assert next_cursor is not None
