/**
 * External Agents - Integration adapters for external AI CLI tools
 */

export interface ExternalAgentConfig {
  name: string;
  command: string;
  args?: string[];
  cwd?: string;
  env?: Record<string, string>;
  timeout?: number;
}

export interface ExternalAgentResult {
  success: boolean;
  output: string;
  error?: string;
  exitCode: number;
  duration: number;
}

/**
 * Base class for external agent integrations
 */
export abstract class BaseExternalAgent {
  protected config: ExternalAgentConfig;

  constructor(config: ExternalAgentConfig) {
    this.config = {
      timeout: 300000, // 5 minutes default
      ...config
    };
  }

  /**
   * Check if the external tool is available
   */
  abstract isAvailable(): Promise<boolean>;

  /**
   * Execute a prompt with the external agent
   */
  abstract execute(prompt: string): Promise<ExternalAgentResult>;

  /**
   * Get the agent name
   */
  getName(): string {
    return this.config.name;
  }

  /**
   * Execute a command and return result
   */
  protected async runCommand(args: string[]): Promise<ExternalAgentResult> {
    const { spawn } = await import('child_process');
    const startTime = Date.now();

    return new Promise((resolve) => {
      const proc = spawn(this.config.command, args, {
        cwd: this.config.cwd || process.cwd(),
        env: { ...process.env, ...this.config.env },
        timeout: this.config.timeout,
        stdio: ['pipe', 'pipe', 'pipe']
      });

      let stdout = '';
      let stderr = '';

      proc.stdout?.on('data', (data) => {
        stdout += data.toString();
      });

      proc.stderr?.on('data', (data) => {
        stderr += data.toString();
      });

      proc.on('close', (code) => {
        resolve({
          success: code === 0,
          output: stdout,
          error: stderr || undefined,
          exitCode: code || 0,
          duration: Date.now() - startTime
        });
      });

      proc.on('error', (error) => {
        resolve({
          success: false,
          output: '',
          error: error.message,
          exitCode: 1,
          duration: Date.now() - startTime
        });
      });
    });
  }

  /**
   * Check if a command exists
   */
  protected async commandExists(command: string): Promise<boolean> {
    const { spawn } = await import('child_process');
    
    return new Promise((resolve) => {
      const proc = spawn('which', [command], { stdio: 'pipe' });
      proc.on('close', (code) => resolve(code === 0));
      proc.on('error', () => resolve(false));
    });
  }
}

/**
 * Claude Code CLI integration
 */
export class ClaudeCodeAgent extends BaseExternalAgent {
  constructor(cwd?: string) {
    super({
      name: 'claude-code',
      command: 'claude',
      cwd
    });
  }

  async isAvailable(): Promise<boolean> {
    return this.commandExists('claude');
  }

  async execute(prompt: string): Promise<ExternalAgentResult> {
    return this.runCommand(['--print', prompt]);
  }

  async executeWithSession(prompt: string, sessionId?: string): Promise<ExternalAgentResult> {
    const args = ['--print'];
    if (sessionId) {
      args.push('--continue', sessionId);
    }
    args.push(prompt);
    return this.runCommand(args);
  }
}

/**
 * Gemini CLI integration
 */
export class GeminiCliAgent extends BaseExternalAgent {
  private model: string;

  constructor(cwd?: string, model: string = 'gemini-2.5-pro') {
    super({
      name: 'gemini-cli',
      command: 'gemini',
      cwd
    });
    this.model = model;
  }

  async isAvailable(): Promise<boolean> {
    return this.commandExists('gemini');
  }

  async execute(prompt: string): Promise<ExternalAgentResult> {
    return this.runCommand(['-m', this.model, prompt]);
  }
}

/**
 * OpenAI Codex CLI integration
 */
export class CodexCliAgent extends BaseExternalAgent {
  constructor(cwd?: string) {
    super({
      name: 'codex-cli',
      command: 'codex',
      cwd
    });
  }

  async isAvailable(): Promise<boolean> {
    return this.commandExists('codex');
  }

  async execute(prompt: string): Promise<ExternalAgentResult> {
    return this.runCommand(['exec', '--full-auto', prompt]);
  }
}

/**
 * Aider CLI integration
 */
export class AiderAgent extends BaseExternalAgent {
  constructor(cwd?: string) {
    super({
      name: 'aider',
      command: 'aider',
      cwd
    });
  }

  async isAvailable(): Promise<boolean> {
    return this.commandExists('aider');
  }

  async execute(prompt: string): Promise<ExternalAgentResult> {
    return this.runCommand(['--message', prompt, '--yes']);
  }
}

/**
 * Generic external agent for any CLI tool
 */
export class GenericExternalAgent extends BaseExternalAgent {
  private promptArg: string;

  constructor(config: ExternalAgentConfig & { promptArg?: string }) {
    super(config);
    this.promptArg = config.promptArg || '';
  }

  async isAvailable(): Promise<boolean> {
    return this.commandExists(this.config.command);
  }

  async execute(prompt: string): Promise<ExternalAgentResult> {
    const args = [...(this.config.args || [])];
    if (this.promptArg) {
      args.push(this.promptArg, prompt);
    } else {
      args.push(prompt);
    }
    return this.runCommand(args);
  }
}

/**
 * External Agent Registry
 */
class ExternalAgentRegistry {
  private agents: Map<string, () => BaseExternalAgent> = new Map();

  constructor() {
    // Register built-in agents
    this.register('claude', () => new ClaudeCodeAgent());
    this.register('gemini', () => new GeminiCliAgent());
    this.register('codex', () => new CodexCliAgent());
    this.register('aider', () => new AiderAgent());
  }

  register(name: string, factory: () => BaseExternalAgent): void {
    this.agents.set(name, factory);
  }

  get(name: string): BaseExternalAgent | undefined {
    const factory = this.agents.get(name);
    return factory ? factory() : undefined;
  }

  list(): string[] {
    return Array.from(this.agents.keys());
  }

  async getAvailable(): Promise<string[]> {
    const available: string[] = [];
    for (const [name, factory] of this.agents) {
      const agent = factory();
      if (await agent.isAvailable()) {
        available.push(name);
      }
    }
    return available;
  }
}

let registry: ExternalAgentRegistry | null = null;

export function getExternalAgentRegistry(): ExternalAgentRegistry {
  if (!registry) {
    registry = new ExternalAgentRegistry();
  }
  return registry;
}

/**
 * Create an external agent by name
 */
export function createExternalAgent(name: string, cwd?: string): BaseExternalAgent | undefined {
  const reg = getExternalAgentRegistry();
  
  switch (name) {
    case 'claude':
      return new ClaudeCodeAgent(cwd);
    case 'gemini':
      return new GeminiCliAgent(cwd);
    case 'codex':
      return new CodexCliAgent(cwd);
    case 'aider':
      return new AiderAgent(cwd);
    default:
      return reg.get(name);
  }
}

/**
 * Convert external agent to tool for use with PraisonAI agents
 */
export function externalAgentAsTool(agent: BaseExternalAgent): {
  name: string;
  description: string;
  execute: (input: string) => Promise<string>;
} {
  return {
    name: `external_${agent.getName()}`,
    description: `Execute a prompt using the ${agent.getName()} external agent`,
    execute: async (input: string) => {
      const result = await agent.execute(input);
      if (!result.success) {
        throw new Error(result.error || 'External agent execution failed');
      }
      return result.output;
    }
  };
}
