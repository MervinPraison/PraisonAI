"""Example: Resolve tool names to callable tools."""
from praisonai.templates.tool_override import (
    create_tool_registry_with_overrides,
    resolve_tools,
)

# Create registry with defaults
registry = create_tool_registry_with_overrides(include_defaults=True)

print(f"Registry contains {len(registry)} tools")

# Resolve tool names
tool_names = ["shell_tool", "internet_search"]
resolved = resolve_tools(tool_names, registry=registry)

print(f"\nResolved {len(resolved)} tools:")
for tool in resolved:
    print(f"  - {getattr(tool, '__name__', type(tool).__name__)}")
