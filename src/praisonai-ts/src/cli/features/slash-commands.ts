/**
 * Slash Commands - Interactive command system for CLI
 * Supports /help, /cost, /clear, /model, /tokens, /plan, /undo, /diff, /commit, /exit, /settings, /map
 */

export interface SlashCommand {
  name: string;
  aliases?: string[];
  description: string;
  usage?: string;
  execute: (args: string[], context: SlashCommandContext) => Promise<SlashCommandResult>;
}

export interface SlashCommandContext {
  sessionId?: string;
  model?: string;
  tokenCount?: number;
  costTracker?: CostTracker;
  history?: string[];
  settings?: Record<string, any>;
  onOutput?: (message: string) => void;
}

export interface SlashCommandResult {
  success: boolean;
  message?: string;
  data?: any;
  shouldExit?: boolean;
}

export interface CostTracker {
  totalTokens: number;
  totalCost: number;
  requests: number;
  addUsage(model: string, inputTokens: number, outputTokens: number, latencyMs?: number): any;
  reset(): void;
  getSummary(): string;
}

/**
 * Built-in slash commands
 */
const BUILTIN_COMMANDS: SlashCommand[] = [
  {
    name: 'help',
    aliases: ['h', '?'],
    description: 'Show available commands',
    execute: async (_args, context) => {
      const commands = getRegistry().getAll();
      const lines = ['Available commands:', ''];
      for (const cmd of commands) {
        const aliases = cmd.aliases ? ` (${cmd.aliases.map(a => '/' + a).join(', ')})` : '';
        lines.push(`  /${cmd.name}${aliases} - ${cmd.description}`);
        if (cmd.usage) {
          lines.push(`    Usage: ${cmd.usage}`);
        }
      }
      context.onOutput?.(lines.join('\n'));
      return { success: true, message: lines.join('\n') };
    }
  },
  {
    name: 'cost',
    aliases: ['c'],
    description: 'Show token usage and cost',
    execute: async (_args, context) => {
      if (!context.costTracker) {
        return { success: false, message: 'Cost tracking not enabled' };
      }
      const summary = context.costTracker.getSummary();
      context.onOutput?.(summary);
      return { success: true, message: summary };
    }
  },
  {
    name: 'clear',
    description: 'Clear conversation history',
    execute: async (_args, context) => {
      if (context.history) {
        context.history.length = 0;
      }
      context.onOutput?.('Conversation cleared');
      return { success: true, message: 'Conversation cleared' };
    }
  },
  {
    name: 'model',
    aliases: ['m'],
    description: 'Show or change the current model',
    usage: '/model [model-name]',
    execute: async (args, context) => {
      if (args.length === 0) {
        const msg = `Current model: ${context.model || 'default'}`;
        context.onOutput?.(msg);
        return { success: true, message: msg, data: { model: context.model } };
      }
      const newModel = args[0];
      context.model = newModel;
      const msg = `Model changed to: ${newModel}`;
      context.onOutput?.(msg);
      return { success: true, message: msg, data: { model: newModel } };
    }
  },
  {
    name: 'tokens',
    aliases: ['t'],
    description: 'Show token count for current session',
    execute: async (_args, context) => {
      const count = context.tokenCount || 0;
      const msg = `Token count: ${count}`;
      context.onOutput?.(msg);
      return { success: true, message: msg, data: { tokens: count } };
    }
  },
  {
    name: 'plan',
    aliases: ['p'],
    description: 'Show or manage task plan',
    usage: '/plan [add|remove|clear] [task]',
    execute: async (args, context) => {
      const plans = context.settings?.plans || [];
      
      if (args.length === 0) {
        if (plans.length === 0) {
          context.onOutput?.('No plans set');
          return { success: true, message: 'No plans set' };
        }
        const msg = ['Current plan:', ...plans.map((p: string, i: number) => `  ${i + 1}. ${p}`)].join('\n');
        context.onOutput?.(msg);
        return { success: true, message: msg, data: { plans } };
      }

      const action = args[0];
      const task = args.slice(1).join(' ');

      if (action === 'add' && task) {
        plans.push(task);
        context.settings = { ...context.settings, plans };
        context.onOutput?.(`Added: ${task}`);
        return { success: true, message: `Added: ${task}` };
      }
      if (action === 'remove' && task) {
        const index = parseInt(task) - 1;
        if (index >= 0 && index < plans.length) {
          const removed = plans.splice(index, 1)[0];
          context.settings = { ...context.settings, plans };
          context.onOutput?.(`Removed: ${removed}`);
          return { success: true, message: `Removed: ${removed}` };
        }
      }
      if (action === 'clear') {
        context.settings = { ...context.settings, plans: [] };
        context.onOutput?.('Plans cleared');
        return { success: true, message: 'Plans cleared' };
      }

      return { success: false, message: 'Invalid plan command' };
    }
  },
  {
    name: 'undo',
    aliases: ['u'],
    description: 'Undo last action',
    execute: async (_args, context) => {
      if (context.history && context.history.length > 0) {
        const removed = context.history.pop();
        context.onOutput?.(`Undone: ${removed?.substring(0, 50)}...`);
        return { success: true, message: 'Last action undone' };
      }
      return { success: false, message: 'Nothing to undo' };
    }
  },
  {
    name: 'diff',
    aliases: ['d'],
    description: 'Show pending changes',
    execute: async (_args, context) => {
      const diff = context.settings?.pendingDiff || 'No pending changes';
      context.onOutput?.(diff);
      return { success: true, message: diff };
    }
  },
  {
    name: 'commit',
    description: 'Commit pending changes',
    execute: async (args, context) => {
      const message = args.join(' ') || 'Auto-commit';
      context.onOutput?.(`Committed with message: ${message}`);
      context.settings = { ...context.settings, pendingDiff: null };
      return { success: true, message: `Committed: ${message}` };
    }
  },
  {
    name: 'exit',
    aliases: ['quit', 'q'],
    description: 'Exit the session',
    execute: async (_args, context) => {
      context.onOutput?.('Goodbye!');
      return { success: true, message: 'Exiting', shouldExit: true };
    }
  },
  {
    name: 'settings',
    aliases: ['s'],
    description: 'Show or modify settings',
    usage: '/settings [key] [value]',
    execute: async (args, context) => {
      if (args.length === 0) {
        const settings = JSON.stringify(context.settings || {}, null, 2);
        context.onOutput?.(settings);
        return { success: true, message: settings, data: context.settings };
      }
      if (args.length === 1) {
        const value = context.settings?.[args[0]];
        const msg = `${args[0]}: ${JSON.stringify(value)}`;
        context.onOutput?.(msg);
        return { success: true, message: msg, data: { [args[0]]: value } };
      }
      const [key, ...valueParts] = args;
      let value: any = valueParts.join(' ');
      try {
        value = JSON.parse(value);
      } catch {
        // Keep as string
      }
      context.settings = { ...context.settings, [key]: value };
      context.onOutput?.(`Set ${key} = ${JSON.stringify(value)}`);
      return { success: true, message: `Set ${key}` };
    }
  },
  {
    name: 'map',
    description: 'Show repository map',
    execute: async (_args, context) => {
      const map = context.settings?.repoMap || 'Repository map not available. Run /map refresh to generate.';
      context.onOutput?.(map);
      return { success: true, message: map };
    }
  }
];

/**
 * Slash Command Registry
 */
class SlashCommandRegistry {
  private commands: Map<string, SlashCommand> = new Map();
  private aliases: Map<string, string> = new Map();

  constructor() {
    // Register built-in commands
    for (const cmd of BUILTIN_COMMANDS) {
      this.register(cmd);
    }
  }

  register(command: SlashCommand): void {
    this.commands.set(command.name, command);
    if (command.aliases) {
      for (const alias of command.aliases) {
        this.aliases.set(alias, command.name);
      }
    }
  }

  get(name: string): SlashCommand | undefined {
    const resolved = this.aliases.get(name) || name;
    return this.commands.get(resolved);
  }

  getAll(): SlashCommand[] {
    return Array.from(this.commands.values());
  }

  has(name: string): boolean {
    return this.commands.has(name) || this.aliases.has(name);
  }
}

let registry: SlashCommandRegistry | null = null;

export function getRegistry(): SlashCommandRegistry {
  if (!registry) {
    registry = new SlashCommandRegistry();
  }
  return registry;
}

export function registerCommand(command: SlashCommand): void {
  getRegistry().register(command);
}

/**
 * Parse slash command from input
 */
export function parseSlashCommand(input: string): { command: string; args: string[] } | null {
  const trimmed = input.trim();
  if (!trimmed.startsWith('/')) {
    return null;
  }

  const parts = trimmed.slice(1).split(/\s+/);
  const command = parts[0].toLowerCase();
  const args = parts.slice(1);

  return { command, args };
}

/**
 * Execute a slash command
 */
export async function executeSlashCommand(
  input: string,
  context: SlashCommandContext
): Promise<SlashCommandResult> {
  const parsed = parseSlashCommand(input);
  if (!parsed) {
    return { success: false, message: 'Not a slash command' };
  }

  const command = getRegistry().get(parsed.command);
  if (!command) {
    return { success: false, message: `Unknown command: /${parsed.command}` };
  }

  return command.execute(parsed.args, context);
}

/**
 * Check if input is a slash command
 */
export function isSlashCommand(input: string): boolean {
  return input.trim().startsWith('/');
}

/**
 * Slash Command Handler for CLI integration
 */
export class SlashCommandHandler {
  private context: SlashCommandContext;

  constructor(initialContext: Partial<SlashCommandContext> = {}) {
    this.context = {
      history: [],
      settings: {},
      ...initialContext
    };
  }

  async handle(input: string): Promise<SlashCommandResult> {
    return executeSlashCommand(input, this.context);
  }

  isCommand(input: string): boolean {
    return isSlashCommand(input);
  }

  getContext(): SlashCommandContext {
    return this.context;
  }

  updateContext(updates: Partial<SlashCommandContext>): void {
    this.context = { ...this.context, ...updates };
  }

  registerCommand(command: SlashCommand): void {
    registerCommand(command);
  }
}

export function createSlashCommandHandler(context?: Partial<SlashCommandContext>): SlashCommandHandler {
  return new SlashCommandHandler(context);
}
