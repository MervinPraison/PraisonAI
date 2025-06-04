# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PraisonAI Agents is a hierarchical AI agent framework for completing complex tasks with self-reflection capabilities. It supports multi-agent collaboration, tool integration, and various execution patterns (sequential, hierarchical, parallel).

## Development Commands

### Installation and Setup
```bash
# Install core package
pip install -e .

# Install with specific features
pip install -e .[all]          # All features
pip install -e .[memory]       # Memory capabilities
pip install -e .[knowledge]    # Document processing
pip install -e .[mcp]          # MCP server support
pip install -e .[llm]          # Extended LLM support
pip install -e .[api]          # API server capabilities
```

### Testing
```bash
# Run individual test examples (no formal test runner configured)
python tests/basic-agents.py
python tests/async_example.py
python tests/knowledge-agents.py

# Test specific features
python tests/mcp-agents.py           # MCP integration
python tests/memory_example.py      # Memory functionality
python tests/tools_example.py       # Tool system
```

### Running Examples
```bash
# Basic agent usage
python tests/single-agent.py

# Multi-agent workflows
python tests/multi-agents-api.py

# Async operations
python tests/async_example_full.py

# MCP server examples
python tests/mcp-sse-direct-server.py  # Start MCP server
python tests/mcp-sse-direct-client.py  # Connect to server
```

## Core Architecture

### Agent System (`praisonaiagents/agent/`)
- **Agent**: Core agent class with LLM integration, tool calling, and self-reflection
- **ImageAgent**: Specialized multimodal agent for image processing
- Self-reflection with configurable min/max iterations (default: 1-3)
- Delegation support for hierarchical agent structures

### Multi-Agent Orchestration (`praisonaiagents/agents/`)
- **PraisonAIAgents**: Main orchestrator for managing multiple agents and tasks
- **AutoAgents**: Automatic agent creation and management
- Process types: `sequential`, `hierarchical`, `parallel`
- Context passing between agents and task dependency management

### Task System (`praisonaiagents/task/`)
- **Task**: Core task definition with context, callbacks, and output specifications
- Supports file output, JSON/Pydantic structured output, async execution
- Conditional logic with `condition` parameter for task flow control
- Context passing via `context` parameter for task dependencies
- **Guardrails**: Built-in validation and safety mechanisms for task outputs
  - Function-based guardrails for custom validation logic
  - LLM-based guardrails using natural language descriptions
  - Automatic retry with configurable `max_retries` parameter
  - Compatible with CrewAI guardrail patterns

### LLM Integration (`praisonaiagents/llm/`)
- Unified wrapper for multiple LLM providers via LiteLLM
- Supports OpenAI, Anthropic, Gemini, DeepSeek, local models (Ollama)
- Context length management and tool calling capabilities
- Set via `llm` parameter on agents or global `OPENAI_API_KEY`/`ANTHROPIC_API_KEY`

### Tool System (`praisonaiagents/tools/`)
Two implementation patterns:
1. **Function-based**: Simple tools using `@tool` decorator
2. **Class-based**: Complex tools inheriting from `BaseTool`

Built-in tools include: DuckDuckGo search, file operations, calculator, Wikipedia, arXiv, data analysis tools, shell execution.

### Memory & Knowledge Systems
- **Memory** (`praisonaiagents/memory/`): Multi-layered memory with RAG support
  - Types: short-term, long-term, entity, user memory
  - Providers: ChromaDB, Mem0, custom implementations
- **Knowledge** (`praisonaiagents/knowledge/`): Document processing with chunking
  - Chunking strategies via `chonkie` library
  - Embedding and retrieval capabilities

### MCP (Model Context Protocol) Integration
- **MCP Server**: Server-side tool protocol for distributed execution
- **SSE Support**: Server-sent events for real-time communication
- Tool discovery and dynamic registration

## Development Patterns

### Agent Creation
```python
agent = Agent(
    name="Agent Name",
    role="Agent Role",
    goal="Agent Goal",
    backstory="Agent Background",
    llm="gpt-4o-mini",  # or other LLM
    self_reflect=True,  # Enable self-reflection
    min_reflect=1,      # Minimum reflection iterations
    max_reflect=3,      # Maximum reflection iterations
    tools=[tool1, tool2]  # Optional tools
)
```

### Task Definition
```python
task = Task(
    name="task_name",
    description="Task description",
    expected_output="Expected output format",
    agent=agent,
    context=[previous_task],  # Task dependencies
    output_pydantic=ResponseModel,  # Structured output
    condition="condition_function"  # Conditional execution
)
```

### Guardrails Usage
```python
from typing import Tuple, Any

# Function-based guardrail
def validate_output(task_output: TaskOutput) -> Tuple[bool, Any]:
    """Custom validation function."""
    if "error" in task_output.raw.lower():
        return False, "Output contains errors"
    if len(task_output.raw) < 10:
        return False, "Output is too short"
    return True, task_output

task = Task(
    description="Write a professional email",
    expected_output="A well-formatted email",
    agent=agent,
    guardrail=validate_output,  # Function-based guardrail
    max_retries=3  # Retry up to 3 times if guardrail fails
)

# LLM-based guardrail
task = Task(
    description="Generate marketing copy",
    expected_output="Professional marketing content",
    agent=agent,
    guardrail="Ensure the content is professional, engaging, and free of errors",  # String description
    max_retries=2
)
```

### Multi-Agent Workflow
```python
workflow = PraisonAIAgents(
    agents=[agent1, agent2],
    tasks=[task1, task2],
    process="sequential",  # or "hierarchical", "parallel"
    verbose=True,
    manager_agent=manager_agent  # For hierarchical process
)
result = workflow.start()
```

### Async Support
All major components support async execution:
```python
result = await workflow.astart()
result = await agent.aexecute(task)
```

## Key Dependencies

- **Core**: `pydantic`, `rich`, `openai`, `mcp`
- **Memory**: `chromadb`, `mem0ai`
- **Knowledge**: `markitdown`, `chonkie`
- **LLM**: `litellm` for unified provider access
- **API**: `fastapi`, `uvicorn` for server capabilities

## Error Handling

- Global error logging via `error_logs` list
- Callback system for real-time error reporting
- Context length exception handling with automatic retry
- Graceful degradation for optional dependencies

## Testing Strategy

The project uses example-driven testing with 100+ test files in `tests/` directory. Each test file demonstrates specific usage patterns and serves as both test and documentation. Run individual examples to test functionality rather than using a formal test runner.

Use conda activate praisonai-agents to activate the environment.