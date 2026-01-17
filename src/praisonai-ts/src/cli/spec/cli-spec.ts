/**
 * PraisonAI CLI Specification - TypeScript Runtime
 * Parsed and validated spec from cli-spec.v1.yaml
 */

export const CLI_SPEC_VERSION = '1.0.0';

export interface CommandArg {
  name: string;
  type: 'string' | 'integer' | 'boolean';
  required: boolean;
  position?: number;
  description?: string;
}

export interface CommandFlag {
  name: string;
  short?: string;
  type: 'string' | 'integer' | 'boolean';
  default?: string | number | boolean;
  enum?: string[];
  description?: string;
  required?: boolean;
}

export interface Subcommand {
  description: string;
  args?: CommandArg[];
  flags?: CommandFlag[];
}

export interface Command {
  description: string;
  args?: CommandArg[];
  flags?: CommandFlag[];
  subcommands?: Record<string, Subcommand>;
}

export const COMMANDS: Record<string, Command> = {
  chat: {
    description: 'Chat with an AI agent',
    args: [
      { name: 'prompt', type: 'string', required: true, position: 0 }
    ],
    flags: [
      { name: 'model', short: 'm', type: 'string', description: 'Model to use (e.g., openai/gpt-4o-mini)' },
      { name: 'stream', short: 's', type: 'boolean', default: false, description: 'Enable streaming output' },
      { name: 'session', type: 'string', description: 'Session ID for conversation continuity' }
    ]
  },
  run: {
    description: 'Run an agent with a task',
    args: [
      { name: 'task', type: 'string', required: true, position: 0 }
    ],
    flags: [
      { name: 'agent', short: 'a', type: 'string', description: 'Agent configuration file or name' },
      { name: 'tools', short: 't', type: 'string', description: 'Comma-separated list of tools' }
    ]
  },
  workflow: {
    description: 'Execute a multi-agent workflow',
    args: [
      { name: 'file', type: 'string', required: true, position: 0, description: 'Workflow YAML file path' }
    ],
    flags: [
      { name: 'parallel', type: 'boolean', default: false, description: 'Run workflow steps in parallel where possible' }
    ]
  },
  agents: {
    description: 'Run multi-agent orchestration',
    args: [
      { name: 'task', type: 'string', required: false, position: 0, description: 'Task for agents to complete' }
    ],
    subcommands: {
      run: { description: 'Run multiple agents', args: [{ name: 'task', type: 'string', required: true, position: 0 }] }
    },
    flags: [
      { name: 'agents', short: 'a', type: 'string', description: 'Comma-separated agent instructions' },
      { name: 'process', short: 'p', type: 'string', enum: ['sequential', 'parallel'], default: 'sequential', description: 'Process mode' },
      { name: 'model', short: 'm', type: 'string', description: 'Model for all agents' }
    ]
  },
  eval: {

    description: 'Evaluate agent performance',
    subcommands: {
      accuracy: {
        description: 'Run accuracy evaluation',
        flags: [
          { name: 'input', type: 'string', required: true },
          { name: 'expected', type: 'string', required: true },
          { name: 'iterations', type: 'integer', default: 1 }
        ]
      },
      performance: {
        description: 'Run performance benchmark',
        flags: [
          { name: 'iterations', type: 'integer', default: 10 },
          { name: 'warmup', type: 'integer', default: 2 }
        ]
      },
      reliability: {
        description: 'Run reliability check',
        flags: [
          { name: 'expected-tools', type: 'string', description: 'Comma-separated expected tool calls' }
        ]
      }
    }
  },
  providers: {
    description: 'List available LLM providers',
    flags: []
  },
  llm: {
    description: 'AI SDK provider management and testing',
    subcommands: {
      providers: { description: 'List available AI SDK providers' },
      test: {
        description: 'Test connectivity to a provider',
        args: [{ name: 'provider', type: 'string', required: false, position: 0 }]
      },
      validate: {
        description: 'Validate provider configuration',
        args: [{ name: 'provider', type: 'string', required: false, position: 0 }]
      },
      run: {
        description: 'Run a prompt with a specific model',
        args: [{ name: 'prompt', type: 'string', required: true, position: 0 }]
      }
    },
    flags: [
      { name: 'model', short: 'm', type: 'string', description: 'Model to use (provider/model format)' },
      { name: 'stream', short: 's', type: 'boolean', default: false, description: 'Enable streaming output' },
      { name: 'timeout', type: 'integer', description: 'Request timeout in milliseconds' },
      { name: 'provider', short: 'p', type: 'string', description: 'Provider ID' }
    ]
  },
  tools: {
    description: 'List or manage tools',
    subcommands: {
      list: {
        description: 'List available tools'
      },
      info: {
        description: 'Show tool information',
        args: [
          { name: 'name', type: 'string', required: true, position: 0 }
        ]
      }
    }
  },
  memory: {
    description: 'Manage agent memory',
    subcommands: {
      list: { description: 'List all memories' },
      add: { description: 'Add a new memory', args: [{ name: 'content', type: 'string', required: true, position: 0 }] },
      search: { description: 'Search memories', args: [{ name: 'query', type: 'string', required: true, position: 0 }] },
      clear: { description: 'Clear all memories' }
    }
  },
  session: {
    description: 'Manage agent sessions',
    subcommands: {
      list: { description: 'List all sessions' },
      create: { description: 'Create a new session', args: [{ name: 'id', type: 'string', required: false, position: 0 }] },
      get: { description: 'Get session details', args: [{ name: 'id', type: 'string', required: true, position: 0 }] },
      delete: { description: 'Delete a session', args: [{ name: 'id', type: 'string', required: true, position: 0 }] },
      export: { description: 'Export session data', args: [{ name: 'id', type: 'string', required: true, position: 0 }] }
    }
  },
  knowledge: {
    description: 'Manage knowledge base',
    subcommands: {
      add: { description: 'Add knowledge from file or text', args: [{ name: 'source', type: 'string', required: true, position: 0 }] },
      search: { description: 'Search knowledge base', args: [{ name: 'query', type: 'string', required: true, position: 0 }] },
      list: { description: 'List all knowledge entries' }
    }
  },
  skills: {
    description: 'Manage agent skills',
    subcommands: {
      list: { description: 'List loaded skills' },
      discover: { description: 'Discover skills in directory', args: [{ name: 'path', type: 'string', required: false, position: 0 }] },
      validate: { description: 'Validate a skill', args: [{ name: 'path', type: 'string', required: true, position: 0 }] },
      info: { description: 'Show skill information', args: [{ name: 'name', type: 'string', required: true, position: 0 }] }
    }
  },
  mcp: {
    description: 'Model Context Protocol management',
    subcommands: {
      list: { description: 'List registered MCP servers' },
      add: { description: 'Add an MCP server', args: [{ name: 'name', type: 'string', required: true, position: 0 }] },
      remove: { description: 'Remove an MCP server', args: [{ name: 'name', type: 'string', required: true, position: 0 }] },
      start: { description: 'Start an MCP server', args: [{ name: 'name', type: 'string', required: true, position: 0 }] },
      stop: { description: 'Stop an MCP server', args: [{ name: 'name', type: 'string', required: true, position: 0 }] }
    }
  },
  auto: {
    description: 'Auto-generate agents from topic',
    args: [{ name: 'topic', type: 'string', required: true, position: 0 }],
    flags: [
      { name: 'pattern', type: 'string', description: 'Agent pattern (sequential, parallel, routing)' },
      { name: 'agents', type: 'integer', description: 'Number of agents to generate' }
    ]
  },
  image: {
    description: 'Image generation and analysis',
    subcommands: {
      generate: { description: 'Generate image from text', args: [{ name: 'prompt', type: 'string', required: true, position: 0 }] },
      analyze: { description: 'Analyze an image', args: [{ name: 'url', type: 'string', required: true, position: 0 }] }
    },
    flags: [
      { name: 'size', type: 'string', description: 'Image size' },
      { name: 'quality', type: 'string', description: 'Image quality' },
      { name: 'style', type: 'string', description: 'Image style' }
    ]
  },
  research: {
    description: 'Deep research on a topic',
    args: [{ name: 'query', type: 'string', required: true, position: 0 }],
    flags: [
      { name: 'depth', type: 'integer', description: 'Research depth (iterations)' },
      { name: 'max-sources', type: 'integer', description: 'Maximum sources to use' }
    ]
  },
  guardrail: {
    description: 'Content validation and safety',
    subcommands: {
      check: { description: 'Check content against guardrails', args: [{ name: 'content', type: 'string', required: true, position: 0 }] }
    },
    flags: [
      { name: 'criteria', type: 'string', description: 'Custom validation criteria' }
    ]
  },
  telemetry: {
    description: 'Usage monitoring and analytics',
    subcommands: {
      status: { description: 'Show telemetry status' },
      enable: { description: 'Enable telemetry' },
      disable: { description: 'Disable telemetry' },
      clear: { description: 'Clear telemetry data' },
      export: { description: 'Export telemetry data' }
    }
  },
  approval: {
    description: 'Tool approval management (AI SDK v6 parity)',
    subcommands: {
      status: { description: 'Show approval status' },
      pending: { description: 'List pending approval requests' },
      approve: { description: 'Approve a pending request', args: [{ name: 'id', type: 'string', required: true, position: 0 }] },
      deny: { description: 'Deny a pending request', args: [{ name: 'id', type: 'string', required: true, position: 0 }] },
      cancel: { description: 'Cancel a pending request', args: [{ name: 'id', type: 'string', required: true, position: 0 }] },
      'cancel-all': { description: 'Cancel all pending requests' },
      'auto-approve': { description: 'Auto-approve a tool', args: [{ name: 'tool', type: 'string', required: true, position: 0 }] },
      'auto-deny': { description: 'Auto-deny a tool', args: [{ name: 'tool', type: 'string', required: true, position: 0 }] },
      interactive: { description: 'Start interactive approval mode' }
    },
    flags: [
      { name: 'timeout', type: 'integer', description: 'Approval timeout in ms' }
    ]
  },
  planning: {
    description: 'Task planning and todo management',
    subcommands: {
      create: { description: 'Create a new plan', args: [{ name: 'name', type: 'string', required: true, position: 0 }] },
      todo: { description: 'Manage todo items' }
    }
  },
  'query-rewrite': {
    description: 'Rewrite queries for better search results',
    args: [{ name: 'query', type: 'string', required: true, position: 0 }],
    flags: [
      { name: 'strategy', type: 'string', description: 'Rewrite strategy (expand, simplify, decompose, rephrase, auto)' }
    ]
  },
  'prompt-expand': {
    description: 'Expand prompts with more detail',
    args: [{ name: 'prompt', type: 'string', required: true, position: 0 }],
    flags: [
      { name: 'strategy', type: 'string', description: 'Expand strategy (detail, context, examples, constraints, auto)' }
    ]
  },
  router: {
    description: 'Route requests to appropriate agents',
    subcommands: {
      analyze: { description: 'Analyze input and suggest routing', args: [{ name: 'input', type: 'string', required: true, position: 0 }] }
    }
  },
  context: {
    description: 'Manage conversation context',
    subcommands: {
      chat: { description: 'Chat with context management', args: [{ name: 'message', type: 'string', required: true, position: 0 }] },
      summarize: { description: 'Summarize context', args: [{ name: 'text', type: 'string', required: true, position: 0 }] }
    },
    flags: [
      { name: 'max-messages', type: 'integer', description: 'Maximum messages in context' }
    ]
  },
  handoff: {
    description: 'Agent handoff management',
    subcommands: {
      info: { description: 'Show handoff feature information' }
    }
  },
  vector: {
    description: 'Vector store management',
    subcommands: {
      info: { description: 'Show vector store information' },
      providers: { description: 'List available vector store providers' }
    }
  },
  observability: {
    description: 'Monitoring and tracing',
    subcommands: {
      info: { description: 'Show observability information' },
      providers: { description: 'List available observability providers' }
    }
  },
  voice: {
    description: 'Text-to-speech and speech-to-text',
    subcommands: {
      info: { description: 'Show voice feature information' },
      providers: { description: 'List available voice providers' }
    }
  },
  reranker: {
    description: 'Document reranking',
    subcommands: {
      info: { description: 'Show reranker information' },
      providers: { description: 'List available reranker providers' }
    }
  },
  'graph-rag': {
    description: 'Graph-based retrieval augmented generation',
    subcommands: {
      info: { description: 'Show Graph RAG information' }
    }
  },
  cache: {
    description: 'Caching management',
    subcommands: {
      info: { description: 'Show cache information' },
      providers: { description: 'List available cache providers' }
    }
  },
  db: {
    description: 'Database adapter management',
    subcommands: {
      info: { description: 'Show database adapter information' },
      adapters: { description: 'List available database adapters' }
    }
  },
  scheduler: {
    description: 'Agent task scheduling',
    subcommands: {
      create: { description: 'Create a scheduled task', args: [{ name: 'name', type: 'string', required: true, position: 0 }] },
      list: { description: 'List all scheduled tasks' },
      run: { description: 'Run a task immediately', args: [{ name: 'id', type: 'string', required: true, position: 0 }] },
      remove: { description: 'Remove a scheduled task', args: [{ name: 'id', type: 'string', required: true, position: 0 }] },
      enable: { description: 'Enable a task', args: [{ name: 'id', type: 'string', required: true, position: 0 }] },
      disable: { description: 'Disable a task', args: [{ name: 'id', type: 'string', required: true, position: 0 }] },
      patterns: { description: 'Show common cron patterns' }
    },
    flags: [
      { name: 'cron', type: 'string', description: 'Cron expression' },
      { name: 'interval', type: 'integer', description: 'Interval in seconds' }
    ]
  },
  jobs: {
    description: 'Background job queue management',
    subcommands: {
      add: { description: 'Add a new job', args: [{ name: 'name', type: 'string', required: true, position: 0 }] },
      list: { description: 'List all jobs' },
      get: { description: 'Get job details', args: [{ name: 'id', type: 'string', required: true, position: 0 }] },
      cancel: { description: 'Cancel a pending job', args: [{ name: 'id', type: 'string', required: true, position: 0 }] },
      retry: { description: 'Retry a failed job', args: [{ name: 'id', type: 'string', required: true, position: 0 }] },
      process: { description: 'Process a job immediately', args: [{ name: 'id', type: 'string', required: true, position: 0 }] },
      stats: { description: 'Show queue statistics' },
      cleanup: { description: 'Clean up old jobs' }
    },
    flags: [
      { name: 'storage', type: 'string', description: 'Path to job storage file' },
      { name: 'priority', type: 'string', description: 'Job priority (low, normal, high, critical)' },
      { name: 'status', type: 'string', description: 'Filter by status' }
    ]
  },
  checkpoints: {
    description: 'Session state checkpointing',
    subcommands: {
      create: { description: 'Create a checkpoint', args: [{ name: 'name', type: 'string', required: false, position: 0 }] },
      list: { description: 'List all checkpoints' },
      get: { description: 'Get checkpoint details', args: [{ name: 'id', type: 'string', required: true, position: 0 }] },
      restore: { description: 'Restore from checkpoint', args: [{ name: 'id', type: 'string', required: false, position: 0 }] },
      delete: { description: 'Delete a checkpoint', args: [{ name: 'id', type: 'string', required: true, position: 0 }] },
      export: { description: 'Export checkpoint as JSON', args: [{ name: 'id', type: 'string', required: true, position: 0 }] },
      import: { description: 'Import checkpoint from JSON', args: [{ name: 'json', type: 'string', required: true, position: 0 }] }
    },
    flags: [
      { name: 'storage', type: 'string', description: 'Path to checkpoint storage' },
      { name: 'state', type: 'string', description: 'JSON state to save' }
    ]
  },
  'fast-context': {
    description: 'Fast context retrieval',
    subcommands: {
      query: { description: 'Query for relevant context', args: [{ name: 'query', type: 'string', required: true, position: 0 }] },
      stats: { description: 'Show cache statistics' },
      clear: { description: 'Clear cache and sources' }
    },
    flags: [
      { name: 'max-tokens', type: 'integer', description: 'Maximum tokens in context' },
      { name: 'sources', type: 'string', description: 'Comma-separated source texts' }
    ]
  },
  autonomy: {
    description: 'Autonomy mode management',
    subcommands: {
      status: { description: 'Show current autonomy status' },
      set: { description: 'Set autonomy mode', args: [{ name: 'mode', type: 'string', required: true, position: 0 }] },
      policies: { description: 'Show policies for a mode', args: [{ name: 'mode', type: 'string', required: false, position: 0 }] },
      reset: { description: 'Reset autonomy state' }
    }
  },
  sandbox: {
    description: 'Safe command execution',
    subcommands: {
      exec: { description: 'Execute a command in sandbox', args: [{ name: 'command', type: 'string', required: true, position: 0 }] },
      check: { description: 'Check if command is allowed', args: [{ name: 'command', type: 'string', required: true, position: 0 }] },
      mode: { description: 'List available sandbox modes' }
    },
    flags: [
      { name: 'mode', type: 'string', description: 'Sandbox mode (disabled, basic, strict, network-isolated)' },
      { name: 'timeout', type: 'integer', description: 'Execution timeout in ms' }
    ]
  },
  'repo-map': {
    description: 'Repository structure visualization',
    subcommands: {
      tree: { description: 'Show repository tree', args: [{ name: 'path', type: 'string', required: false, position: 0 }] },
      symbols: { description: 'Extract code symbols', args: [{ name: 'path', type: 'string', required: false, position: 0 }] }
    },
    flags: [
      { name: 'depth', type: 'integer', description: 'Maximum directory depth' },
      { name: 'symbols', type: 'boolean', description: 'Include symbols in tree' }
    ]
  },
  git: {
    description: 'Git integration (read-only)',
    subcommands: {
      status: { description: 'Show repository status' },
      diff: { description: 'Show changes' },
      log: { description: 'Show recent commits' },
      branches: { description: 'List branches' },
      stash: { description: 'List stashes' }
    },
    flags: [
      { name: 'cwd', type: 'string', description: 'Working directory' },
      { name: 'staged', type: 'boolean', description: 'Show staged changes only' },
      { name: 'limit', type: 'integer', description: 'Number of commits to show' }
    ]
  },
  n8n: {
    description: 'N8N workflow integration',
    subcommands: {
      trigger: { description: 'Trigger an N8N webhook', args: [{ name: 'webhookId', type: 'string', required: true, position: 0 }] },
      export: { description: 'Export workflow to N8N format', args: [{ name: 'name', type: 'string', required: false, position: 0 }] }
    },
    flags: [
      { name: 'base-url', type: 'string', description: 'N8N base URL' },
      { name: 'api-key', type: 'string', description: 'N8N API key' },
      { name: 'steps', type: 'string', description: 'Workflow steps' }
    ]
  },
  'external-agents': {
    description: 'External AI CLI tool integration',
    subcommands: {
      list: { description: 'List all external agents' },
      check: { description: 'Check agent availability', args: [{ name: 'name', type: 'string', required: true, position: 0 }] },
      run: { description: 'Run with external agent', args: [{ name: 'name', type: 'string', required: true, position: 0 }] }
    },
    flags: [
      { name: 'cwd', type: 'string', description: 'Working directory' }
    ]
  },
  flow: {
    description: 'Workflow flow visualization',
    subcommands: {
      show: { description: 'Display workflow as text', args: [{ name: 'steps', type: 'string', required: false, position: 0 }] },
      dot: { description: 'Export as DOT format', args: [{ name: 'steps', type: 'string', required: false, position: 0 }] }
    },
    flags: [
      { name: 'steps', type: 'string', description: 'Steps as JSON or comma-separated' },
      { name: 'boxes', type: 'boolean', description: 'Display as ASCII boxes' },
      { name: 'compact', type: 'boolean', description: 'Compact display mode' }
    ]
  },
  cost: {
    description: 'Token usage and cost tracking',
    subcommands: {
      summary: { description: 'Show cost summary' },
      add: { description: 'Add token usage', args: [{ name: 'model', type: 'string', required: true, position: 0 }] },
      reset: { description: 'Reset cost tracker' },
      pricing: { description: 'Show model pricing', args: [{ name: 'model', type: 'string', required: false, position: 0 }] }
    }
  },
  interactive: {
    description: 'Interactive TUI mode',
    flags: [
      { name: 'model', short: 'm', type: 'string', description: 'Model to use' },
      { name: 'prompt', type: 'string', description: 'Custom prompt string' },
      { name: 'history', type: 'string', description: 'Path to history file' }
    ]
  },
  version: {
    description: 'Show CLI version',
    flags: []
  },
  help: {
    description: 'Show help information',
    args: [
      { name: 'command', type: 'string', required: false, position: 0 }
    ]
  },
  embed: {
    description: 'Generate embeddings using AI SDK',
    subcommands: {
      text: { description: 'Embed text(s)', args: [{ name: 'text', type: 'string', required: true, position: 0 }] },
      file: { description: 'Embed file contents', args: [{ name: 'path', type: 'string', required: true, position: 0 }] },
      query: { description: 'Query similar texts', args: [{ name: 'query', type: 'string', required: true, position: 0 }] },
      models: { description: 'List available embedding models' }
    },
    flags: [
      { name: 'model', short: 'm', type: 'string', description: 'Embedding model to use' },
      { name: 'provider', type: 'string', description: 'Provider (openai, google, cohere)' },
      { name: 'backend', type: 'string', description: 'Backend (ai-sdk, native, auto)' },
      { name: 'save', type: 'string', description: 'Save embeddings to file' },
      { name: 'file', type: 'string', description: 'Embeddings file for query' }
    ]
  },
  benchmark: {
    description: 'Run performance benchmarks',
    subcommands: {
      run: { description: 'Run all benchmarks' },
      import: { description: 'Benchmark import time' },
      memory: { description: 'Benchmark memory usage' },
      latency: { description: 'Benchmark first-call latency' },
      streaming: { description: 'Benchmark streaming throughput' },
      embedding: { description: 'Benchmark embedding throughput' }
    },
    flags: [
      { name: 'iterations', type: 'integer', description: 'Number of iterations' },
      { name: 'backend', type: 'string', description: 'Backend to test (ai-sdk, native, both)' },
      { name: 'real', type: 'boolean', description: 'Use real API calls (requires keys)' }
    ]
  },
  hooks: {
    description: 'Manage hooks and callbacks',
    subcommands: {
      list: { description: 'List all available hook events' },
      events: { description: 'List hook events (alias for list)' },
      'display-types': { description: 'List display callback types' },
      stats: { description: 'Show hooks statistics' },
      clear: { description: 'Clear all registered callbacks' }
    }
  },
  agent: {
    description: 'Create and run a single agent',
    args: [
      { name: 'task', type: 'string', required: false, position: 0, description: 'Task for the agent to complete' }
    ],
    flags: [
      { name: 'instructions', short: 'i', type: 'string', description: 'Agent instructions' },
      { name: 'model', short: 'm', type: 'string', description: 'Model to use' },
      { name: 'tools', short: 't', type: 'string', description: 'Comma-separated list of tools' }
    ]
  }
};

export const GLOBAL_FLAGS: CommandFlag[] = [
  { name: 'verbose', short: 'v', type: 'boolean', default: false, description: 'Enable verbose output' },
  { name: 'config', short: 'c', type: 'string', description: 'Path to config file' },
  { name: 'profile', short: 'p', type: 'string', description: 'Profile name to use' },
  { name: 'output', short: 'o', type: 'string', enum: ['json', 'text', 'pretty'], default: 'pretty', description: 'Output format' },
  { name: 'json', type: 'boolean', default: false, description: 'Shorthand for --output json' },
  { name: 'db', type: 'string', description: 'Database URL for persistence (sqlite:./data.db, postgres://, redis://)' }
];

export const EXIT_CODES = {
  SUCCESS: 0,
  RUNTIME_ERROR: 1,
  INVALID_ARGUMENTS: 2,
  CONFIG_ERROR: 3,
  NETWORK_ERROR: 4,
  AUTH_ERROR: 5
} as const;

export type ExitCode = typeof EXIT_CODES[keyof typeof EXIT_CODES];

export interface SuccessOutput<T = unknown> {
  success: true;
  data: T;
  meta?: {
    duration_ms?: number;
    model?: string;
    tokens?: {
      input?: number;
      output?: number;
    };
  };
}

export interface ErrorOutput {
  success: false;
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

export type CLIOutput<T = unknown> = SuccessOutput<T> | ErrorOutput;

export const ENV_VARS = {
  PRAISONAI_MODEL: 'PRAISONAI_MODEL',
  PRAISONAI_PROFILE: 'PRAISONAI_PROFILE',
  PRAISONAI_VERBOSE: 'PRAISONAI_VERBOSE',
  PRAISONAI_CONFIG: 'PRAISONAI_CONFIG',
  PRAISONAI_DB: 'PRAISONAI_DB',
  OPENAI_API_KEY: 'OPENAI_API_KEY',
  ANTHROPIC_API_KEY: 'ANTHROPIC_API_KEY',
  GOOGLE_API_KEY: 'GOOGLE_API_KEY'
} as const;

export const CONFIG_FILES = ['.praisonai.yaml', '.praisonai.json'] as const;

export interface ConfigSchema {
  model?: string;
  verbose?: boolean;
  stream?: boolean;
  profiles?: Record<string, {
    model?: string;
    verbose?: boolean;
    stream?: boolean;
  }>;
}

export function validateCommand(command: string): command is keyof typeof COMMANDS {
  return command in COMMANDS;
}

export function getCommandSpec(command: string): Command | undefined {
  return COMMANDS[command];
}

export function getAllFlags(command: string): CommandFlag[] {
  const cmdSpec = COMMANDS[command];
  const cmdFlags = cmdSpec?.flags || [];
  return [...GLOBAL_FLAGS, ...cmdFlags];
}
