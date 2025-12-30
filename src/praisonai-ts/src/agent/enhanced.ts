/**
 * Enhanced Agent - Agent with session management, provider abstraction, and tool support
 */

import { type LLMProvider, type Message, type ToolCall, type GenerateTextResult } from '../llm/providers';
import { resolveBackend } from '../llm/backend-resolver';
import { Session, Run, Trace, getSessionManager } from '../session';
import { FunctionTool, ToolRegistry, tool } from '../tools/decorator';
import { Logger } from '../utils/logger';

export interface EnhancedAgentConfig {
  name?: string;
  instructions: string;
  llm?: string;
  tools?: Array<FunctionTool | Function | { name: string; description?: string; parameters?: any; execute: Function }>;
  session?: Session;
  sessionId?: string;
  verbose?: boolean;
  stream?: boolean;
  maxToolCalls?: number;
  temperature?: number;
  maxTokens?: number;
  outputSchema?: any;
}

export interface ChatOptions {
  stream?: boolean;
  temperature?: number;
  maxTokens?: number;
  outputSchema?: any;
  onToken?: (token: string) => void;
}

export interface ChatResult {
  text: string;
  structured?: any;
  toolCalls?: ToolCall[];
  usage: {
    promptTokens: number;
    completionTokens: number;
    totalTokens: number;
  };
  runId: string;
  sessionId: string;
}

/**
 * Enhanced Agent with full feature support
 */
export class EnhancedAgent {
  readonly name: string;
  readonly instructions: string;
  readonly sessionId: string;
  
  private provider: LLMProvider | null = null;
  private providerPromise: Promise<LLMProvider> | null = null;
  private llmModel: string;
  private session: Session;
  private toolRegistry: ToolRegistry;
  private verbose: boolean;
  private stream: boolean;
  private maxToolCalls: number;
  private temperature: number;
  private maxTokens?: number;
  private outputSchema?: any;

  constructor(config: EnhancedAgentConfig) {
    this.name = config.name || `Agent_${Math.random().toString(36).substr(2, 9)}`;
    this.instructions = config.instructions;
    this.verbose = config.verbose ?? true;
    this.stream = config.stream ?? true;
    this.maxToolCalls = config.maxToolCalls ?? 10;
    this.temperature = config.temperature ?? 0.7;
    this.maxTokens = config.maxTokens;
    this.outputSchema = config.outputSchema;

    // Store model string for lazy provider initialization
    this.llmModel = config.llm || 'openai/gpt-4o-mini';

    // Initialize session
    if (config.session) {
      this.session = config.session;
    } else if (config.sessionId) {
      this.session = getSessionManager().getOrCreate(config.sessionId);
    } else {
      this.session = getSessionManager().create();
    }
    this.sessionId = this.session.id;

    // Initialize tool registry
    this.toolRegistry = new ToolRegistry();
    if (config.tools) {
      this.registerTools(config.tools);
    }

    Logger.setVerbose(this.verbose);
  }

  /**
   * Get the LLM provider (lazy initialization with AI SDK backend)
   */
  private async getProvider(): Promise<LLMProvider> {
    if (this.provider) {
      return this.provider;
    }

    if (!this.providerPromise) {
      this.providerPromise = (async () => {
        const result = await resolveBackend(this.llmModel, {
          attribution: {
            agentId: this.name,
            sessionId: this.sessionId,
          },
        });
        this.provider = result.provider;
        return result.provider;
      })();
    }

    return this.providerPromise;
  }

  private registerTools(tools: EnhancedAgentConfig['tools']): void {
    if (!tools) return;

    for (const t of tools) {
      if (t instanceof FunctionTool) {
        this.toolRegistry.register(t);
      } else if (typeof t === 'function') {
        // Convert function to tool
        const funcName = t.name || `function_${Math.random().toString(36).substr(2, 9)}`;
        this.toolRegistry.register(tool({
          name: funcName,
          description: `Function ${funcName}`,
          execute: t as any,
        }));
      } else if (typeof t === 'object' && 'execute' in t) {
        // Tool config object
        this.toolRegistry.register(tool({
          name: t.name,
          description: t.description,
          parameters: t.parameters,
          execute: t.execute as any,
        }));
      }
    }
  }

  /**
   * Add a tool to the agent
   */
  addTool(t: FunctionTool | { name: string; description?: string; parameters?: any; execute: Function }): this {
    if (t instanceof FunctionTool) {
      this.toolRegistry.register(t);
    } else {
      this.toolRegistry.register(tool({
        name: t.name,
        description: t.description,
        parameters: t.parameters,
        execute: t.execute as any,
      }));
    }
    return this;
  }

  /**
   * Get all registered tools
   */
  getTools(): FunctionTool[] {
    return this.toolRegistry.list();
  }

  /**
   * Chat with the agent
   */
  async chat(prompt: string, options: ChatOptions = {}): Promise<ChatResult> {
    const run = this.session.createRun().start();
    const trace = run.createTrace({ name: 'chat' }).start();

    try {
      // Add user message to session
      this.session.addMessage({ role: 'user', content: prompt });

      // Build messages array
      const messages: Message[] = [
        { role: 'system', content: this.instructions },
        ...this.session.getMessagesForLLM() as Message[],
      ];

      // Get tool definitions
      const tools = this.toolRegistry.list().length > 0
        ? this.toolRegistry.getDefinitions()
        : undefined;

      let result: GenerateTextResult;
      let fullText = '';
      let allToolCalls: ToolCall[] = [];
      let iterations = 0;

      // Tool calling loop
      while (iterations < this.maxToolCalls) {
        iterations++;

        if (options.stream && !tools && options.onToken) {
          // Streaming without tools
          const provider = await this.getProvider();
          const stream = await provider.streamText({
            messages,
            temperature: options.temperature ?? this.temperature,
            maxTokens: options.maxTokens ?? this.maxTokens,
            onToken: options.onToken,
          });

          let usage = { promptTokens: 0, completionTokens: 0, totalTokens: 0 };
          for await (const chunk of stream) {
            if (chunk.text) fullText += chunk.text;
            if (chunk.usage) usage = { ...usage, ...chunk.usage };
          }

          result = {
            text: fullText,
            usage,
            finishReason: 'stop',
          };
          break;
        } else if (options.outputSchema) {
          // Structured output
          const provider = await this.getProvider();
          const objResult = await provider.generateObject({
            messages,
            schema: options.outputSchema ?? this.outputSchema,
            temperature: options.temperature ?? this.temperature,
            maxTokens: options.maxTokens ?? this.maxTokens,
          });

          result = {
            text: JSON.stringify(objResult.object),
            usage: objResult.usage,
            finishReason: 'stop',
          };
          fullText = result.text;
          break;
        } else {
          // Regular generation with potential tool calls
          const provider = await this.getProvider();
          result = await provider.generateText({
            messages,
            temperature: options.temperature ?? this.temperature,
            maxTokens: options.maxTokens ?? this.maxTokens,
            tools,
          });

          if (result.toolCalls && result.toolCalls.length > 0) {
            allToolCalls.push(...result.toolCalls);

            // Add assistant message with tool calls
            messages.push({
              role: 'assistant',
              content: result.text || null,
              tool_calls: result.toolCalls,
            });

            // Execute tool calls
            for (const tc of result.toolCalls) {
              const toolTrace = trace.createChild({ name: `tool:${tc.function.name}` }).start();
              
              try {
                const toolFn = this.toolRegistry.get(tc.function.name);
                if (!toolFn) {
                  throw new Error(`Tool '${tc.function.name}' not found`);
                }

                const args = JSON.parse(tc.function.arguments);
                const toolResult = await toolFn.execute(args, {
                  agentName: this.name,
                  sessionId: this.sessionId,
                  runId: run.id,
                });

                const resultStr = typeof toolResult === 'string' 
                  ? toolResult 
                  : JSON.stringify(toolResult);

                messages.push({
                  role: 'tool',
                  content: resultStr,
                  tool_call_id: tc.id,
                });

                toolTrace.complete({ result: resultStr });
              } catch (error: any) {
                messages.push({
                  role: 'tool',
                  content: `Error: ${error.message}`,
                  tool_call_id: tc.id,
                });
                toolTrace.fail(error);
              }
            }

            // Continue loop to get final response
            continue;
          }

          // No tool calls, we have our final response
          fullText = result.text;
          break;
        }
      }

      // Add assistant message to session
      this.session.addMessage({
        role: 'assistant',
        content: fullText,
        tool_calls: allToolCalls.length > 0 ? allToolCalls : undefined,
      });

      trace.complete({ responseLength: fullText.length });
      run.complete();

      // Parse structured output if schema was provided
      let structured: any;
      if (options.outputSchema) {
        try {
          structured = JSON.parse(fullText);
        } catch {
          // Not valid JSON
        }
      }

      return {
        text: fullText,
        structured,
        toolCalls: allToolCalls.length > 0 ? allToolCalls : undefined,
        usage: result!.usage,
        runId: run.id,
        sessionId: this.sessionId,
      };
    } catch (error: any) {
      trace.fail(error);
      run.fail(error);
      throw error;
    }
  }

  /**
   * Start method for compatibility
   */
  async start(prompt: string, options?: ChatOptions): Promise<string> {
    const result = await this.chat(prompt, options);
    return result.text;
  }

  /**
   * Get the session
   */
  getSession(): Session {
    return this.session;
  }

  /**
   * Clear conversation history
   */
  clearHistory(): void {
    this.session.clearMessages();
  }
}
