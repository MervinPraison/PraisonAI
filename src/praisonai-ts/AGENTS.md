# AGENTS.md - PraisonAI TypeScript SDK Comprehensive Guide

> **For AI Agents and Developers**: This document provides the complete context needed to work with the PraisonAI TypeScript SDK, including design principles, architecture, repository structure, and implementation guidelines.

---

## 1. What is PraisonAI TypeScript?

PraisonAI TypeScript is a **high-performance, agentic AI framework** for Node.js/JavaScript, designed for building production-ready AI agents and multi-agent workflows.

### Core Philosophy

```
Simpler than competitors • More extensible • Faster • Agent-centric
```

| Principle | Description |
|-----------|-------------|
| **Agent-Centric** | Every design decision centers on Agents, workflows, sessions, tools, and memory |
| **TypeScript-First** | Full type safety with excellent IntelliSense support |
| **AI SDK Integration** | First-class support for Vercel AI SDK providers |
| **Minimal API** | Fewer parameters, sensible defaults, explicit overrides |
| **Performance-First** | Lazy loading, optional dependencies, no hot-path regressions |
| **Multi-Agent Safe** | Concurrent execution, no shared mutable state issues |
| **TDD Mandatory** | Tests first; failing tests prove gaps; passing tests prove fixes |
| **Production-Ready** | Safe by default, async-safe, observable |

---

## 2. Repository Structure

### 2.1 Canonical Paths

```
/Users/praison/praisonai-package/
├── src/
│   ├── praisonai-agents/          # Python SDK (praisonaiagents)
│   │   ├── praisonaiagents/       # Python package
│   │   ├── tests/                 # Unit & integration tests
│   │   └── examples/              # Package-level examples
│   │
│   ├── praisonai-ts/              # TypeScript SDK (this package)
│   │   ├── src/                   # Source code
│   │   ├── tests/                 # Unit & integration tests
│   │   ├── examples/              # TypeScript examples
│   │   └── package.json           # Package config
│   │
│   └── praisonai/                 # Wrapper (praisonai CLI)
│
├── examples/                      # Main examples directory
│   ├── python/                    # Python examples
│   ├── yaml/                      # YAML configuration examples
│   └── js/                        # JavaScript/TypeScript examples
│
/Users/praison/PraisonAIDocs/      # Documentation (Mintlify)
```

### 2.2 TypeScript SDK Source Structure

```
src/
├── agent/              # Core Agent implementations (20 files)
│   ├── simple.ts       # Main Agent class
│   ├── audio.ts        # AudioAgent
│   ├── video.ts        # VideoAgent
│   ├── vision.ts       # VisionAgent
│   ├── code.ts         # CodeAgent
│   ├── research.ts     # DeepResearchAgent
│   ├── handoff.ts      # Agent handoff system
│   └── router.ts       # RouterAgent
│
├── tools/              # Tool SDK (27 files)
│   ├── decorator.ts    # Tool function & FunctionTool class
│   ├── registry.ts     # Tool registry with middleware
│   ├── tools.ts        # Tools facade (40+ built-ins)
│   └── builtins/       # Built-in tools (13 modules)
│
├── workflows/          # Workflow engine (4 files)
│   ├── index.ts        # Workflow, Task, Pipeline
│   ├── loop.ts         # Loop pattern
│   └── repeat.ts       # Repeat pattern
│
├── memory/             # Memory systems (7 files)
│   ├── memory.ts       # Base Memory class
│   ├── auto-memory.ts  # AutoMemory with auto-detection
│   ├── file-memory.ts  # FileMemory for persistence
│   └── rules-manager.ts # Rules management
│
├── hooks/              # Hooks & middleware (4 files)
│   ├── manager.ts      # HookManager
│   ├── callbacks.ts    # Callbacks system
│   └── workflow-hooks.ts # Workflow-specific hooks
│
├── llm/                # LLM providers (18 files)
│   ├── openai.ts       # OpenAI client
│   ├── providers/      # Provider implementations
│   │   ├── ai-sdk/     # Vercel AI SDK integration
│   │   ├── anthropic.ts
│   │   ├── google.ts
│   │   └── openai.ts
│   └── backend-resolver.ts # Automatic backend selection
│
├── knowledge/          # Knowledge & RAG (10 files)
│   ├── knowledge.ts    # Knowledge base
│   ├── rag.ts          # RAG implementation
│   ├── graph-rag.ts    # Graph-based RAG
│   └── query-engine.ts # Query processing
│
├── mcp/                # Model Context Protocol (5 files)
│   ├── index.ts        # MCP client
│   ├── server.ts       # MCP server
│   ├── session.ts      # Session management
│   └── transports.ts   # Transport layer (stdio, SSE, WebSocket)
│
├── observability/      # Observability adapters (21 files)
│   ├── adapters/       # External integrations
│   │   └── external/   # Langfuse, LangSmith, Helicone, etc.
│   └── types.ts        # Trace types
│
├── eval/               # Evaluation framework (4 files)
│   ├── judge.ts        # LLM-based evaluation
│   ├── base.ts         # Evaluator base
│   └── results.ts      # Results handling
│
├── guardrails/         # Input/output guardrails (2 files)
├── session/            # Session management (5 files)
├── context/            # Context optimization (5 files)
├── telemetry/          # Telemetry collection (3 files)
├── integrations/       # External integrations (15 files)
│   ├── computer-use.ts # Computer Use
│   ├── postgres.ts     # PostgreSQL
│   ├── slack.ts        # Slack
│   └── voice/          # Voice integrations
│
├── ai/                 # AI SDK helpers (19 files)
│   ├── generate-text.ts
│   ├── generate-object.ts
│   ├── generate-image.ts
│   └── speech.ts
│
├── cli/                # CLI (78 files)
│   ├── commands/       # 51 command modules
│   └── features/       # 16 feature modules
│
└── index.ts            # Main exports (938 lines)
```

---

## 3. Core Classes & Types

### 3.1 Agent

The primary class for creating AI agents:

```typescript
import { Agent } from 'praisonai';

interface SimpleAgentConfig {
  name?: string;           // Agent identifier
  instructions: string;    // System prompt/instructions
  llm?: string;            // Model: 'gpt-4o-mini', 'claude-3-opus', etc.
  verbose?: boolean;       // Enable logging
  stream?: boolean;        // Enable streaming
  tools?: any[];           // Tool functions or FunctionTool instances
  db?: DbAdapter;          // Database adapter for persistence
  sessionId?: string;      // Session identifier
  memory?: boolean;        // Enable memory
  cache?: boolean;         // Enable response caching
  telemetry?: boolean;     // Enable telemetry
  role?: string;           // Agent role
  goal?: string;           // Agent goal
  backstory?: string;      // Agent backstory
}
```

### 3.2 AgentTeam (Agents)

Multi-agent orchestration:

```typescript
import { AgentTeam, Agent } from 'praisonai';

interface AgentTeamConfig {
  agents?: Agent[];                         // List of agents
  tasks?: (Task | string)[];                // Tasks to execute
  verbose?: boolean;                        // Enable logging
  process?: 'sequential' | 'parallel' | 'hierarchical';
  manager_llm?: string;                     // Manager LLM for hierarchical
}

// Aliases for Python parity
export type Agents = AgentTeam;
export type PraisonAIAgents = AgentTeam;
```

### 3.3 Task

Task definition for workflows:

```typescript
import { Task, Agent } from 'praisonai';

interface TaskConfig {
  name: string;
  description: string;
  expected_output?: string;
  agent?: Agent;
  dependencies?: Task[];
}
```

### 3.4 FunctionTool

Type-safe tool creation:

```typescript
import { tool, FunctionTool } from 'praisonai';

const myTool = tool({
  name: 'search',
  description: 'Search the web',
  parameters: {
    type: 'object',
    properties: {
      query: { type: 'string', description: 'Search query' }
    },
    required: ['query']
  },
  async execute({ query }) {
    return `Results for: ${query}`;
  }
});
```

---

## 4. Core Engineering Principles

### 4.1 TypeScript-First Design

```typescript
// ✅ CORRECT: Full type safety
interface ToolConfig<TParams = any, TResult = any> {
  name: string;
  description?: string;
  parameters?: ToolParameters | any;
  execute: (params: TParams, context?: ToolContext) => Promise<TResult> | TResult;
}

// ❌ WRONG: Using any without generics
function createTool(config: any): any;
```

### 4.2 AI SDK Integration

PraisonAI TypeScript provides first-class support for Vercel AI SDK:

```typescript
// Automatic backend resolution
const agent = new Agent({
  instructions: "Be helpful",
  llm: "gpt-4o-mini"  // Resolves to AI SDK or native OpenAI
});

// Get backend info
const backend = await agent.getBackend();
const source = agent.getBackendSource(); // 'ai-sdk' | 'native' | 'custom'
```

### 4.3 Lazy Import Pattern

```typescript
// ✅ CORRECT: Lazy import for optional dependencies
async function useFirecrawl() {
  const { Firecrawl } = await import('@mendable/firecrawl-js');
  return new Firecrawl();
}

// ❌ WRONG: Top-level import of optional dependency
import { Firecrawl } from '@mendable/firecrawl-js';
```

### 4.4 Async/Await Pattern

```typescript
// Entry points: Always async
async start(prompt: string): Promise<string>;
async chat(prompt: string): Promise<string>;

// Internal: Prefer async
async processToolCalls(toolCalls: any[]): Promise<ToolResult[]>;

// Utilities: Support both
function parseArgs(args: string[]): ParsedArgs;
async function loadConfig(path: string): Promise<Config>;
```

### 4.5 Error Handling

```typescript
// Custom error classes
export class MissingDependencyError extends Error {
  constructor(packageName: string, installCommand?: string) {
    super(`Missing dependency: ${packageName}. Install with: ${installCommand}`);
    this.name = 'MissingDependencyError';
  }
}

export class MissingEnvVarError extends Error {
  constructor(envVar: string) {
    super(`Missing environment variable: ${envVar}`);
    this.name = 'MissingEnvVarError';
  }
}
```

---

## 5. Built-in Tools

### 5.1 Tools Facade

Access all built-in tools through the `tools` object:

```typescript
import { Agent, tools } from 'praisonai';

const agent = new Agent({
  instructions: "Research assistant",
  tools: [
    tools.tavily(),           // Web search
    tools.codeExecution(),    // Code sandbox
    tools.firecrawl(),        // Web scraping
    tools.perplexity(),       // Perplexity search
  ]
});
```

### 5.2 Available Built-in Tools

| Category | Tools |
|----------|-------|
| **Search** | `tavily()`, `tavilySearch()`, `tavilyExtract()`, `tavilyCrawl()` |
| **Search** | `exa()`, `exaSearch()`, `perplexity()`, `perplexitySearch()` |
| **Search** | `parallel()`, `parallelSearch()` (multi-provider) |
| **Scraping** | `firecrawl()`, `firecrawlScrape()`, `firecrawlCrawl()` |
| **Domain Search** | `valyuWebSearch()`, `valyuFinanceSearch()`, `valyuPaperSearch()` |
| **Domain Search** | `valyuBioSearch()`, `valyuPatentSearch()`, `valyuSecSearch()` |
| **Security** | `guard()`, `redact()`, `verify()` (superagent) |
| **Code** | `codeExecution()`, `executeCode()`, `codeMode()` |
| **Bedrock** | `bedrockCodeInterpreter()`, `bedrockBrowserNavigate()` |
| **Vector** | `airweave()`, `airweaveSearch()` |
| **Custom** | `custom()` for custom tool creation |

---

## 6. LLM Providers

### 6.1 Supported Providers

| Provider | Config Key | Models |
|----------|------------|--------|
| **OpenAI** | `openai/gpt-4o-mini` | gpt-4o, gpt-4o-mini, gpt-4-turbo |
| **Anthropic** | `anthropic/claude-3-opus` | claude-3-opus, claude-3-sonnet, claude-3-haiku |
| **Google** | `google/gemini-1.5-pro` | gemini-1.5-pro, gemini-1.5-flash |
| **AI SDK** | via peer dependency | All AI SDK providers |

### 6.2 Backend Resolution

```typescript
// Automatic resolution (AI SDK preferred)
const agent = new Agent({ llm: "gpt-4o-mini" });

// Force native provider
const agent = new Agent({ llm: "openai/gpt-4o-mini" });

// Check backend
const backend = await agent.getBackend();
console.log(agent.getBackendSource()); // 'ai-sdk' | 'native'
```

---

## 7. Memory System

### 7.1 Memory Types

```typescript
import { Memory, FileMemory, AutoMemory } from 'praisonai';

// Basic memory
const memory = new Memory({ sessionId: "user-123" });

// File-based persistence
const fileMemory = new FileMemory({
  path: './data/memory.json',
  sessionId: "user-123"
});

// Auto-detecting memory (short-term + long-term)
const autoMemory = new AutoMemory({
  enableShortTerm: true,
  enableLongTerm: true,
  provider: 'file'  // or 'sqlite', 'chroma'
});
```

### 7.2 Memory with Agent

```typescript
import { Agent, db } from 'praisonai';

const agent = new Agent({
  instructions: "You are a helpful assistant",
  db: db("sqlite:./data.db"),
  sessionId: "conversation-123",
  memory: true
});
```

---

## 8. Hooks & Callbacks

### 8.1 Agent Callbacks

```typescript
import { Agent, AgentCallbacks } from 'praisonai';

const callbacks: AgentCallbacks = {
  onStart: (agent, input) => console.log('Starting:', input),
  onEnd: (agent, output) => console.log('Result:', output),
  onToolCall: (agent, tool, args) => console.log('Calling:', tool),
  onError: (agent, error) => console.error('Error:', error)
};

const agent = new Agent({
  instructions: "Be helpful",
  callbacks
});
```

### 8.2 Workflow Hooks

```typescript
import { WorkflowHooks, createLoggingWorkflowHooks } from 'praisonai';

const hooks: WorkflowHooks = {
  onStepStart: (step, context) => { /* ... */ },
  onStepEnd: (step, result, context) => { /* ... */ },
  onWorkflowStart: (workflow, context) => { /* ... */ },
  onWorkflowEnd: (workflow, results, context) => { /* ... */ }
};
```

---

## 9. Workflows

### 9.1 Task-Based Workflows

```typescript
import { Task, Workflow, createContext } from 'praisonai';

const researchTask = new Task({
  name: 'research',
  async execute(input, context) {
    return await performResearch(input);
  }
});

const summaryTask = new Task({
  name: 'summarize',
  async execute(input, context) {
    const research = context.get('research');
    return summarize(research);
  }
});

const workflow = new Workflow([researchTask, summaryTask]);
const results = await workflow.run(createContext('workflow-1'));
```

### 9.2 Loop Pattern

```typescript
import { Loop, loop } from 'praisonai';

const iterativeLoop = new Loop({
  maxIterations: 5,
  async condition(context) {
    return context.iteration < 5;
  },
  async body(context) {
    return await processIteration(context);
  }
});
```

### 9.3 Repeat Pattern

```typescript
import { Repeat, repeat } from 'praisonai';

const repeater = new Repeat({
  times: 3,
  async action(context) {
    return await performAction(context);
  }
});
```

---

## 10. MCP (Model Context Protocol)

### 10.1 MCP Client

```typescript
import { MCPClient, createMCPClient } from 'praisonai';

const client = await createMCPClient({
  transport: 'stdio',
  command: 'npx',
  args: ['-y', '@modelcontextprotocol/server-filesystem', '/path']
});

const tools = await client.listTools();
const result = await client.callTool('read_file', { path: '/file.txt' });
```

### 10.2 MCP Server

```typescript
import { MCPServer, createMCPServer } from 'praisonai';

const server = createMCPServer({
  name: 'my-server',
  version: '1.0.0',
  tools: [myTool1, myTool2]
});

await server.start({ transport: 'stdio' });
```

---

## 11. Observability

### 11.1 External Adapters

```typescript
import { createLangfuseAdapter, createLangSmithAdapter } from 'praisonai';

// Langfuse
const langfuseAdapter = createLangfuseAdapter({
  publicKey: process.env.LANGFUSE_PUBLIC_KEY,
  secretKey: process.env.LANGFUSE_SECRET_KEY
});

// LangSmith
const langsmithAdapter = createLangSmithAdapter({
  apiKey: process.env.LANGSMITH_API_KEY
});
```

### 11.2 Supported Platforms

- Langfuse, LangSmith, LangWatch
- Arize, Axiom, Braintrust
- Helicone, Laminar, Maxim
- Patronus, Scorecard, SignOz
- Traceloop, Weave

---

## 12. Guardrails

```typescript
import { createGuardrail, GuardrailAction } from 'praisonai';

const contentGuardrail = createGuardrail({
  name: 'content-filter',
  async check(input) {
    if (containsHarmfulContent(input)) {
      return { action: GuardrailAction.BLOCK, reason: 'Harmful content' };
    }
    return { action: GuardrailAction.ALLOW };
  }
});

const agent = new Agent({
  instructions: "Be helpful",
  guardrails: [contentGuardrail]
});
```

---

## 13. Specialized Agents

### 13.1 Available Agent Types

| Agent | Purpose |
|-------|---------|
| `Agent` | Base agent for general tasks |
| `AudioAgent` | Speech synthesis and transcription |
| `VideoAgent` | Video generation and analysis |
| `VisionAgent` | Image analysis and understanding |
| `CodeAgent` | Code generation and execution |
| `DeepResearchAgent` | Multi-step research workflows |
| `RouterAgent` | Route requests to appropriate agents |
| `ContextAgent` | Context-aware responses |

### 13.2 Example: AudioAgent

```typescript
import { AudioAgent, createAudioAgent } from 'praisonai';

const audioAgent = createAudioAgent({
  voiceModel: 'alloy',
  transcriptionModel: 'whisper-1'
});

// Text to speech
const audio = await audioAgent.speak("Hello, world!");

// Speech to text
const text = await audioAgent.transcribe(audioBuffer);
```

---

## 14. CLI Commands

### 14.1 Basic Usage

```bash
# Install globally
npm install -g praisonai

# Run agent
praisonai-ts agent run --prompt "Hello"

# Multi-agent
praisonai-ts agents run --config agents.yaml

# Start server
praisonai-ts serve --port 8000
```

### 14.2 Command Categories

| Category | Commands |
|----------|----------|
| **Agent** | `agent run`, `agent chat` |
| **Multi-Agent** | `agents run`, `agents config` |
| **Tools** | `tools list`, `tools install` |
| **Memory** | `memory list`, `memory clear` |
| **MCP** | `mcp connect`, `mcp list` |
| **Server** | `serve`, `gateway` |

---

## 15. Testing

### 15.1 Test Structure

```
tests/
├── unit/              # Unit tests
├── integration/       # Integration tests
└── development/       # Development test scripts
```

### 15.2 Run Tests

```bash
# All tests
npm test

# With coverage
npm test -- --coverage

# Specific test file
npm test -- tests/unit/agent.test.ts
```

---

## 16. Dependencies

### 16.1 Required Dependencies

```json
{
  "dependencies": {
    "@modelcontextprotocol/sdk": "^1.12.1",
    "axios": "^1.7.9",
    "dotenv": "^16.4.7",
    "openai": "^4.81.0"
  }
}
```

### 16.2 Peer Dependencies (Optional)

```json
{
  "peerDependencies": {
    "@ai-sdk/anthropic": ">=1.0.0",
    "@ai-sdk/google": ">=1.0.0",
    "@ai-sdk/openai": ">=1.0.0",
    "ai": ">=4.0.0"
  }
}
```

### 16.3 Optional Dependencies

```json
{
  "optionalDependencies": {
    "@mendable/firecrawl-js": ">=1.0.0",
    "better-sqlite3": "^12.6.2",
    "bedrock-agentcore": ">=0.1.0"
  }
}
```

---

## 17. Quick Reference

### 17.1 Core Imports

```typescript
// Most common
import { Agent, AgentTeam, Task, tool, tools } from 'praisonai';

// Memory
import { Memory, FileMemory, AutoMemory, db } from 'praisonai';

// Hooks
import { HookManager, AgentCallbacks, WorkflowHooks } from 'praisonai';

// MCP
import { MCPClient, MCPServer, createMCPClient } from 'praisonai';

// Observability
import { createLangfuseAdapter, createLangSmithAdapter } from 'praisonai';

// Specialized agents
import { AudioAgent, VideoAgent, VisionAgent, CodeAgent } from 'praisonai';

// Workflows
import { Workflow, Loop, Repeat, createContext } from 'praisonai';

// RAG
import { RAG, createRAG, Knowledge } from 'praisonai';

// Eval
import { Evaluator, EvalSuite, createEvaluator } from 'praisonai';
```

### 17.2 File Locations

| What | Where |
|------|-------|
| Agent class | `src/agent/simple.ts` |
| Tool decorator | `src/tools/decorator.ts` |
| Tool registry | `src/tools/registry/index.ts` |
| Built-in tools | `src/tools/builtins/` |
| Hook system | `src/hooks/` |
| Memory | `src/memory/` |
| Workflows | `src/workflows/` |
| MCP | `src/mcp/` |
| LLM providers | `src/llm/providers/` |
| Observability | `src/observability/` |

---

## 18. Naming Conventions

```typescript
// Registration/Mutation
registerTool()       // Register tool to registry
addHook()            // Add hook to manager

// Retrieval
getTool()            // Single tool by name
getRegistry()        // Get global registry
listTools()          // All tools

// Creation
createAgent()        // Factory function
createMCPClient()    // Factory function

// Types & Interfaces
interface AgentConfig { }     // Configuration
interface AgentCallbacks { }  // Callbacks
type AgentResult = { }        // Result type

// Classes
class Agent { }               // Main class
class FunctionTool { }        // Tool class
class ToolRegistry { }        // Registry class
```

---

## 19. CLI Parity Requirement

Every feature implemented must have a corresponding CLI representation:

```typescript
// Pattern: If you add an API, add a CLI command
// Feature: Agent memory
// API: await agent.clearMemory()
// CLI: praisonai-ts memory clear --session <id>
```

| Feature | API | CLI Equivalent |
|---------|-----|----------------|
| Chat | `agent.chat(prompt)` | `praisonai-ts agent chat` |
| Multi-agent | `team.start(task)` | `praisonai-ts agents run` |
| Server | `createServer()` | `praisonai-ts serve` |

---

## 20. Verification Checklist

For every feature/change, verify:

- [ ] **Tests pass**: `npm test`
- [ ] **TypeScript compiles**: `npm run build`
- [ ] **Lint clean**: `npm run lint`
- [ ] **No heavy imports at top-level**: Check lazy loading
- [ ] **Async-safe**: Proper Promise handling
- [ ] **Multi-agent safe**: No shared mutable state
- [ ] **CLI works**: Command appears in `--help`
- [ ] **Docs updated**: JSDoc with examples

---

## 21. Documentation Standards

### 21.1 JSDoc Comments

All public APIs must have JSDoc with examples:

```typescript
/**
 * Creates an agent with the given configuration.
 *
 * @param config - Agent configuration
 * @returns Configured agent instance
 *
 * @example
 * ```typescript
 * const agent = new Agent({
 *   instructions: "Be helpful"
 * });
 * const response = await agent.chat("Hello");
 * ```
 */
export class Agent { }
```

### 21.2 Mermaid Diagrams

Use two-color scheme for architecture diagrams:
- **Dark Red (#8B0000)**: Agents, inputs, outputs
- **Teal (#189AB4)**: Tools, utilities

```mermaid
graph LR
    A[Agent]:::agent --> B[Tool]:::tool
    B --> C[Result]:::agent
    classDef agent fill:#8B0000,color:#fff
    classDef tool fill:#189AB4,color:#fff
```

### 21.3 Beginner-Friendly

Documentation should make users feel: *"With just a few lines of code, I can do this!"*

```typescript
// 3 lines to chat with AI
const agent = new Agent({ instructions: "Be helpful" });
const response = await agent.chat("Hello");
console.log(response);
```

---

## 22. Free Core / Paid Upgrade Path

Design features so that:

| Aspect | Guideline |
|--------|------------|
| **Core remains free** | Essential agent functionality always open source |
| **Clear upgrade path** | Support, cloud, managed services as paid options |
| **Reduces friction** | Features reduce production risk, not just add functionality |
| **Safe by default** | Simple to adopt, hard to misuse |

---

## 23. Implementation Checklist

For every feature/change:

- [ ] **TypeScript-first**: Full type definitions with generics
- [ ] **No new deps**: Use optional dependencies only
- [ ] **Lazy imports**: Heavy deps imported inside functions
- [ ] **Naming**: Follow conventions (create*, get*, XConfig)
- [ ] **Tests**: Write unit tests in `tests/`
- [ ] **Docs**: Update this file and Mintlify docs
- [ ] **Examples**: Add to `examples/` directory
- [ ] **Async-safe**: Support async/await patterns
- [ ] **Error handling**: Use custom error classes

---

## 24. Design Goals

> Make PraisonAI the **best TypeScript agent framework in the world**

1. **Simpler** than competitors (fewer concepts, cleaner API)
2. **More extensible** (registry-driven, plugin-ready)
3. **Faster** (lazy loading, AI SDK integration)
4. **Type-safe** (full TypeScript support)
5. **Production-ready** (observability, guardrails, MCP)

---

## 25. Python Parity

This TypeScript SDK maintains feature parity with the Python SDK:

| Python | TypeScript | Notes |
|--------|------------|-------|
| `Agent` | `Agent` | Same API |
| `Agents` | `AgentTeam` | `Agents` is alias |
| `Task` | `Task` | Same API |
| `@tool` | `tool()` | Function vs decorator |
| `Memory` | `Memory`, `FileMemory` | Same concepts |
| `Hooks` | `HookManager` | Same events |
| `Knowledge` | `Knowledge`, `RAG` | Same features |

---

*This document is the source of truth for the PraisonAI TypeScript SDK architecture and design principles.*
