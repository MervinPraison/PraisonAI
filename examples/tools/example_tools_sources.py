"""Example: Configure tool sources for templates."""
from praisonai.templates.tool_override import create_tool_registry_with_overrides

# Create registry with tools_sources
registry = create_tool_registry_with_overrides(
    tools_sources=["praisonai_tools.video"],
    include_defaults=True,
)

print(f"Registry with tools_sources: {len(registry)} tools")

# List some tools
for name in list(registry.keys())[:10]:
    print(f"  - {name}")
