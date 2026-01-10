# Consolidated Params Examples

Examples demonstrating the **Agent-Centric API** with consolidated parameters.

## Precedence Ladder

```
Instance > Config > Array > Dict > String > Bool > Default
```

## Quick Reference

| Feature | Presets | Example |
|---------|---------|---------|
| `memory` | file, sqlite, redis, postgres, mem0, mongodb | `memory="sqlite"` |
| `output` | minimal, normal, verbose, debug, silent | `output="verbose"` |
| `execution` | fast, balanced, thorough, unlimited | `execution="balanced"` |
| `planning` | reasoning, read_only, auto | `planning="reasoning"` |
| `reflection` | minimal, standard, thorough | `reflection="standard"` |
| `guardrails` | strict, permissive, safety | `guardrails="strict"` |
| `web` | duckduckgo, tavily, google, bing, serper | `web="duckduckgo"` |
| `context` | sliding_window, summarize, truncate | `context="sliding_window"` |
| `autonomy` | suggest, auto_edit, full_auto | `autonomy="suggest"` |
| `caching` | enabled, disabled, prompt | `caching="prompt"` |

## Examples

### Basic Examples (Single Feature)

| File | Feature | Description |
|------|---------|-------------|
| `basic_agent.py` | Agent | Minimal agent with memory |
| `basic_memory.py` | memory | SQLite memory preset |
| `basic_output.py` | output | Verbose output preset |
| `basic_execution.py` | execution | Execution control |
| `basic_guardrails.py` | guardrails | Callable validator |
| `basic_reflection.py` | reflection | Self-reflection preset |
| `basic_web.py` | web | Web search preset |
| `basic_planning.py` | planning | Planning preset |
| `basic_autonomy.py` | autonomy | Autonomy preset |
| `basic_caching.py` | caching | Caching preset |
| `basic_knowledge.py` | knowledge | RAG with sources |
| `basic_context.py` | context | Context management |
| `basic_hooks.py` | hooks | Lifecycle callbacks |

### Multi-Agent Examples

| File | Description |
|------|-------------|
| `basic_agents.py` | Multi-agent with memory and planning |

### Workflow Examples

| File | Description |
|------|-------------|
| `basic_workflow.py` | Simple workflow with output preset |
| `basic_workflow_agentlike.py` | Workflow with agent-like params |
| `basic_step_override.py` | Step-level param overrides |
| `advanced_workflow_full_features.py` | All consolidated params |

### Advanced Examples

| File | Description |
|------|-------------|
| `advanced_output_execution.py` | Combined output + execution |

## Usage Forms

Each consolidated param supports multiple input forms:

```python
# Bool - enable with defaults
memory=True

# String preset
memory="sqlite"

# Dict config
memory={"backend": "sqlite", "user_id": "user123"}

# Config instance
memory=MemoryConfig(backend="sqlite", user_id="user123")

# Array with overrides (for some params)
guardrails=["strict", {"max_retries": 10}]
```

## Running Examples

```bash
# Set API key
export OPENAI_API_KEY=your_key_here

# Run any example
python basic_agent.py
```
