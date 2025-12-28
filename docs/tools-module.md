# Tools Module

## Tool Registry

```python
from praisonai.templates.tool_override import (
    create_tool_registry_with_overrides,
    resolve_tools,
)

# Create registry with defaults
registry = create_tool_registry_with_overrides(include_defaults=True)

# Create registry with overrides
registry = create_tool_registry_with_overrides(
    override_files=["my_tools.py"],
    override_dirs=["./tools"],
    include_defaults=True,
)

# Create registry with tools_sources
registry = create_tool_registry_with_overrides(
    tools_sources=["praisonai_tools.video"],
    template_dir="./my-template",
    include_defaults=True,
)

# Resolve tool names to callables
tools = resolve_tools(
    ["shell_tool", "internet_search"],
    registry=registry,
)
```

## Tool Override Loader

```python
from praisonai.templates.tool_override import ToolOverrideLoader

loader = ToolOverrideLoader()

# Load from file
tools = loader.load_from_file("my_tools.py")

# Load from directory
tools = loader.load_from_directory("./tools")

# Load from module
tools = loader.load_from_module("praisonai_tools.video")

# Get default tool directories
dirs = loader.get_default_tool_dirs()
```

## Resolution Order

1. CLI `--tools` files (highest priority)
2. CLI `--tools-dir` directories
3. Template `tools_sources` (from TEMPLATE.yaml)
4. Template-local `tools.py`
5. Default dirs (`~/.praison/tools`, `~/.config/praison/tools`)
6. Package discovery (`praisonai_tools`)
7. Built-in tools (lowest priority)

## Creating Custom Tools

```python
from praisonai_tools import tool

@tool
def my_custom_tool(query: str) -> str:
    """My custom tool description.
    
    Args:
        query: The search query
    """
    return f"Result for: {query}"
```

## Template tools_sources

```yaml
# TEMPLATE.yaml
requires:
  tools: [shell_tool]
  tools_sources:
    - praisonai_tools.video
    - ./local_tools.py
    - ./tools_dir/
```
