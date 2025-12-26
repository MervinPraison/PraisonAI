/**
 * Sandbox Executor - Safe command execution with restrictions
 */

export type SandboxMode = 'disabled' | 'basic' | 'strict' | 'network-isolated';

export interface SandboxConfig {
  mode: SandboxMode;
  allowedCommands?: string[];
  blockedCommands?: string[];
  blockedPaths?: string[];
  timeout?: number;
  maxOutputSize?: number;
  cwd?: string;
  env?: Record<string, string>;
}

export interface ExecutionResult {
  success: boolean;
  stdout: string;
  stderr: string;
  exitCode: number;
  duration: number;
  truncated?: boolean;
}

/**
 * Default blocked commands (dangerous operations)
 */
export const DEFAULT_BLOCKED_COMMANDS = [
  'rm -rf /',
  'rm -rf /*',
  'rm -rf ~',
  'rm -rf ~/*',
  'mkfs',
  'dd if=/dev/zero',
  'dd if=/dev/random',
  ':(){ :|:& };:',
  'chmod -R 777 /',
  'chown -R',
  'sudo rm',
  'sudo dd',
  'sudo mkfs',
  'shutdown',
  'reboot',
  'halt',
  'poweroff',
  'init 0',
  'init 6'
];

/**
 * Default blocked paths
 */
export const DEFAULT_BLOCKED_PATHS = [
  '/etc/passwd',
  '/etc/shadow',
  '/etc/sudoers',
  '/root',
  '~/.ssh',
  '~/.gnupg',
  '~/.aws',
  '~/.config/gcloud',
  '/var/log',
  '/boot',
  '/sys',
  '/proc'
];

/**
 * Command validator
 */
export class CommandValidator {
  private blockedCommands: string[];
  private blockedPaths: string[];
  private allowedCommands?: string[];

  constructor(config: Partial<SandboxConfig> = {}) {
    this.blockedCommands = config.blockedCommands || DEFAULT_BLOCKED_COMMANDS;
    this.blockedPaths = config.blockedPaths || DEFAULT_BLOCKED_PATHS;
    this.allowedCommands = config.allowedCommands;
  }

  /**
   * Validate a command
   */
  validate(command: string): { valid: boolean; reason?: string } {
    const normalized = command.toLowerCase().trim();

    // Check allowlist first if specified
    if (this.allowedCommands) {
      const baseCmd = normalized.split(/\s+/)[0];
      if (!this.allowedCommands.includes(baseCmd)) {
        return { valid: false, reason: `Command '${baseCmd}' not in allowlist` };
      }
    }

    // Check blocked commands
    for (const blocked of this.blockedCommands) {
      if (normalized.includes(blocked.toLowerCase())) {
        return { valid: false, reason: `Blocked command pattern: ${blocked}` };
      }
    }

    // Check blocked paths
    for (const blockedPath of this.blockedPaths) {
      const expandedPath = blockedPath.replace('~', process.env.HOME || '');
      if (normalized.includes(expandedPath.toLowerCase())) {
        return { valid: false, reason: `Blocked path: ${blockedPath}` };
      }
    }

    // Check for shell injection patterns
    const dangerousPatterns = [
      /;\s*rm\s/i,
      /\|\s*rm\s/i,
      /`.*`/,
      /\$\(.*\)/,
      />\s*\/dev\/sd/i,
      />\s*\/dev\/null.*2>&1.*&/i
    ];

    for (const pattern of dangerousPatterns) {
      if (pattern.test(command)) {
        return { valid: false, reason: 'Potentially dangerous pattern detected' };
      }
    }

    return { valid: true };
  }
}

/**
 * Sandbox Executor class
 */
export class SandboxExecutor {
  private config: SandboxConfig;
  private validator: CommandValidator;

  constructor(config: Partial<SandboxConfig> = {}) {
    this.config = {
      mode: 'basic',
      timeout: 30000,
      maxOutputSize: 1024 * 1024, // 1MB
      cwd: process.cwd(),
      ...config
    };
    this.validator = new CommandValidator(this.config);
  }

  /**
   * Execute a command in the sandbox
   */
  async execute(command: string): Promise<ExecutionResult> {
    const startTime = Date.now();

    // Disabled mode - no execution
    if (this.config.mode === 'disabled') {
      return {
        success: false,
        stdout: '',
        stderr: 'Sandbox execution is disabled',
        exitCode: 1,
        duration: 0
      };
    }

    // Validate command
    const validation = this.validator.validate(command);
    if (!validation.valid) {
      return {
        success: false,
        stdout: '',
        stderr: `Command rejected: ${validation.reason}`,
        exitCode: 1,
        duration: 0
      };
    }

    try {
      const result = await this.spawn(command);
      return {
        ...result,
        duration: Date.now() - startTime
      };
    } catch (error: any) {
      return {
        success: false,
        stdout: '',
        stderr: error.message,
        exitCode: 1,
        duration: Date.now() - startTime
      };
    }
  }

  /**
   * Spawn the command
   */
  private async spawn(command: string): Promise<Omit<ExecutionResult, 'duration'>> {
    const { spawn } = await import('child_process');

    return new Promise((resolve) => {
      const env = this.buildEnv();
      
      const proc = spawn('sh', ['-c', command], {
        cwd: this.config.cwd,
        env,
        timeout: this.config.timeout,
        stdio: ['pipe', 'pipe', 'pipe']
      });

      let stdout = '';
      let stderr = '';
      let truncated = false;
      const maxSize = this.config.maxOutputSize || 1024 * 1024;

      proc.stdout?.on('data', (data) => {
        if (stdout.length < maxSize) {
          stdout += data.toString();
          if (stdout.length > maxSize) {
            stdout = stdout.slice(0, maxSize);
            truncated = true;
          }
        }
      });

      proc.stderr?.on('data', (data) => {
        if (stderr.length < maxSize) {
          stderr += data.toString();
          if (stderr.length > maxSize) {
            stderr = stderr.slice(0, maxSize);
            truncated = true;
          }
        }
      });

      proc.on('close', (code) => {
        resolve({
          success: code === 0,
          stdout,
          stderr,
          exitCode: code || 0,
          truncated
        });
      });

      proc.on('error', (error) => {
        resolve({
          success: false,
          stdout,
          stderr: error.message,
          exitCode: 1
        });
      });
    });
  }

  /**
   * Build environment variables based on sandbox mode
   */
  private buildEnv(): Record<string, string> {
    const baseEnv = { ...process.env, ...this.config.env };

    switch (this.config.mode) {
      case 'strict':
        // Minimal environment
        return {
          PATH: '/usr/local/bin:/usr/bin:/bin',
          HOME: process.env.HOME || '',
          USER: process.env.USER || '',
          SHELL: '/bin/sh',
          TERM: 'dumb',
          ...this.config.env
        };

      case 'network-isolated':
        // No network access (requires additional OS-level setup)
        return {
          ...baseEnv,
          http_proxy: 'http://localhost:0',
          https_proxy: 'http://localhost:0',
          HTTP_PROXY: 'http://localhost:0',
          HTTPS_PROXY: 'http://localhost:0',
          no_proxy: '',
          NO_PROXY: ''
        };

      case 'basic':
      default:
        return baseEnv as Record<string, string>;
    }
  }

  /**
   * Check if a command would be allowed
   */
  wouldAllow(command: string): { allowed: boolean; reason?: string } {
    if (this.config.mode === 'disabled') {
      return { allowed: false, reason: 'Sandbox execution is disabled' };
    }
    const validation = this.validator.validate(command);
    return { allowed: validation.valid, reason: validation.reason };
  }

  /**
   * Get current sandbox mode
   */
  getMode(): SandboxMode {
    return this.config.mode;
  }

  /**
   * Update sandbox mode
   */
  setMode(mode: SandboxMode): void {
    this.config.mode = mode;
  }
}

/**
 * Create a sandbox executor
 */
export function createSandboxExecutor(config?: Partial<SandboxConfig>): SandboxExecutor {
  return new SandboxExecutor(config);
}

/**
 * Quick execute with default sandbox
 */
export async function sandboxExec(command: string, config?: Partial<SandboxConfig>): Promise<ExecutionResult> {
  const executor = createSandboxExecutor(config);
  return executor.execute(command);
}
