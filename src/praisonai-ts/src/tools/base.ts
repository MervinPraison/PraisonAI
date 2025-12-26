/**
 * BaseTool - Abstract base class for creating custom tools (plugins)
 * 
 * This provides the same extensibility pattern as Python's BaseTool.
 * External developers can create plugins by extending BaseTool.
 * 
 * Usage:
 *   import { BaseTool } from 'praisonai';
 * 
 *   class MyTool extends BaseTool {
 *     name = 'my_tool';
 *     description = 'Does something useful';
 *     
 *     async run(params: { query: string }): Promise<string> {
 *       return `Result for ${params.query}`;
 *     }
 *   }
 */

export interface ToolResult<T = any> {
  output: T;
  success: boolean;
  error?: string;
  metadata?: Record<string, any>;
}

export class ToolValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ToolValidationError';
  }
}

export interface ToolParameters {
  type: 'object';
  properties: Record<string, {
    type: string;
    description?: string;
    enum?: string[];
    default?: any;
  }>;
  required?: string[];
}

/**
 * Abstract base class for all PraisonAI tools.
 * 
 * Subclass this to create custom tools that can be:
 * - Used directly by agents
 * - Distributed as npm packages (plugins)
 * - Auto-discovered via package.json
 */
export abstract class BaseTool<TParams = any, TResult = any> {
  /** Unique identifier for the tool */
  abstract name: string;
  
  /** Human-readable description (used by LLM) */
  abstract description: string;
  
  /** Tool version string */
  version: string = '1.0.0';
  
  /** JSON Schema for parameters */
  parameters?: ToolParameters;

  /**
   * Execute the tool with given arguments.
   * This method must be implemented by subclasses.
   */
  abstract run(params: TParams): Promise<TResult> | TResult;

  /**
   * Allow tool to be called directly like a function.
   */
  async execute(params: TParams): Promise<TResult> {
    return this.run(params);
  }

  /**
   * Execute tool with error handling, returning ToolResult.
   */
  async safeRun(params: TParams): Promise<ToolResult<TResult>> {
    try {
      const output = await this.run(params);
      return { output, success: true };
    } catch (error: any) {
      return {
        output: null as any,
        success: false,
        error: error.message
      };
    }
  }

  /**
   * Get OpenAI-compatible function schema for this tool.
   */
  getSchema(): { type: 'function'; function: { name: string; description: string; parameters: any } } {
    return {
      type: 'function',
      function: {
        name: this.name,
        description: this.description,
        parameters: this.parameters || { type: 'object', properties: {}, required: [] }
      }
    };
  }

  /**
   * Validate the tool configuration.
   */
  validate(): boolean {
    const errors: string[] = [];

    if (!this.name || typeof this.name !== 'string') {
      errors.push("Tool must have a non-empty string 'name'");
    }

    if (!this.description || typeof this.description !== 'string') {
      errors.push("Tool must have a non-empty string 'description'");
    }

    if (errors.length > 0) {
      throw new ToolValidationError(`Tool '${this.name}' validation failed: ${errors.join('; ')}`);
    }

    return true;
  }

  toString(): string {
    return `${this.constructor.name}(name='${this.name}')`;
  }
}

/**
 * Validate any tool-like object.
 */
export function validateTool(tool: any): boolean {
  if (tool instanceof BaseTool) {
    return tool.validate();
  }

  if (typeof tool === 'function' || (tool && typeof tool.run === 'function')) {
    const name = tool.name || tool.__name__;
    if (!name) {
      throw new ToolValidationError('Tool must have a name');
    }
    return true;
  }

  throw new ToolValidationError(`Invalid tool type: ${typeof tool}`);
}

/**
 * Create a simple tool from a function (alternative to class-based approach)
 */
export function createTool<TParams = any, TResult = any>(config: {
  name: string;
  description: string;
  parameters?: ToolParameters;
  run: (params: TParams) => Promise<TResult> | TResult;
}): BaseTool<TParams, TResult> {
  return {
    name: config.name,
    description: config.description,
    version: '1.0.0',
    parameters: config.parameters,
    run: config.run,
    execute: async (params: TParams) => config.run(params),
    safeRun: async (params: TParams) => {
      try {
        const output = await config.run(params);
        return { output, success: true };
      } catch (error: any) {
        return { output: null as any, success: false, error: error.message };
      }
    },
    getSchema: () => ({
      type: 'function' as const,
      function: {
        name: config.name,
        description: config.description,
        parameters: config.parameters || { type: 'object', properties: {}, required: [] }
      }
    }),
    validate: () => true,
    toString: () => `Tool(name='${config.name}')`
  } as BaseTool<TParams, TResult>;
}
