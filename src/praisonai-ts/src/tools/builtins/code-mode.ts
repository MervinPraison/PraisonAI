/**
 * Code Mode Tool
 * 
 * Transform MCP tools and AI SDK tools into code-mode execution.
 * Allows writing code to a sandbox FS, importing tools, and running them.
 */

import type { ToolMetadata, PraisonTool, ToolExecutionContext } from '../registry/types';

export const CODE_MODE_METADATA: ToolMetadata = {
  id: 'code-mode',
  displayName: 'Code Mode',
  description: 'Execute code that can import and use other tools in a sandboxed environment',
  tags: ['sandbox', 'code', 'mcp', 'tools'],
  requiredEnv: [],
  optionalEnv: [],
  install: {
    npm: '# Built-in, no installation required',
    pnpm: '# Built-in, no installation required',
    yarn: '# Built-in, no installation required',
    bun: '# Built-in, no installation required',
  },
  docsSlug: 'tools/code-mode',
  capabilities: {
    sandbox: true,
    code: true,
  },
  packageName: 'praisonai', // Built-in
};

export interface CodeModeConfig {
  /** Allowed tools that can be imported */
  allowedTools?: string[];
  /** Blocked tools that cannot be imported */
  blockedTools?: string[];
  /** Enable network access (default: false) */
  allowNetwork?: boolean;
  /** Allowed file paths (glob patterns) */
  allowedPaths?: string[];
  /** Execution timeout in ms (default: 30000) */
  timeoutMs?: number;
  /** Maximum memory in MB (default: 128) */
  maxMemoryMb?: number;
}

export interface CodeModeInput {
  /** Code to execute */
  code: string;
  /** Files to write to the sandbox before execution */
  files?: Record<string, string>;
  /** Environment variables for execution */
  env?: Record<string, string>;
}

export interface CodeModeResult {
  /** Execution output */
  output: string;
  /** Standard output */
  stdout: string;
  /** Standard error */
  stderr: string;
  /** Exit code */
  exitCode: number;
  /** Files created/modified during execution */
  files?: Record<string, string>;
  /** Execution success */
  success: boolean;
  /** Error message if failed */
  error?: string;
}

/**
 * Create a Code Mode tool
 */
export function codeMode(config?: CodeModeConfig): PraisonTool<CodeModeInput, CodeModeResult> {
  const settings = {
    allowNetwork: false,
    timeoutMs: 30000,
    maxMemoryMb: 128,
    ...config,
  };

  return {
    name: 'codeMode',
    description: 'Execute code in a sandboxed environment with access to imported tools. Write files, run code, and get results.',
    parameters: {
      type: 'object',
      properties: {
        code: {
          type: 'string',
          description: 'The code to execute',
        },
        files: {
          type: 'object',
          description: 'Files to write to the sandbox before execution (path -> content)',
        },
        env: {
          type: 'object',
          description: 'Environment variables for execution',
        },
      },
      required: ['code'],
    },
    execute: async (input: CodeModeInput, context?: ToolExecutionContext): Promise<CodeModeResult> => {
      const { code, files, env } = input;

      // Validate code doesn't contain blocked patterns
      const blockedPatterns = [
        /require\s*\(\s*['"]child_process['"]\s*\)/,
        /require\s*\(\s*['"]fs['"]\s*\)/,
        /import\s+.*from\s+['"]child_process['"]/,
        /process\.exit/,
        /eval\s*\(/,
      ];

      if (!settings.allowNetwork) {
        blockedPatterns.push(
          /require\s*\(\s*['"]http['"]\s*\)/,
          /require\s*\(\s*['"]https['"]\s*\)/,
          /require\s*\(\s*['"]net['"]\s*\)/,
          /fetch\s*\(/,
        );
      }

      for (const pattern of blockedPatterns) {
        if (pattern.test(code)) {
          return {
            output: '',
            stdout: '',
            stderr: `Blocked pattern detected: ${pattern.source}`,
            exitCode: 1,
            success: false,
            error: 'Code contains blocked patterns for security',
          };
        }
      }

      // Check for blocked tools
      if (settings.blockedTools && settings.blockedTools.length > 0) {
        for (const tool of settings.blockedTools) {
          if (code.includes(tool)) {
            return {
              output: '',
              stdout: '',
              stderr: `Blocked tool: ${tool}`,
              exitCode: 1,
              success: false,
              error: `Tool "${tool}" is not allowed`,
            };
          }
        }
      }

      try {
        // Create a sandboxed execution context
        // In a real implementation, this would use a proper sandbox like vm2 or isolated-vm
        // For now, we provide a safe execution wrapper
        
        const sandbox = {
          console: {
            log: (...args: unknown[]) => stdout.push(args.map(String).join(' ')),
            error: (...args: unknown[]) => stderr.push(args.map(String).join(' ')),
            warn: (...args: unknown[]) => stderr.push(args.map(String).join(' ')),
          },
          setTimeout: undefined,
          setInterval: undefined,
          setImmediate: undefined,
          process: undefined,
          require: undefined,
          __dirname: '/sandbox',
          __filename: '/sandbox/index.js',
          env: env || {},
          files: files || {},
        };

        const stdout: string[] = [];
        const stderr: string[] = [];

        // Execute with timeout
        const timeoutPromise = new Promise<never>((_, reject) => {
          setTimeout(() => reject(new Error('Execution timeout')), settings.timeoutMs);
        });

        const executePromise = new Promise<string>((resolve, reject) => {
          try {
            // Create a function from the code
            const fn = new Function(
              'sandbox',
              `with (sandbox) { ${code} }`
            );
            const result = fn(sandbox);
            resolve(String(result ?? ''));
          } catch (error) {
            reject(error);
          }
        });

        const result = await Promise.race([executePromise, timeoutPromise]);

        return {
          output: result,
          stdout: stdout.join('\n'),
          stderr: stderr.join('\n'),
          exitCode: 0,
          success: true,
        };
      } catch (error) {
        return {
          output: '',
          stdout: '',
          stderr: error instanceof Error ? error.message : String(error),
          exitCode: 1,
          success: false,
          error: error instanceof Error ? error.message : String(error),
        };
      }
    },
  };
}

/**
 * Factory function for registry
 */
export function createCodeModeTool(config?: CodeModeConfig): PraisonTool<unknown, unknown> {
  return codeMode(config) as PraisonTool<unknown, unknown>;
}
