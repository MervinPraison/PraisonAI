# PraisonAI Example Plugin

This is a template for creating tool plugins for PraisonAI Agents.

## Installation

```bash
# Install in development mode
pip install -e .

# Or install from PyPI (after publishing)
pip install praisonai-example-plugin
```

## Usage

After installation, tools are automatically discovered:

```python
from praisonaiagents import Agent

# Use tools by name - they're auto-discovered!
agent = Agent(
    name="Assistant",
    tools=["example_greet", "example_math", "example_reverse"]
)

# Or import and use directly
from praisonai_example_plugin import GreetTool, MathTool, reverse_text

agent = Agent(
    name="Assistant", 
    tools=[GreetTool(), MathTool(), reverse_text]
)
```

## Creating Your Own Plugin

1. **Copy this template**
2. **Rename the package** in `pyproject.toml` and `src/` directory
3. **Add your tools** following the patterns in `__init__.py`
4. **Update entry_points** in `pyproject.toml` to register your tools

### Tool Patterns

**Class-based tool:**
```python
from praisonaiagents import BaseTool

class MyTool(BaseTool):
    name = "my_tool"
    description = "What this tool does"
    
    def run(self, param: str) -> str:
        return f"Result: {param}"
```

**Decorator-based tool:**
```python
from praisonaiagents import tool

@tool
def my_function(param: str) -> str:
    """What this function does."""
    return f"Result: {param}"
```

### Registering Tools

In `pyproject.toml`:
```toml
[project.entry-points."praisonaiagents.tools"]
my_tool = "my_package:MyTool"
my_function = "my_package:my_function"
```

## Testing

```bash
pip install -e ".[dev]"
pytest
```

## Publishing

```bash
pip install build twine
python -m build
twine upload dist/*
```

## License

MIT
