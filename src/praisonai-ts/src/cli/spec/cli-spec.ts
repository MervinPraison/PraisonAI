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
  version: {
    description: 'Show CLI version',
    flags: []
  },
  help: {
    description: 'Show help information',
    args: [
      { name: 'command', type: 'string', required: false, position: 0 }
    ]
  }
};

export const GLOBAL_FLAGS: CommandFlag[] = [
  { name: 'verbose', short: 'v', type: 'boolean', default: false, description: 'Enable verbose output' },
  { name: 'config', short: 'c', type: 'string', description: 'Path to config file' },
  { name: 'profile', short: 'p', type: 'string', description: 'Profile name to use' },
  { name: 'output', short: 'o', type: 'string', enum: ['json', 'text', 'pretty'], default: 'pretty', description: 'Output format' },
  { name: 'json', type: 'boolean', default: false, description: 'Shorthand for --output json' }
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
