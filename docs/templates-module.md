# Templates Module

## Loading Templates

```python
from praisonai.templates.loader import TemplateLoader

loader = TemplateLoader()

# Load from local path
template = loader.load("./my-template")

# Load from URI
template = loader.load("ai-video-editor")

# Load offline
template = loader.load("ai-video-editor", offline=True)

# Check requirements
missing = loader.check_requirements(template)
```

## Template Discovery

```python
from praisonai.templates.discovery import TemplateDiscovery

discovery = TemplateDiscovery(
    include_package=True,
    include_defaults=True,
)

# Find template
result = discovery.find_template("ai-video-editor")

# List all templates
templates = discovery.list_templates()
```

## Template Config

```python
from praisonai.templates.loader import TemplateConfig

# Access template properties
template.name
template.description
template.version
template.author
template.requires
template.workflow_file
template.agents_file
template.path
```

## Tool Override Integration

```python
from praisonai.templates.tool_override import (
    create_tool_registry_with_overrides,
    resolve_tools,
)

# Build registry with template sources
tools_sources = template.requires.get("tools_sources", [])

registry = create_tool_registry_with_overrides(
    tools_sources=tools_sources,
    template_dir=str(template.path),
    include_defaults=True,
)

# Resolve tool names
tools = resolve_tools(["shell_tool"], registry=registry)
```

## TEMPLATE.yaml Schema

```yaml
name: my-template
version: "1.0.0"
description: Template description

requires:
  tools: [shell_tool]
  packages: [praisonai-tools]
  env: [OPENAI_API_KEY]
  tools_sources:
    - praisonai_tools.video
    - ./local_tools.py

workflow: workflow.yaml
agents: agents.yaml

config:
  input:
    type: string
    required: true
  output:
    type: string

defaults:
  preset: podcast
```
