"""
Enhanced templates for the FDEP standardisation system.

Based on analysis of existing PraisonAI documentation best practices:
- Progressive disclosure (simple first, advanced later)
- Mermaid diagrams for concepts
- CodeGroup/Tabs for multiple examples
- Consistent structure across page types
"""

from pathlib import Path
from typing import Optional

from .models import ArtifactType, FeatureSlug


# Template constants based on existing doc analysis
CONCEPT_TEMPLATE = '''---
title: "{name}"
sidebarTitle: "{name}"
description: "{description}"
icon: "{icon}"
---

## Overview

{name} provides [brief description of what this feature does and why it exists].

```mermaid
flowchart LR
    subgraph Input
        A[User Request]
    end
    
    subgraph {name}
        B[Process] --> C[Validate]
        C --> D[Execute]
    end
    
    subgraph Output
        E[Result]
    end
    
    A --> B
    D --> E
    
    style B fill:#189AB4,color:#fff
    style C fill:#2E8B57,color:#fff
    style D fill:#8B0000,color:#fff
```

## Types of {name}

<CardGroup cols={{2}}>
  <Card title="Type 1" icon="code">
    Description of first type
  </Card>
  <Card title="Type 2" icon="brain">
    Description of second type
  </Card>
</CardGroup>

## Quick Start

```python
from praisonaiagents import Agent, Task

# Basic {slug} usage
agent = Agent(
    instructions="You are a helpful assistant",
    # Configure {slug} here
)

result = agent.start("Your prompt here")
print(result)
```

## When to Use

| Use Case | Recommendation |
|----------|----------------|
| Simple tasks | Use basic configuration |
| Complex workflows | Use advanced patterns |
| Production | Enable all safety features |

## Related Features

- [Related Feature 1](/docs/concepts/related1)
- [Related Feature 2](/docs/concepts/related2)
'''

FEATURE_TEMPLATE = '''---
title: "{name}"
description: "How to use {slug} in PraisonAI"
icon: "code"
---

## Quick Start

<CodeGroup>
```python Basic Usage
from praisonaiagents import Agent, Task

# Simple {slug} example
agent = Agent(
    instructions="You are a helpful assistant",
    # {slug} configuration
)

result = agent.start("Hello!")
print(result)
```

```python Advanced Usage
from praisonaiagents import Agent, Task, Agents

# Advanced {slug} with multiple agents
agent1 = Agent(name="Agent1", instructions="First agent")
agent2 = Agent(name="Agent2", instructions="Second agent")

task = Task(
    description="Complex task using {slug}",
    agent=agent1,
)

agents = AgentManager(agents=[agent1, agent2], tasks=[task])
result = agents.start()
```
</CodeGroup>

## Configuration Options

<Tabs>
  <Tab title="Basic">
    ```python
    # Minimal configuration
    agent = Agent(
        instructions="Your instructions",
        # {slug}=True,  # Enable feature
    )
    ```
  </Tab>
  <Tab title="Advanced">
    ```python
    # Full configuration
    agent = Agent(
        instructions="Your instructions",
        # {slug}={{
        #     "option1": "value1",
        #     "option2": "value2",
        # }},
    )
    ```
  </Tab>
</Tabs>

## API Reference

### Parameters

<ParamField body="param1" type="string" required>
  Description of the first parameter.
</ParamField>

<ParamField body="param2" type="boolean" default="false">
  Description of the second parameter.
</ParamField>

<ParamField body="param3" type="object">
  Advanced configuration object.
</ParamField>

## Examples

### Example 1: Basic Usage

```python
from praisonaiagents import Agent

agent = Agent(instructions="You are helpful")
result = agent.start("Hello")
```

### Example 2: With Callbacks

```python
from praisonaiagents import Agent

def on_complete(result):
    print(f"Completed: {{result}}")

agent = Agent(
    instructions="You are helpful",
    # callbacks=[on_complete],
)
```

## Troubleshooting

<Accordion title="Common Issue 1">
  **Problem**: Description of the issue
  
  **Solution**: How to fix it
</Accordion>

<Accordion title="Common Issue 2">
  **Problem**: Another common issue
  
  **Solution**: The fix for this issue
</Accordion>

## See Also

- [Concept Guide](/docs/concepts/{slug})
- [CLI Reference](/docs/cli/{slug})
- [API Reference](/docs/sdk/praisonaiagents/{slug}/{slug})
'''

CLI_TEMPLATE = '''---
title: "{name}"
sidebarTitle: "{name}"
description: "CLI commands for {slug}"
icon: "terminal"
---

## Quick Start

```bash
praisonai {slug} [OPTIONS]
```

## Commands

### Basic Command

```bash
praisonai {slug}
```

**Expected Output:**
```
[Output example here]
```

### With Options

```bash
praisonai {slug} --option value
```

## Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--help` | flag | - | Show help message |
| `--verbose` | flag | false | Enable verbose output |
| `--config` | string | - | Path to config file |

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PRAISONAI_{slug_upper}` | Configure {slug} | None |

## Examples

### Example 1: Basic

```bash
praisonai {slug}
```

### Example 2: With Config

```bash
praisonai {slug} --config config.yaml
```

### Example 3: Verbose Mode

```bash
praisonai {slug} --verbose
```

## Integration with Python

You can also use {slug} programmatically:

```python
from praisonaiagents import Agent

# Equivalent to CLI command
agent = Agent(instructions="Your instructions")
result = agent.start("Your prompt")
```

## Troubleshooting

<Accordion title="Command not found">
  Ensure PraisonAI is installed: `pip install praisonai`
</Accordion>

<Accordion title="Permission denied">
  Check file permissions and try with `sudo` if needed.
</Accordion>
'''

SDK_TEMPLATE = '''---
title: "{name} Module"
description: "API reference for {slug}"
icon: "code"
---

# {name}

The {name} module provides [brief description].

## Installation

```bash
pip install praisonaiagents
```

## Quick Start

```python
from praisonaiagents import {class_name}

# Basic usage
instance = {class_name}()
result = instance.execute()
```

## Classes

### `{class_name}`

Main class for {slug} functionality.

#### Constructor

```python
{class_name}(
    param1: str,
    param2: bool = False,
    **kwargs
)
```

#### Parameters

<ParamField body="param1" type="string" required>
  Primary configuration parameter.
</ParamField>

<ParamField body="param2" type="boolean" default="false">
  Enable advanced features.
</ParamField>

#### Methods

##### `execute()`

Execute the main functionality.

```python
result = instance.execute(input_data)
```

**Parameters:**
- `input_data` (str): The input to process

**Returns:** `str` - The processed result

##### `configure()`

Update configuration.

```python
instance.configure(option="value")
```

## Type Definitions

```python
from typing import TypedDict, Optional

class {class_name}Config(TypedDict):
    param1: str
    param2: Optional[bool]
```

## Examples

### Basic Example

```python
from praisonaiagents import {class_name}

instance = {class_name}(param1="value")
result = instance.execute()
print(result)
```

### Advanced Example

```python
from praisonaiagents import {class_name}

# With full configuration
instance = {class_name}(
    param1="value",
    param2=True,
)

# Custom processing
result = instance.execute()
```

## See Also

- [Concept Guide](/docs/concepts/{slug})
- [Feature Guide](/docs/features/{slug})
'''

EXAMPLE_BASIC_TEMPLATE = '''"""
{name} - Basic Example

Demonstrates minimal usage of {slug} with a single agent.

Features:
- Simple configuration
- Single agent setup
- Basic execution

Expected Output:
    Agent response demonstrating {slug} functionality.

Usage:
    python {slug}-basic.py
"""

from praisonaiagents import Agent

# ============================================================
# Basic {name} Configuration
# ============================================================

# Create an agent with {slug} enabled
agent = Agent(
    name="{name}Agent",
    role="{name} Specialist",
    goal="Demonstrate basic {slug} functionality",
    backstory="You are an expert in {slug} operations.",
    instructions="Provide clear, helpful responses demonstrating {slug}.",
    # {slug}=True,  # Enable {slug} feature
)

# ============================================================
# Execute
# ============================================================

if __name__ == "__main__":
    # Run the agent
    result = agent.start("Demonstrate {slug} functionality")
    print(result)
'''

EXAMPLE_ADVANCED_TEMPLATE = '''"""
{name} - Advanced Example

Demonstrates advanced {slug} patterns including:
- Multi-agent configuration
- Custom callbacks/handlers
- Error handling
- All available options

Features:
- Multiple agents working together
- Custom configuration
- Production-ready patterns

Expected Output:
    Comprehensive demonstration of {slug} with multiple agents.

Usage:
    python {slug}-advanced.py
"""

from praisonaiagents import Agent, Task, Agents
from typing import Any

# ============================================================
# Section 1: Custom Configuration
# ============================================================

# Define custom {slug} configuration
# config = {{
#     "option1": "value1",
#     "option2": True,
# }}

# ============================================================
# Section 2: Custom Callbacks
# ============================================================

def on_task_complete(task_output: Any) -> None:
    """Callback when a task completes."""
    print(f"Task completed: {{task_output}}")

def on_error(error: Exception) -> None:
    """Callback when an error occurs."""
    print(f"Error occurred: {{error}}")

# ============================================================
# Section 3: Multi-Agent Setup
# ============================================================

# Primary agent
primary_agent = Agent(
    name="Primary{name}Agent",
    role="Primary {name} Handler",
    goal="Handle primary {slug} operations",
    backstory="You are the primary handler for {slug} tasks.",
    instructions="Process {slug} requests thoroughly and accurately.",
    # {slug}=config,
)

# Secondary agent
secondary_agent = Agent(
    name="Secondary{name}Agent",
    role="Secondary {name} Handler",
    goal="Support and verify {slug} operations",
    backstory="You verify and enhance {slug} results.",
    instructions="Review and improve {slug} outputs.",
    # {slug}=config,
)

# ============================================================
# Section 4: Task Definition
# ============================================================

primary_task = Task(
    description="Demonstrate advanced {slug} with primary processing",
    agent=primary_agent,
    expected_output="Detailed {slug} demonstration",
)

verification_task = Task(
    description="Verify and enhance the {slug} results",
    agent=secondary_agent,
    expected_output="Verified and enhanced {slug} output",
)

# ============================================================
# Section 5: Execution
# ============================================================

if __name__ == "__main__":
    # Create agents team
    agents = AgentManager(
        agents=[primary_agent, secondary_agent],
        tasks=[primary_task, verification_task],
        verbose=True,
    )
    
    # Execute
    result = agents.start()
    print("\\n" + "=" * 60)
    print("FINAL RESULT:")
    print("=" * 60)
    print(result)

# ============================================================
# Section 6: All Options Reference
# ============================================================
"""
{name} Options:
──────────────────────────────────────────────────────────────
| Option          | Type     | Default | Description           |
|-----------------|----------|---------|----------------------|
| option1         | str      | None    | Primary option       |
| option2         | bool     | False   | Enable advanced mode |
| option3         | int      | 10      | Iteration count      |
| option4         | list     | []      | Additional handlers  |
──────────────────────────────────────────────────────────────
"""
'''


class EnhancedTemplateGenerator:
    """Enhanced template generator with best-practice templates."""
    
    # Icon mapping for features
    ICON_MAP = {
        "guardrails": "shield-halved",
        "memory": "brain",
        "knowledge": "book",
        "tools": "wrench",
        "agents": "robot",
        "tasks": "list-check",
        "workflows": "diagram-project",
        "handoffs": "arrow-right-arrow-left",
        "sessions": "clock",
        "hooks": "plug",
        "callbacks": "phone",
        "telemetry": "chart-line",
        "default": "code",
    }
    
    def get_icon(self, slug: str) -> str:
        """Get appropriate icon for a feature."""
        return self.ICON_MAP.get(slug, self.ICON_MAP["default"])
    
    def generate(self, slug: FeatureSlug, artifact_type: ArtifactType) -> str:
        """Generate template content for an artifact type."""
        slug_str = slug.normalised
        name = slug_str.replace("-", " ").title()
        class_name = "".join(word.title() for word in slug_str.split("-"))
        icon = self.get_icon(slug_str)
        slug_upper = slug_str.upper().replace("-", "_")
        
        # Select template
        if artifact_type == ArtifactType.DOCS_CONCEPT:
            template = CONCEPT_TEMPLATE
        elif artifact_type == ArtifactType.DOCS_FEATURE:
            template = FEATURE_TEMPLATE
        elif artifact_type == ArtifactType.DOCS_CLI:
            template = CLI_TEMPLATE
        elif artifact_type == ArtifactType.DOCS_SDK:
            template = SDK_TEMPLATE
        elif artifact_type == ArtifactType.EXAMPLE_BASIC:
            template = EXAMPLE_BASIC_TEMPLATE
        elif artifact_type == ArtifactType.EXAMPLE_ADVANCED:
            template = EXAMPLE_ADVANCED_TEMPLATE
        else:
            return ""
        
        # Fill template
        return template.format(
            name=name,
            slug=slug_str,
            class_name=class_name,
            icon=icon,
            slug_upper=slug_upper,
            description=f"{name} functionality for PraisonAI agents",
        )
    
    def get_expected_path(self, slug: FeatureSlug, artifact_type: ArtifactType,
                          docs_root: Optional[Path] = None,
                          examples_root: Optional[Path] = None) -> Optional[Path]:
        """Get the expected path for an artifact."""
        slug_str = slug.normalised
        
        if artifact_type == ArtifactType.EXAMPLE_BASIC:
            if examples_root:
                return examples_root / slug_str / f"{slug_str}-basic.py"
        elif artifact_type == ArtifactType.EXAMPLE_ADVANCED:
            if examples_root:
                return examples_root / slug_str / f"{slug_str}-advanced.py"
        elif artifact_type == ArtifactType.DOCS_CONCEPT:
            if docs_root:
                return docs_root / "concepts" / f"{slug_str}.mdx"
        elif artifact_type == ArtifactType.DOCS_FEATURE:
            if docs_root:
                return docs_root / "features" / f"{slug_str}.mdx"
        elif artifact_type == ArtifactType.DOCS_CLI:
            if docs_root:
                return docs_root / "cli" / f"{slug_str}.mdx"
        elif artifact_type == ArtifactType.DOCS_SDK:
            if docs_root:
                return docs_root / "sdk" / "praisonaiagents" / slug_str / f"{slug_str}.mdx"
        
        return None
