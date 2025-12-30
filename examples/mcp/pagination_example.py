#!/usr/bin/env python3
"""
MCP Pagination Example

Demonstrates the pagination feature for tools/list, resources/list, and prompts/list
per MCP 2025-11-25 specification.

Usage:
    python pagination_example.py
"""

from praisonai.mcp_server.registry import (
    MCPToolRegistry,
    encode_cursor,
    decode_cursor,
    DEFAULT_PAGE_SIZE,
)


def demo_tool_pagination():
    """Demonstrate tool pagination."""
    print("\n" + "=" * 60)
    print("Tool Pagination Demo")
    print("=" * 60)
    
    # Create registry with many tools
    registry = MCPToolRegistry()
    for i in range(75):
        registry.register(
            name=f"example.tool_{i:03d}",
            handler=lambda: f"Tool {i} executed",
            description=f"Example tool number {i}",
        )
    
    print(f"\nRegistered {len(registry.list_all())} tools")
    print(f"Default page size: {DEFAULT_PAGE_SIZE}")
    
    # First page
    print("\n--- First Page ---")
    tools, next_cursor = registry.list_paginated()
    print(f"Tools returned: {len(tools)}")
    print(f"First tool: {tools[0]['name']}")
    print(f"Last tool: {tools[-1]['name']}")
    print(f"Next cursor: {next_cursor}")
    
    # Second page
    print("\n--- Second Page (using cursor) ---")
    tools2, next_cursor2 = registry.list_paginated(cursor=next_cursor)
    print(f"Tools returned: {len(tools2)}")
    print(f"First tool: {tools2[0]['name']}")
    print(f"Last tool: {tools2[-1]['name']}")
    print(f"Next cursor: {next_cursor2}")
    
    # Custom page size
    print("\n--- Custom Page Size (10) ---")
    tools3, next_cursor3 = registry.list_paginated(page_size=10)
    print(f"Tools returned: {len(tools3)}")
    print(f"Next cursor: {next_cursor3}")


def demo_cursor_encoding():
    """Demonstrate cursor encoding/decoding."""
    print("\n" + "=" * 60)
    print("Cursor Encoding Demo")
    print("=" * 60)
    
    # Simple offset
    cursor1 = encode_cursor(50)
    offset1, _ = decode_cursor(cursor1)
    print(f"\nOffset 50 -> Cursor: {cursor1}")
    print(f"Decoded back: offset={offset1}")
    
    # With snapshot hash
    cursor2 = encode_cursor(100, "abc123hash")
    offset2, snapshot = decode_cursor(cursor2)
    print(f"\nOffset 100 with snapshot -> Cursor: {cursor2}")
    print(f"Decoded back: offset={offset2}, snapshot={snapshot}")


def demo_tool_search():
    """Demonstrate tool search with pagination."""
    print("\n" + "=" * 60)
    print("Tool Search Demo")
    print("=" * 60)
    
    registry = MCPToolRegistry()
    
    # Register tools with different categories
    from praisonai.mcp_server.registry import MCPToolDefinition
    
    tools_data = [
        ("memory.show", "Show memory contents", "memory", True, False),
        ("memory.clear", "Clear memory", "memory", False, True),
        ("file.read", "Read a file", "file", True, False),
        ("file.write", "Write to a file", "file", False, True),
        ("file.delete", "Delete a file", "file", False, True),
        ("web.search", "Search the web", "web", True, False),
        ("web.fetch", "Fetch a URL", "web", True, False),
    ]
    
    for name, desc, category, read_only, destructive in tools_data:
        registry._tools[name] = MCPToolDefinition(
            name=name,
            description=desc,
            handler=lambda: None,
            input_schema={"type": "object"},
            category=category,
            read_only_hint=read_only,
            destructive_hint=destructive,
        )
    
    # Search by query
    print("\n--- Search: 'memory' ---")
    results, _, total = registry.search(query="memory")
    print(f"Found {total} tools:")
    for tool in results:
        print(f"  - {tool['name']}")
    
    # Search by category
    print("\n--- Search: category='file' ---")
    results, _, total = registry.search(category="file")
    print(f"Found {total} tools:")
    for tool in results:
        print(f"  - {tool['name']}")
    
    # Search read-only tools
    print("\n--- Search: read_only=True ---")
    results, _, total = registry.search(read_only=True)
    print(f"Found {total} read-only tools:")
    for tool in results:
        print(f"  - {tool['name']}")


def main():
    """Run all demos."""
    print("\n" + "#" * 60)
    print("# MCP Pagination & Search Examples")
    print("# MCP Protocol Version: 2025-11-25")
    print("#" * 60)
    
    demo_cursor_encoding()
    demo_tool_pagination()
    demo_tool_search()
    
    print("\n" + "=" * 60)
    print("All demos completed!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
