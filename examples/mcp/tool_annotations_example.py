#!/usr/bin/env python3
"""
MCP Tool Annotations Example

Demonstrates the MCP 2025-11-25 tool annotation hints:
- readOnlyHint: Tool only reads data, doesn't modify
- destructiveHint: Tool may have destructive side effects
- idempotentHint: Tool can be called multiple times with same result
- openWorldHint: Tool interacts with external world

Usage:
    python tool_annotations_example.py
"""

import json
from praisonai.mcp_server.registry import MCPToolDefinition, MCPToolRegistry


def demo_default_annotations():
    """Demonstrate default annotation values."""
    print("\n" + "=" * 60)
    print("Default Annotations Demo")
    print("=" * 60)
    
    tool = MCPToolDefinition(
        name="example.default",
        description="Tool with default annotations",
        handler=lambda: None,
        input_schema={"type": "object"},
    )
    
    print("\nDefault annotation values (per MCP 2025-11-25 spec):")
    print(f"  readOnlyHint:     {tool.read_only_hint} (default: False)")
    print(f"  destructiveHint:  {tool.destructive_hint} (default: True)")
    print(f"  idempotentHint:   {tool.idempotent_hint} (default: False)")
    print(f"  openWorldHint:    {tool.open_world_hint} (default: True)")


def demo_read_only_tool():
    """Demonstrate a read-only tool."""
    print("\n" + "=" * 60)
    print("Read-Only Tool Demo")
    print("=" * 60)
    
    tool = MCPToolDefinition(
        name="memory.show",
        description="Show memory contents without modification",
        handler=lambda: {"memory": "contents"},
        input_schema={"type": "object"},
        read_only_hint=True,
        destructive_hint=False,
    )
    
    schema = tool.to_mcp_schema()
    print("\nRead-only tool schema:")
    print(json.dumps(schema, indent=2))


def demo_destructive_tool():
    """Demonstrate a destructive tool."""
    print("\n" + "=" * 60)
    print("Destructive Tool Demo")
    print("=" * 60)
    
    tool = MCPToolDefinition(
        name="file.delete",
        description="Delete a file permanently",
        handler=lambda path: f"Deleted {path}",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to delete"}
            },
            "required": ["path"]
        },
        destructive_hint=True,
        idempotent_hint=False,  # Deleting twice has different effects
    )
    
    schema = tool.to_mcp_schema()
    print("\nDestructive tool schema:")
    print(json.dumps(schema, indent=2))


def demo_idempotent_tool():
    """Demonstrate an idempotent tool."""
    print("\n" + "=" * 60)
    print("Idempotent Tool Demo")
    print("=" * 60)
    
    tool = MCPToolDefinition(
        name="config.set",
        description="Set a configuration value (can be called multiple times safely)",
        handler=lambda key, value: f"Set {key}={value}",
        input_schema={
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "value": {"type": "string"}
            },
            "required": ["key", "value"]
        },
        idempotent_hint=True,
        destructive_hint=False,
    )
    
    schema = tool.to_mcp_schema()
    print("\nIdempotent tool schema:")
    print(json.dumps(schema, indent=2))


def demo_closed_world_tool():
    """Demonstrate a closed-world tool (openWorldHint=False)."""
    print("\n" + "=" * 60)
    print("Closed-World Tool Demo")
    print("=" * 60)
    
    tool = MCPToolDefinition(
        name="session.get",
        description="Get session data (internal only, no external interaction)",
        handler=lambda session_id: {"session": session_id},
        input_schema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string"}
            }
        },
        read_only_hint=True,
        destructive_hint=False,
        open_world_hint=False,  # Internal tool, no external interaction
    )
    
    schema = tool.to_mcp_schema()
    print("\nClosed-world tool schema:")
    print(json.dumps(schema, indent=2))


def demo_tool_with_title():
    """Demonstrate tool with custom title annotation."""
    print("\n" + "=" * 60)
    print("Tool with Title Demo")
    print("=" * 60)
    
    tool = MCPToolDefinition(
        name="praisonai.workflow.run",
        description="Execute a PraisonAI workflow from YAML definition",
        handler=lambda workflow: "Workflow executed",
        input_schema={"type": "object"},
        title="Run AI Workflow",  # Human-friendly title
        category="workflow",
        tags=["ai", "automation", "workflow"],
    )
    
    schema = tool.to_mcp_schema()
    print("\nTool with title:")
    print(json.dumps(schema, indent=2))
    print(f"\nCategory: {tool.category}")
    print(f"Tags: {tool.tags}")


def demo_registry_with_annotations():
    """Demonstrate registry with annotated tools."""
    print("\n" + "=" * 60)
    print("Registry with Annotated Tools Demo")
    print("=" * 60)
    
    registry = MCPToolRegistry()
    
    # Register tools with different annotation profiles
    registry._tools["read.data"] = MCPToolDefinition(
        name="read.data",
        description="Read data",
        handler=lambda: None,
        input_schema={"type": "object"},
        read_only_hint=True,
        destructive_hint=False,
    )
    
    registry._tools["write.data"] = MCPToolDefinition(
        name="write.data",
        description="Write data",
        handler=lambda: None,
        input_schema={"type": "object"},
        read_only_hint=False,
        destructive_hint=True,
    )
    
    # Search for read-only tools
    results, _, total = registry.search(read_only=True)
    print(f"\nRead-only tools ({total}):")
    for tool in results:
        print(f"  - {tool['name']}")
    
    # Search for destructive tools
    results, _, total = registry.search(read_only=False)
    print(f"\nNon-read-only tools ({total}):")
    for tool in results:
        print(f"  - {tool['name']}")


def main():
    """Run all demos."""
    print("\n" + "#" * 60)
    print("# MCP Tool Annotations Examples")
    print("# MCP Protocol Version: 2025-11-25")
    print("#" * 60)
    
    demo_default_annotations()
    demo_read_only_tool()
    demo_destructive_tool()
    demo_idempotent_tool()
    demo_closed_world_tool()
    demo_tool_with_title()
    demo_registry_with_annotations()
    
    print("\n" + "=" * 60)
    print("All demos completed!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
