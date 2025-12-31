/**
 * Code Execution Tool (Vercel Sandbox)
 * 
 * Execute Python code in a sandboxed Vercel environment.
 * Package: ai-sdk-tool-code-execution
 */

import type { ToolMetadata, PraisonTool, ToolExecutionContext } from '../registry/types';
import { MissingDependencyError, MissingEnvVarError } from '../registry/types';

export const CODE_EXECUTION_METADATA: ToolMetadata = {
  id: 'code-execution',
  displayName: 'Code Execution (Vercel Sandbox)',
  description: 'Execute Python code in a secure Vercel Sandbox environment',
  tags: ['sandbox', 'code', 'python', 'execution'],
  requiredEnv: [], // VERCEL_OIDC_TOKEN is auto-provided in Vercel, or use alternative auth
  optionalEnv: ['VERCEL_OIDC_TOKEN', 'VERCEL_TOKEN', 'VERCEL_TEAM_ID', 'VERCEL_PROJECT_ID'],
  install: {
    npm: 'npm install ai-sdk-tool-code-execution',
    pnpm: 'pnpm add ai-sdk-tool-code-execution',
    yarn: 'yarn add ai-sdk-tool-code-execution',
    bun: 'bun add ai-sdk-tool-code-execution',
  },
  docsSlug: 'tools/code-execution',
  capabilities: {
    sandbox: true,
    code: true,
  },
  packageName: 'ai-sdk-tool-code-execution',
};

export interface CodeExecutionConfig {
  /** Enable debug logging */
  debug?: boolean;
  /** Execution timeout in ms */
  timeoutMs?: number;
}

export interface CodeExecutionInput {
  /** Python code to execute */
  code: string;
}

export interface CodeExecutionOutput {
  /** Execution result/output */
  result: string;
  /** Standard output */
  stdout?: string;
  /** Standard error */
  stderr?: string;
  /** Execution success */
  success: boolean;
}

/**
 * Create a Code Execution tool instance
 */
export function codeExecution(config?: CodeExecutionConfig): PraisonTool<CodeExecutionInput, CodeExecutionOutput> {
  // Lazy load the package
  let executeCodeFn: ((options?: { debug?: boolean }) => unknown) | null = null;

  const loadPackage = async () => {
    if (executeCodeFn) return executeCodeFn;

    try {
      // @ts-ignore - Optional dependency
      const pkg = await import('ai-sdk-tool-code-execution');
      executeCodeFn = pkg.executeCode;
      return executeCodeFn;
    } catch (error) {
      throw new MissingDependencyError(
        CODE_EXECUTION_METADATA.id,
        CODE_EXECUTION_METADATA.packageName,
        CODE_EXECUTION_METADATA.install,
        CODE_EXECUTION_METADATA.requiredEnv,
        CODE_EXECUTION_METADATA.docsSlug
      );
    }
  };

  return {
    name: 'executeCode',
    description: 'Execute Python code in a secure sandbox environment. Use this for calculations, data processing, and computational tasks.',
    parameters: {
      type: 'object',
      properties: {
        code: {
          type: 'string',
          description: 'Python code to execute',
        },
      },
      required: ['code'],
    },
    execute: async (input: CodeExecutionInput, context?: ToolExecutionContext): Promise<CodeExecutionOutput> => {
      const executeCode = await loadPackage();
      
      // The AI SDK tool returns a tool definition, not a direct executor
      // We need to use it with the AI SDK's generateText
      // For direct execution, we'll create a wrapper
      try {
        // Create the tool with config
        const tool = (executeCode as Function)({ debug: config?.debug });
        
        // The tool is meant to be used with AI SDK's generateText
        // For standalone use, we execute it directly if possible
        if (tool && typeof tool.execute === 'function') {
          const result = await tool.execute(input);
          return {
            result: String(result),
            success: true,
          };
        }

        // If the tool doesn't have a direct execute, return info about usage
        return {
          result: 'Code execution tool created. Use with AI SDK generateText for full functionality.',
          success: true,
        };
      } catch (error) {
        return {
          result: '',
          stderr: error instanceof Error ? error.message : String(error),
          success: false,
        };
      }
    },
  };
}

/**
 * Factory function for registry
 */
export function createCodeExecutionTool(config?: CodeExecutionConfig): PraisonTool<unknown, unknown> {
  return codeExecution(config) as PraisonTool<unknown, unknown>;
}
