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

### Planning Mode 🆕

Plan before execution, like Cursor, Windsurf, and Claude Code:

```python
from praisonaiagents import Agent, Task, PraisonAIAgents

researcher = Agent(name="Researcher", role="Research Analyst")
writer = Agent(name="Writer", role="Content Writer")

research_task = Task(description="Research AI benefits", agent=researcher)
write_task = Task(description="Write summary", agent=writer)

# Enable planning mode
agents = PraisonAIAgents(
    agents=[researcher, writer],
    tasks=[research_task, write_task],
    planning=True,              # Enable planning
    planning_llm="gpt-4o-mini", # Fast LLM for planning
    auto_approve_plan=True      # Auto-approve plans
)

result = agents.start()
```

**Features:**
- **Plan Creation**: LLM creates step-by-step implementation plans
- **Todo Lists**: Auto-generated from plans with progress tracking
- **Read-Only Mode**: `plan_mode=True` restricts agents to safe tools
- **Approval Flow**: Review and approve plans before execution
- **Persistence**: Plans saved to `.praison/plans/` as markdown

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

### 3. QueryRewriterAgent 🆕
Transform user queries to improve RAG retrieval quality using multiple strategies.

```python
from praisonaiagents import QueryRewriterAgent, RewriteStrategy

agent = QueryRewriterAgent(model="gpt-4o-mini", verbose=True)

# Basic rewriting - expands abbreviations, adds context
result = agent.rewrite("AI trends")
print(result.primary_query)
# Output: "What are the current trends in Artificial Intelligence (AI)?"

# HyDE - generates hypothetical document for semantic matching
result = agent.rewrite("What is quantum computing?", strategy=RewriteStrategy.HYDE)
print(result.hypothetical_document)

# Step-back - generates broader context question
result = agent.rewrite("Difference between GPT-4 and Claude 3?", strategy=RewriteStrategy.STEP_BACK)
print(result.step_back_question)

# Sub-queries - decomposes complex questions
result = agent.rewrite("How to set up RAG and what embedding models to use?", strategy=RewriteStrategy.SUB_QUERIES)
print(result.sub_queries)

# Contextual - uses chat history to resolve references
result = agent.rewrite("What about its cost?", strategy=RewriteStrategy.CONTEXTUAL, chat_history=[...])
```

**Strategies:**
- **BASIC**: Expand abbreviations, fix typos, add context
- **HYDE**: Generate hypothetical document for better semantic matching
- **STEP_BACK**: Generate higher-level concept questions
- **SUB_QUERIES**: Decompose multi-part questions
- **MULTI_QUERY**: Generate multiple paraphrased versions
- **CONTEXTUAL**: Resolve references using conversation history
- **AUTO**: Automatically detect best strategy

### 4. ImageAgent
Agent specialized for image generation and analysis.

```python
from praisonaiagents import ImageAgent

agent = ImageAgent(
    name="Artist",
    instructions="Generate creative images"
)

result = agent.chat("Create an image of a sunset over mountains")
```

### 5. ContextAgent
Agent with persistent context across conversations.

```python
from praisonaiagents import ContextAgent

agent = ContextAgent(
    name="Context Agent",
    instructions="Remember our conversation"
)
```

### 6. RouterAgent
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

PraisonAI provides a comprehensive memory system with features inspired by Claude, Gemini CLI, Codex CLI, Cursor, and Windsurf.

### Quick Start (Zero Dependencies)

```python
from praisonaiagents import Agent
from praisonaiagents.memory import FileMemory

# Simple file-based memory (no extra dependencies)
memory = FileMemory(user_id="user123")

agent = Agent(
    name="Memory Agent",
    instructions="You are a helpful assistant with memory.",
    memory=memory  # or memory=True for auto FileMemory
)

response = agent.chat("My name is John and I prefer Python")
# Memory automatically stores this context
```

### Advanced Memory (with providers)

```python
from praisonaiagents.memory import Memory

memory = Memory(
    provider="chroma",  # or "mongodb", "mem0", "rag"
    use_short_term=True,
    use_long_term=True
)

agent = Agent(name="Memory Agent", memory=memory)
```

### Memory Types

| Type | Description | Storage |
|------|-------------|---------|
| **Short-term** | Rolling buffer of recent context | JSON/SQLite |
| **Long-term** | Persistent facts and knowledge | JSON/SQLite/Vector DB |
| **Entity** | Named entities (people, places, concepts) | JSON/SQLite |
| **Episodic** | Date-based interaction memories | JSON files |
| **Graph** | Relationship-based memory | Mem0/Neo4j |

### Session Save/Resume (like Gemini CLI)

```python
from praisonaiagents.memory import FileMemory

memory = FileMemory(user_id="user123")

# Add context during conversation
memory.add_short_term("User is working on ML project")
memory.add_long_term("User prefers Python", importance=0.9)

# Save session for later
memory.save_session("ml_project", conversation_history=[...])

# Resume later
session_data = memory.resume_session("ml_project")

# List all sessions
sessions = memory.list_sessions()
```

### Context Compression (like Gemini CLI)

```python
# Auto-compress when memory gets full
memory.auto_compress_if_needed(threshold_percent=0.7)

# Manual compression with LLM summarization
def llm_summarize(prompt):
    return agent.chat(prompt)

summary = memory.compress(llm_func=llm_summarize, max_items=10)
```

### Checkpointing (like Gemini CLI)

```python
# Create checkpoint before risky operations
checkpoint_id = memory.create_checkpoint("before_refactor", include_files=["main.py"])

# Restore if needed
memory.restore_checkpoint(checkpoint_id, restore_files=True)

# List checkpoints
checkpoints = memory.list_checkpoints()
```

### Memory Slash Commands

```python
# Handle slash commands programmatically
result = memory.handle_command("/memory show")
result = memory.handle_command("/memory add User likes coffee")
result = memory.handle_command("/memory search Python")
result = memory.handle_command("/memory save my_session")
result = memory.handle_command("/memory compress")
result = memory.handle_command("/memory checkpoint")
result = memory.handle_command("/memory help")
```

**Available Commands:**
- `/memory show` - Display stats and recent items
- `/memory add <content>` - Add to long-term memory
- `/memory clear [short|all]` - Clear memory
- `/memory search <query>` - Search memories
- `/memory save <name>` - Save session
- `/memory resume <name>` - Resume session
- `/memory sessions` - List saved sessions
- `/memory compress` - Compress short-term memory
- `/memory checkpoint [name]` - Create checkpoint
- `/memory restore <id>` - Restore checkpoint
- `/memory checkpoints` - List checkpoints
- `/memory refresh` - Reload from disk

---

## Rules & Instructions (like Cursor/Windsurf)

PraisonAI automatically discovers and applies rules from multiple sources, similar to Cursor, Windsurf, Claude Code, and Codex CLI.

### Supported Instruction Files

| File | Description | Priority |
|------|-------------|----------|
| `PRAISON.md` | PraisonAI native instructions | High (500) |
| `PRAISON.local.md` | Local overrides (gitignored) | Higher (600) |
| `CLAUDE.md` | Claude Code memory file | High (500) |
| `CLAUDE.local.md` | Local overrides (gitignored) | Higher (600) |
| `AGENTS.md` | OpenAI Codex CLI instructions | High (500) |
| `GEMINI.md` | Gemini CLI memory file | High (500) |
| `.cursorrules` | Cursor IDE rules (legacy) | High (500) |
| `.windsurfrules` | Windsurf IDE rules (legacy) | High (500) |
| `.claude/rules/*.md` | Claude Code modular rules | Medium (50) |
| `.windsurf/rules/*.md` | Windsurf modular rules | Medium (50) |
| `.cursor/rules/*.mdc` | Cursor modular rules | Medium (50) |
| `.praison/rules/*.md` | Workspace rules | Medium (0) |
| `~/.praison/rules/*.md` | Global rules | Low (-1000) |

### Auto-Discovery

Rules are automatically loaded when you create an Agent:

```python
from praisonaiagents import Agent

# Agent auto-discovers CLAUDE.md, AGENTS.md, GEMINI.md, etc.
agent = Agent(
    name="Assistant",
    instructions="You are helpful."
)

# Rules are injected into system prompt automatically
```

### Rule File Format

Rules support YAML frontmatter for advanced configuration:

```markdown
---
description: Python coding guidelines
globs: ["**/*.py", "**/*.pyx"]
activation: always  # always, glob, manual, ai_decision
priority: 10
---

# Python Guidelines
- Use type hints for all functions
- Follow PEP 8 style guide
- Write docstrings for public APIs
```

### Activation Modes

| Mode | Description |
|------|-------------|
| `always` | Always applied (default) |
| `glob` | Applied when file matches glob pattern |
| `manual` | Only when explicitly invoked via @mention |
| `ai_decision` | AI decides when to apply |

### Programmatic Rules Management

```python
from praisonaiagents.memory import RulesManager

rules = RulesManager(workspace_path="/path/to/project")

# Get all active rules
active = rules.get_active_rules()

# Get rules for specific file
python_rules = rules.get_rules_for_file("src/main.py")

# Build context for LLM
context = rules.build_rules_context(file_path="src/main.py")

# Create new rule
rules.create_rule(
    name="testing",
    content="Always write tests first",
    globs=["**/*.test.*"],
    activation="glob"
)

# Get stats
stats = rules.get_stats()
# {'total_rules': 5, 'root_rules': 3, 'workspace_rules': 2, ...}
```

### Storage Structure

```
project/
├── CLAUDE.md              # Auto-loaded (Claude Code)
├── CLAUDE.local.md        # Local overrides (gitignored)
├── AGENTS.md              # Auto-loaded (Codex CLI)
├── GEMINI.md              # Auto-loaded (Gemini CLI)
├── PRAISON.md             # Auto-loaded (PraisonAI)
├── PRAISON.local.md       # Local overrides (gitignored)
├── .claude/rules/         # Claude Code modular rules
├── .windsurf/rules/       # Windsurf rules
├── .cursor/rules/         # Cursor rules
├── .praison/
│   ├── rules/             # Workspace rules
│   │   ├── python.md
│   │   └── testing.md
│   ├── workflows/         # Reusable workflows
│   │   └── deploy.md
│   ├── hooks.json         # Pre/post operation hooks
│   └── memory/
│       └── {user_id}/
│           ├── short_term.json
│           ├── long_term.json
│           ├── sessions/
│           └── checkpoints/
└── ~/.praison/
    └── rules/             # Global rules
        └── global.md
```

### @Import Syntax (like Claude Code)

Include other files in your rules:

```markdown
# CLAUDE.md
See @README for project overview
See @docs/architecture.md for system design
@~/.praison/my-preferences.md
```

### Auto-Generated Memories (like Windsurf Cascade)

```python
from praisonaiagents.memory import FileMemory, AutoMemory

memory = FileMemory(user_id="user123")
auto = AutoMemory(memory, enabled=True)

# Automatically extracts and stores memories from conversations
memories = auto.process_interaction(
    "My name is John and I prefer Python for backend work"
)
# Extracts: name="John", preference="Python for backend"
```

### Workflows (like Windsurf)

Create reusable multi-step workflows:

```python
from praisonaiagents.memory import WorkflowManager

manager = WorkflowManager()

# Execute a workflow
result = manager.execute(
    "deploy",
    executor=lambda prompt: agent.chat(prompt),
    variables={"environment": "production"}
)
```

### Hooks (like Windsurf Cascade Hooks)

```python
from praisonaiagents.memory import HooksManager

hooks = HooksManager()

# Register Python hooks
hooks.register("pre_write_code", lambda ctx: print(f"Writing {ctx['file']}"))

# Or configure in .praison/hooks.json
```

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

## Native Web Search

Enable real-time web search capabilities using LiteLLM's native web search.

```python
from praisonaiagents import Agent

# Enable web search with a supported model
agent = Agent(
    name="Researcher",
    instructions="You are a helpful research assistant.",
    llm="openai/gpt-4o-search-preview",
    web_search=True
)

result = agent.start("What are the latest developments in AI today?")
```

**Supported Providers:**
- **OpenAI**: `gpt-4o-search-preview`, `gpt-4o-mini-search-preview`
- **Anthropic**: `claude-3-5-sonnet-latest`, `claude-sonnet-4`
- **Google/Gemini**: `gemini-2.0-flash`, `gemini-2.5-pro`
- **xAI**: `grok-3`
- **Perplexity**: All models

---

## Web Fetch

Retrieve full content from specific URLs (Anthropic models only).

```python
from praisonaiagents import Agent

# Enable web fetch with an Anthropic model
agent = Agent(
    name="Content Analyzer",
    instructions="You can fetch and analyze web content.",
    llm="anthropic/claude-sonnet-4-20250514",
    web_fetch=True
)

result = agent.start("Fetch and summarize https://example.com")
```

**Web Fetch Options:**
```python
agent = Agent(
    llm="anthropic/claude-sonnet-4-20250514",
    web_fetch={
        "max_uses": 10,
        "allowed_domains": ["example.com"],
        "citations": {"enabled": True}
    }
)
```

---

## Prompt Caching

Reduce costs and latency by caching parts of prompts.

```python
from praisonaiagents import Agent

# Enable prompt caching for Anthropic models
agent = Agent(
    name="Legal Analyst",
    instructions="You are an AI assistant analyzing legal documents." * 50,  # Long prompt
    llm="anthropic/claude-3-5-sonnet-latest",
    prompt_caching=True
)

# First call creates cache, subsequent calls use cached tokens
result = agent.start("Summarize the key terms")
```

**Supported Providers:**
- **OpenAI** (`openai/`) - Automatic caching for prompts ≥1024 tokens
- **Anthropic** (`anthropic/`) - Manual caching with `cache_control`
- **Bedrock** (`bedrock/`) - All models supporting prompt caching
- **Deepseek** (`deepseek/`) - Works like OpenAI

---

## Claude Memory Tool (Beta)

Enable Claude to store and retrieve information across conversations.

```python
from praisonaiagents import Agent

# Enable Claude memory (Anthropic models only)
agent = Agent(
    name="Research Assistant",
    llm="anthropic/claude-sonnet-4-20250514",
    claude_memory=True
)

# Claude will automatically:
# 1. Check /memories directory before tasks
# 2. Store progress/learnings in files
# 3. Reference memories in future conversations
result = agent.start("Research AI trends and remember key findings")
```

**Features:**
- File-based persistent memory in `.praison/claude_memory/`
- Claude autonomously decides what to store/retrieve
- Supports: view, create, str_replace, insert, delete, rename commands
- Cross-conversation learning

**Supported Models:** Claude Sonnet 4, Claude Opus 4, Claude Haiku 4.5

---

## Memory (Zero Dependencies)

Enable persistent memory for agents without any extra packages.

```python
from praisonaiagents import Agent

# Simple: Enable file-based memory (no extra dependencies!)
agent = Agent(
    name="Assistant",
    memory=True  # Uses FileMemory by default
)

# Store memories
agent.store_memory("User prefers dark mode", memory_type="short_term")
agent.store_memory("User's name is John", memory_type="long_term", importance=0.9)

# Get memory context for prompts
context = agent.get_memory_context(query="What does the user prefer?")
```

**Memory Types:**
- **Short-term**: Rolling buffer of recent context (auto-expires)
- **Long-term**: Persistent important facts
- **Entity**: People, places, organizations
- **Episodic**: Date-based interaction history

**Storage Providers:**
| Provider | Dependencies | Use Case |
|----------|-------------|----------|
| `memory=True` or `"file"` | None | Default, zero-config |
| `"sqlite"` | Built-in | Search, indexing |
| `"chromadb"` | chromadb | Semantic/vector search |
| `"mem0"` | mem0ai | Graph memory, cloud |

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