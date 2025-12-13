# PraisonAI Agents

A powerful Python framework for building AI agents with self-reflection, tool use, and multi-agent orchestration capabilities.

[![PyPI version](https://badge.fury.io/py/praisonaiagents.svg)](https://badge.fury.io/py/praisonaiagents)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

## Installation

```bash
# Basic installation
pip install praisonaiagents

# With all features
pip install "praisonaiagents[all]"

# Specific features
pip install "praisonaiagents[memory]"      # Memory support
pip install "praisonaiagents[knowledge]"   # Knowledge base
pip install "praisonaiagents[mcp]"         # Model Context Protocol
pip install "praisonaiagents[llm]"         # LiteLLM support
pip install "praisonaiagents[mongodb]"     # MongoDB integration
```

## Quick Start

### Basic Agent

```python
from praisonaiagents import Agent

agent = Agent(
    name="Assistant",
    instructions="You are a helpful assistant.",
    model="gpt-4o-mini"
)

response = agent.chat("What is the capital of France?")
print(response)
```

### Agent with Tools

```python
from praisonaiagents import Agent

def get_weather(city: str) -> str:
    """Get weather for a city."""
    return f"Weather in {city}: Sunny, 22°C"

agent = Agent(
    name="Weather Agent",
    instructions="You help users check the weather.",
    tools=[get_weather]
)

response = agent.chat("What's the weather in Paris?")
```

### Multi-Agent Workflow

```python
from praisonaiagents import Agent, Task, PraisonAIAgents

# Define agents
researcher = Agent(name="Researcher", instructions="Research topics thoroughly")
writer = Agent(name="Writer", instructions="Write clear, engaging content")

# Define tasks
research_task = Task(
    description="Research AI trends in 2025",
    agent=researcher,
    expected_output="Research findings"
)

write_task = Task(
    description="Write an article based on research",
    agent=writer,
    expected_output="Article draft"
)

# Run workflow
agents = PraisonAIAgents(agents=[researcher, writer], tasks=[research_task, write_task])
result = agents.start()
```

---

## Agent Types

### 1. Agent (Base)
The core agent class with self-reflection, tool use, and streaming support.

```python
from praisonaiagents import Agent

agent = Agent(
    name="Assistant",
    instructions="You are helpful.",
    model="gpt-4o-mini",
    verbose=True,
    self_reflect=True,  # Enable self-reflection
    max_reflect=3       # Max reflection iterations
)
```

### 2. DeepResearchAgent 🆕
Automated research agent using OpenAI or Gemini Deep Research APIs with real-time streaming.

```python
from praisonaiagents import DeepResearchAgent

# OpenAI Deep Research
agent = DeepResearchAgent(
    model="o4-mini-deep-research",  # or "o3-deep-research"
    verbose=True
)

result = agent.research("What are the latest AI trends?")
print(result.report)
print(f"Citations: {len(result.citations)}")

# Gemini Deep Research
agent = DeepResearchAgent(
    model="deep-research-pro",  # Auto-detected as Gemini
    verbose=True
)

result = agent.research("Research quantum computing advances")
```

**Features:**
- **Multi-provider**: OpenAI, Gemini, and LiteLLM support
- **Auto-detection**: Provider detected from model name
- **Streaming**: Real-time progress with reasoning summaries (default: enabled)
- **Citations**: Structured citations with URLs
- **Tools**: Web search, code interpreter, MCP, file search

### 3. ImageAgent
Agent specialized for image generation and analysis.

```python
from praisonaiagents import ImageAgent

agent = ImageAgent(
    name="Artist",
    instructions="Generate creative images"
)

result = agent.chat("Create an image of a sunset over mountains")
```

### 4. ContextAgent
Agent with persistent context across conversations.

```python
from praisonaiagents import ContextAgent

agent = ContextAgent(
    name="Context Agent",
    instructions="Remember our conversation"
)
```

### 5. RouterAgent
Routes requests to appropriate specialized agents.

```python
from praisonaiagents.agent import RouterAgent

router = RouterAgent(
    agents=[weather_agent, math_agent, general_agent],
    instructions="Route to the best agent for each query"
)
```

---

## Memory

Persistent memory with short-term, long-term, and graph memory support.

```python
from praisonaiagents import Agent, Memory

memory = Memory(
    provider="chroma",  # or "mongodb", "rag"
    use_short_term=True,
    use_long_term=True
)

agent = Agent(
    name="Memory Agent",
    memory=memory
)
```

**Memory Types:**
- **Short-term**: Recent conversation context
- **Long-term**: Persistent storage across sessions
- **Graph**: Relationship-based memory with Mem0

---

## Knowledge Base

Add documents and data sources to your agents.

```python
from praisonaiagents import Agent, Knowledge

knowledge = Knowledge(
    sources=["docs/", "data.pdf", "https://example.com"],
    chunking_method="semantic"
)

agent = Agent(
    name="Knowledge Agent",
    knowledge=knowledge
)
```

**Supported Sources:**
- PDF, Word, Excel, CSV files
- Directories of documents
- URLs and web pages
- Databases

---

## Tools

### Built-in Tools

```python
from praisonaiagents.tools import (
    # Search
    duckduckgo_search,
    searxng_search,
    
    # Data
    read_csv, write_csv,
    read_json, write_json,
    read_yaml, write_yaml,
    read_excel, write_excel,
    
    # Finance
    get_stock_price, get_stock_info,
    
    # Research
    arxiv_search,
    wikipedia_search,
    
    # Web
    spider_scrape,
    newspaper_extract,
    
    # System
    execute_shell,
    run_python,
    
    # Database
    duckdb_query,
    mongodb_query
)
```

### Custom Tools

```python
def my_tool(param: str) -> str:
    """Tool description for the agent."""
    return f"Result: {param}"

agent = Agent(tools=[my_tool])
```

---

## MCP (Model Context Protocol)

Connect to MCP servers for extended capabilities.

```python
from praisonaiagents import Agent, MCP

# Local MCP server
agent = Agent(
    tools=MCP(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "/path"]
    )
)

# Remote MCP server (SSE)
agent = Agent(
    tools=MCP(url="http://localhost:8080/sse")
)

# With environment variables
agent = Agent(
    tools=MCP(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-brave-search"],
        env={"BRAVE_API_KEY": "your-key"}
    )
)
```

---

## Guardrails

Add safety checks and validation to agent responses.

```python
from praisonaiagents import Agent, LLMGuardrail

# LLM-based guardrail
guardrail = LLMGuardrail(
    instructions="Ensure responses are professional and accurate"
)

agent = Agent(
    name="Safe Agent",
    guardrail=guardrail
)
```

---

## Handoffs

Transfer conversations between agents.

```python
from praisonaiagents import Agent, handoff

support_agent = Agent(name="Support", instructions="Handle support queries")
sales_agent = Agent(name="Sales", instructions="Handle sales queries")

# Enable handoffs
support_agent.handoffs = [handoff(sales_agent, "Transfer to sales")]
```

---

## Streaming

Real-time streaming responses.

```python
from praisonaiagents import Agent

agent = Agent(name="Streamer", verbose=True)

# Streaming is automatic with verbose=True
response = agent.chat("Tell me a story")

# Or use the stream method
for chunk in agent.stream("Tell me a story"):
    print(chunk, end="", flush=True)
```

---

## Async Support

Full async/await support for all operations.

```python
import asyncio
from praisonaiagents import Agent

agent = Agent(name="Async Agent")

async def main():
    response = await agent.achat("Hello!")
    print(response)

asyncio.run(main())
```

---

## Telemetry

Built-in telemetry for monitoring and analytics.

```python
from praisonaiagents import enable_telemetry, disable_telemetry

# Enable full telemetry
enable_telemetry()

# Disable telemetry
disable_telemetry()
```

**Environment Variables:**
- `PRAISONAI_DISABLE_TELEMETRY=true` - Disable all telemetry
- `PRAISONAI_PERFORMANCE_MODE=true` - Minimal overhead mode
- `DO_NOT_TRACK=true` - Respect DNT preference

---

## Supported LLM Providers

PraisonAI Agents works with any LLM provider via LiteLLM:

| Provider | Model Example |
|----------|---------------|
| OpenAI | `gpt-4o`, `gpt-4o-mini`, `o1`, `o3` |
| Anthropic | `claude-3-5-sonnet`, `claude-3-opus` |
| Google | `gemini-2.0-flash`, `gemini-pro` |
| Ollama | `ollama/llama3`, `ollama/mistral` |
| Azure | `azure/gpt-4` |
| AWS Bedrock | `bedrock/claude-3` |
| Groq | `groq/llama3-70b` |
| Together | `together/mixtral-8x7b` |

```python
# Use any provider
agent = Agent(model="anthropic/claude-3-5-sonnet")
agent = Agent(model="ollama/llama3")
agent = Agent(model="gemini/gemini-2.0-flash")
```

---

## Configuration

### Environment Variables

```bash
# API Keys
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=...
GOOGLE_API_KEY=...

# Logging
LOGLEVEL=DEBUG  # DEBUG, INFO, WARNING, ERROR

# Telemetry
PRAISONAI_DISABLE_TELEMETRY=true
```

---

## Examples

### Research Agent with Citations

```python
from praisonaiagents import DeepResearchAgent

agent = DeepResearchAgent(
    model="o4-mini-deep-research",
    instructions="Provide data-rich insights with citations",
    verbose=True
)

result = agent.research("Economic impact of AI on healthcare")

print(result.report)
for citation in result.citations:
    print(f"- {citation.title}: {citation.url}")
```

### Multi-Agent Research Team

```python
from praisonaiagents import Agent, Task, PraisonAIAgents

researcher = Agent(
    name="Researcher",
    instructions="Research topics thoroughly",
    tools=[duckduckgo_search]
)

analyst = Agent(
    name="Analyst", 
    instructions="Analyze data and provide insights"
)

writer = Agent(
    name="Writer",
    instructions="Write clear reports"
)

tasks = [
    Task(description="Research AI trends", agent=researcher),
    Task(description="Analyze findings", agent=analyst),
    Task(description="Write report", agent=writer)
]

team = PraisonAIAgents(agents=[researcher, analyst, writer], tasks=tasks)
result = team.start()
```

### Agent with Memory and Knowledge

```python
from praisonaiagents import Agent, Memory, Knowledge

agent = Agent(
    name="Smart Assistant",
    memory=Memory(use_long_term=True),
    knowledge=Knowledge(sources=["docs/"]),
    instructions="Help users with their questions using available knowledge"
)
```

---

## API Reference

### Agent

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | str | "Agent" | Agent name |
| `instructions` | str | "" | System instructions |
| `model` | str | "gpt-4o-mini" | LLM model |
| `tools` | list | [] | Available tools |
| `memory` | Memory | None | Memory instance |
| `knowledge` | Knowledge | None | Knowledge base |
| `verbose` | bool | False | Enable verbose output |
| `self_reflect` | bool | False | Enable self-reflection |
| `max_reflect` | int | 3 | Max reflection iterations |

### DeepResearchAgent

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | str | "o3-deep-research" | Research model |
| `provider` | str | None | Force provider (openai/gemini/litellm) |
| `verbose` | bool | True | Show progress |
| `poll_interval` | int | 5 | Gemini poll interval (seconds) |
| `max_wait_time` | int | 3600 | Max research time (seconds) |

### Task

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `description` | str | required | Task description |
| `agent` | Agent | required | Assigned agent |
| `expected_output` | str | "" | Expected output format |
| `context` | list | [] | Context from other tasks |

---

## License

MIT License - see LICENSE file for details.

## Links

- [Documentation](https://docs.praison.ai)
- [GitHub](https://github.com/MervinPraison/PraisonAI)
- [PyPI](https://pypi.org/project/praisonaiagents/)