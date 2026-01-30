"""
Template generators for the FDEP standardisation system.

Generates:
- Example files (basic and advanced)
- Docs pages (concept, feature, cli, sdk)
"""

from pathlib import Path
from typing import Optional

from .models import ArtifactType, FeatureSlug


class TemplateGenerator:
    """Generates template files for features."""
    
    def generate(self, slug: FeatureSlug, artifact_type: ArtifactType,
                 output_path: Optional[Path] = None) -> str:
        """Generate template content for an artifact type."""
        if artifact_type == ArtifactType.EXAMPLE_BASIC:
            return self._generate_basic_example(slug)
        elif artifact_type == ArtifactType.EXAMPLE_ADVANCED:
            return self._generate_advanced_example(slug)
        elif artifact_type == ArtifactType.DOCS_CONCEPT:
            return self._generate_concept_doc(slug)
        elif artifact_type == ArtifactType.DOCS_FEATURE:
            return self._generate_feature_doc(slug)
        elif artifact_type == ArtifactType.DOCS_CLI:
            return self._generate_cli_doc(slug)
        elif artifact_type == ArtifactType.DOCS_SDK:
            return self._generate_sdk_doc(slug)
        else:
            raise ValueError(f"Unknown artifact type: {artifact_type}")
    
    def _generate_basic_example(self, slug: FeatureSlug) -> str:
        """Generate a basic example template."""
        name = slug.normalised.replace("-", " ").title()
        slug_str = slug.normalised
        
        return f'''"""
{name} - Basic Example

Demonstrates minimal usage of {slug_str} with a single agent.

Expected Output:
    Agent response demonstrating {slug_str} functionality.
"""
from praisonaiagents import Agent

# Basic {slug_str} usage
agent = Agent(
    instructions="You are a helpful assistant",
    # {slug_str}=...  # Configure {slug_str} here
)

# Run the agent
result = agent.start("Hello! Demonstrate {slug_str} functionality.")
print(result)
'''
    
    def _generate_advanced_example(self, slug: FeatureSlug) -> str:
        """Generate an advanced example template."""
        name = slug.normalised.replace("-", " ").title()
        slug_str = slug.normalised
        
        return f'''"""
{name} - Advanced Example

Demonstrates advanced {slug_str} patterns including:
- Multi-agent configuration
- Custom callbacks/handlers
- Error handling
- All available options

Expected Output:
    Comprehensive demonstration of {slug_str} with multiple agents.
"""
from praisonaiagents import Agent, Task, PraisonAIAgents

# ============================================================
# Section 1: Custom Configuration
# ============================================================

# Define custom {slug_str} configuration
# config = ...

# ============================================================
# Section 2: Multi-Agent Setup
# ============================================================

agent1 = Agent(
    name="Agent1",
    instructions="You are the first agent",
    # {slug_str}=config,
)

agent2 = Agent(
    name="Agent2",
    instructions="You are the second agent",
    # {slug_str}=config,
)

# ============================================================
# Section 3: Task Definition
# ============================================================

task = Task(
    description="Demonstrate {slug_str} with multiple agents",
    agent=agent1,
)

# ============================================================
# Section 4: Execution
# ============================================================

agents = PraisonAIAgentManager(agents=[agent1, agent2], tasks=[task])
result = agents.start()
print(result)

# ============================================================
# Section 5: All Options Reference
# ============================================================
"""
{name} Options:
──────────────────
| Option          | Type     | Default | Description           |
|-----------------|----------|---------|----------------------|
| option1         | str      | None    | Description here     |
| option2         | bool     | False   | Description here     |
"""
'''
    
    def _generate_concept_doc(self, slug: FeatureSlug) -> str:
        """Generate a concept documentation template."""
        name = slug.normalised.replace("-", " ").title()
        slug_str = slug.normalised
        
        return f'''---
title: "{name}"
description: "Understanding {slug_str} in PraisonAI"
icon: "lightbulb"
---

## Overview

{name} provides [brief description of what this feature does and why it exists].

```mermaid
graph LR
    A[Input] --> B[{name}]
    B --> C[Output]
```

## When to Use

<CardGroup cols={{2}}>
  <Card title="Use When" icon="check">
    - Use case 1
    - Use case 2
  </Card>
  <Card title="Don't Use When" icon="xmark">
    - Anti-pattern 1
    - Anti-pattern 2
  </Card>
</CardGroup>

## How It Works

[Brief explanation of the mechanism, 3-5 sentences max.]

## Related Features

- [Related Feature 1](/docs/concepts/related1)
- [Related Feature 2](/docs/concepts/related2)
'''
    
    def _generate_feature_doc(self, slug: FeatureSlug) -> str:
        """Generate a feature documentation template."""
        name = slug.normalised.replace("-", " ").title()
        slug_str = slug.normalised
        
        return f'''---
title: "{name}"
description: "How to use {slug_str} in PraisonAI"
icon: "code"
---

## Quick Start

```python
from praisonaiagents import Agent

agent = Agent(
    instructions="You are a helpful assistant",
    # {slug_str}=...
)
result = agent.start("Hello!")
```

## Basic Usage

<Steps>
  <Step title="Step 1: Configure">
    Configure {slug_str} for your agent.
    ```python
    # Configuration code
    ```
  </Step>
  <Step title="Step 2: Run">
    Run the agent with {slug_str} enabled.
  </Step>
</Steps>

## Advanced Patterns

<Tabs>
  <Tab title="Pattern 1">
    ```python
    # Pattern 1 code
    ```
  </Tab>
  <Tab title="Pattern 2">
    ```python
    # Pattern 2 code
    ```
  </Tab>
</Tabs>

## All Options

<ParamField body="option1" type="string" required>
  Description of option1.
</ParamField>

<ParamField body="option2" type="boolean" default="false">
  Description of option2.
</ParamField>

## See Also

- [CLI Reference](/docs/cli/{slug_str})
- [API Reference](/docs/sdk/praisonaiagents/{slug_str}/{slug_str})
'''
    
    def _generate_cli_doc(self, slug: FeatureSlug) -> str:
        """Generate a CLI documentation template."""
        name = slug.normalised.replace("-", " ").title()
        slug_str = slug.normalised
        
        return f'''---
title: "{name}"
description: "CLI commands for {slug_str}"
icon: "terminal"
---

## Quick Start

```bash
praisonai "Your prompt" --{slug_str}
```

## Commands

### `--{slug_str}`

Enable {slug_str} functionality.

```bash
praisonai "Your prompt" --{slug_str}
```

**Expected Output:**
```
[Example output here]
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PRAISONAI_{slug_str.upper().replace("-", "_")}` | Configure {slug_str} | None |

## Examples

### Basic

```bash
praisonai "Hello" --{slug_str}
```

### With Other Flags

```bash
praisonai "Hello" --{slug_str} --verbose
```

## Troubleshooting

<Accordion title="Common Issue 1">
  Solution for common issue 1.
</Accordion>
'''
    
    def _generate_sdk_doc(self, slug: FeatureSlug) -> str:
        """Generate an SDK documentation template."""
        name = slug.normalised.replace("-", " ").title()
        slug_str = slug.normalised
        class_name = "".join(word.title() for word in slug_str.split("-"))
        
        return f'''---
title: "{name} Module"
description: "API reference for {slug_str}"
icon: "code"
---

# {name}

{name} module provides [brief description].

## Quick Start

```python
from praisonaiagents import {class_name}

# Basic usage
instance = {class_name}()
```

## Classes

### `{class_name}`

Main class for {slug_str} functionality.

#### Constructor

```python
{class_name}(
    param1: str,
    param2: bool = False
)
```

#### Parameters

<ParamField body="param1" type="string" required>
  Description of param1.
</ParamField>

<ParamField body="param2" type="boolean" default="false">
  Description of param2.
</ParamField>

#### Methods

##### `method_name()`

Description of the method.

```python
result = instance.method_name(args)
```

**Returns:** `ReturnType` - Description of return value.

## Type Definitions

```python
# Type aliases used in this module
```
'''
    
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
