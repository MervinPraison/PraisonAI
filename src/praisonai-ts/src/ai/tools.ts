/**
 * Tools - AI SDK Wrapper
 * 
 * Provides tool definition utilities compatible with AI SDK.
 */

export interface ToolDefinition<TInput = unknown, TOutput = unknown> {
  /** Tool description */
  description: string;
  /** Input parameters schema (Zod or JSON schema) */
  parameters: any;
  /** Execute function */
  execute: ToolExecuteFunction<TInput, TOutput>;
}

export type ToolExecuteFunction<TInput = unknown, TOutput = unknown> = (
  args: TInput,
  options?: ToolExecutionOptions
) => Promise<TOutput> | TOutput;

export interface ToolExecutionOptions {
  /** Tool call ID */
  toolCallId?: string;
  /** Abort signal */
  abortSignal?: AbortSignal;
  /** Messages context */
  messages?: any[];
}

export type ToolInput<T extends ToolDefinition> = T extends ToolDefinition<infer I, any> ? I : never;
export type ToolOutput<T extends ToolDefinition> = T extends ToolDefinition<any, infer O> ? O : never;

/**
 * Define a tool for use with AI SDK.
 * 
 * @example With Zod schema
 * ```typescript
 * import { z } from 'zod';
 * 
 * const weatherTool = defineTool({
 *   description: 'Get weather for a city',
 *   parameters: z.object({
 *     city: z.string().describe('City name'),
 *     unit: z.enum(['celsius', 'fahrenheit']).optional()
 *   }),
 *   execute: async ({ city, unit }) => {
 *     return { temperature: 20, unit: unit || 'celsius', city };
 *   }
 * });
 * ```
 * 
 * @example With JSON schema
 * ```typescript
 * const searchTool = defineTool({
 *   description: 'Search the web',
 *   parameters: {
 *     type: 'object',
 *     properties: {
 *       query: { type: 'string', description: 'Search query' }
 *     },
 *     required: ['query']
 *   },
 *   execute: async ({ query }) => {
 *     return { results: [`Result for: ${query}`] };
 *   }
 * });
 * ```
 */
export function defineTool<TInput = unknown, TOutput = unknown>(
  definition: ToolDefinition<TInput, TOutput>
): ToolDefinition<TInput, TOutput> {
  return definition;
}

/**
 * Create a tool set from multiple tool definitions.
 * 
 * @example
 * ```typescript
 * const tools = createToolSet({
 *   weather: weatherTool,
 *   search: searchTool
 * });
 * 
 * const result = await generateText({
 *   model: 'gpt-4o',
 *   prompt: 'What is the weather in Paris?',
 *   tools
 * });
 * ```
 */
export function createToolSet<T extends Record<string, ToolDefinition>>(
  tools: T
): T {
  return tools;
}

/**
 * Convert a simple function to a tool definition.
 * 
 * @example
 * ```typescript
 * const addTool = functionToTool(
 *   'add',
 *   'Add two numbers',
 *   z.object({ a: z.number(), b: z.number() }),
 *   ({ a, b }) => a + b
 * );
 * ```
 */
export function functionToTool<TInput = unknown, TOutput = unknown>(
  name: string,
  description: string,
  parameters: any,
  execute: ToolExecuteFunction<TInput, TOutput>
): ToolDefinition<TInput, TOutput> {
  return {
    description,
    parameters,
    execute,
  };
}
