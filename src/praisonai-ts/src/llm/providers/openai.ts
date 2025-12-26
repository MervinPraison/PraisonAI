/**
 * OpenAI Provider - Implementation for OpenAI API
 */

import OpenAI from 'openai';
import type { ChatCompletionMessageParam, ChatCompletionTool } from 'openai/resources/chat/completions';
import { BaseProvider } from './base';
import type {
  ProviderConfig,
  GenerateTextOptions,
  GenerateTextResult,
  StreamTextOptions,
  StreamChunk,
  GenerateObjectOptions,
  GenerateObjectResult,
  Message,
  ToolDefinition,
  ToolCall,
} from './types';

export class OpenAIProvider extends BaseProvider {
  readonly providerId = 'openai';
  private client: OpenAI;

  constructor(modelId: string, config: ProviderConfig = {}) {
    super(modelId, config);
    this.client = new OpenAI({
      apiKey: config.apiKey || process.env.OPENAI_API_KEY,
      baseURL: config.baseUrl,
      timeout: config.timeout || 60000,
      maxRetries: 0, // We handle retries ourselves
    });
  }

  async generateText(options: GenerateTextOptions): Promise<GenerateTextResult> {
    return this.withRetry(async () => {
      const response = await this.client.chat.completions.create({
        model: this.modelId,
        messages: this.formatMessages(options.messages),
        temperature: options.temperature ?? 0.7,
        max_tokens: options.maxTokens,
        tools: options.tools ? this.formatTools(options.tools) : undefined,
        tool_choice: options.toolChoice as any,
        stop: options.stop,
        top_p: options.topP,
        frequency_penalty: options.frequencyPenalty,
        presence_penalty: options.presencePenalty,
      });

      const choice = response.choices[0];
      const message = choice.message;

      return {
        text: message.content || '',
        toolCalls: message.tool_calls?.map(tc => ({
          id: tc.id,
          type: 'function' as const,
          function: {
            name: tc.function.name,
            arguments: tc.function.arguments,
          },
        })),
        usage: {
          promptTokens: response.usage?.prompt_tokens || 0,
          completionTokens: response.usage?.completion_tokens || 0,
          totalTokens: response.usage?.total_tokens || 0,
        },
        finishReason: this.mapFinishReason(choice.finish_reason),
        raw: response,
      };
    });
  }

  async streamText(options: StreamTextOptions): Promise<AsyncIterable<StreamChunk>> {
    const self = this;
    
    return {
      async *[Symbol.asyncIterator]() {
        const stream = await self.client.chat.completions.create({
          model: self.modelId,
          messages: self.formatMessages(options.messages),
          temperature: options.temperature ?? 0.7,
          max_tokens: options.maxTokens,
          tools: options.tools ? self.formatTools(options.tools) : undefined,
          tool_choice: options.toolChoice as any,
          stop: options.stop,
          stream: true,
        });

        let toolCalls: ToolCall[] = [];
        
        for await (const chunk of stream) {
          const delta = chunk.choices[0]?.delta;
          
          if (delta?.content) {
            if (options.onToken) {
              options.onToken(delta.content);
            }
            yield { text: delta.content };
          }
          
          if (delta?.tool_calls) {
            for (const tc of delta.tool_calls) {
              if (tc.index !== undefined) {
                if (!toolCalls[tc.index]) {
                  toolCalls[tc.index] = {
                    id: tc.id || '',
                    type: 'function',
                    function: { name: '', arguments: '' },
                  };
                }
                if (tc.id) toolCalls[tc.index].id = tc.id;
                if (tc.function?.name) toolCalls[tc.index].function.name = tc.function.name;
                if (tc.function?.arguments) toolCalls[tc.index].function.arguments += tc.function.arguments;
              }
            }
          }
          
          if (chunk.choices[0]?.finish_reason) {
            yield {
              finishReason: chunk.choices[0].finish_reason,
              toolCalls: toolCalls.length > 0 ? toolCalls : undefined,
              usage: chunk.usage ? {
                promptTokens: chunk.usage.prompt_tokens,
                completionTokens: chunk.usage.completion_tokens,
                totalTokens: chunk.usage.total_tokens,
              } : undefined,
            };
          }
        }
      },
    };
  }

  async generateObject<T = any>(options: GenerateObjectOptions<T>): Promise<GenerateObjectResult<T>> {
    return this.withRetry(async () => {
      const response = await this.client.chat.completions.create({
        model: this.modelId,
        messages: this.formatMessages(options.messages),
        temperature: options.temperature ?? 0.7,
        max_tokens: options.maxTokens,
        response_format: {
          type: 'json_schema',
          json_schema: {
            name: 'response',
            schema: this.normalizeSchema(options.schema),
            strict: true,
          },
        },
      });

      const choice = response.choices[0];
      const content = choice.message.content || '{}';
      
      let parsed: T;
      try {
        parsed = JSON.parse(content);
      } catch (e) {
        throw new Error(`Failed to parse JSON response: ${content}`);
      }

      return {
        object: parsed,
        usage: {
          promptTokens: response.usage?.prompt_tokens || 0,
          completionTokens: response.usage?.completion_tokens || 0,
          totalTokens: response.usage?.total_tokens || 0,
        },
        raw: response,
      };
    });
  }

  protected formatMessages(messages: Message[]): ChatCompletionMessageParam[] {
    return messages.map(msg => {
      if (msg.role === 'tool') {
        return {
          role: 'tool' as const,
          content: msg.content || '',
          tool_call_id: msg.tool_call_id || '',
        };
      }
      if (msg.role === 'assistant' && msg.tool_calls) {
        return {
          role: 'assistant' as const,
          content: msg.content,
          tool_calls: msg.tool_calls,
        };
      }
      return {
        role: msg.role as 'system' | 'user' | 'assistant',
        content: msg.content || '',
      };
    });
  }

  protected formatTools(tools: ToolDefinition[]): ChatCompletionTool[] {
    return tools.map(tool => ({
      type: 'function' as const,
      function: {
        name: tool.name,
        description: tool.description || `Function ${tool.name}`,
        parameters: tool.parameters || { type: 'object', properties: {} },
      },
    }));
  }

  private mapFinishReason(reason: string | null): GenerateTextResult['finishReason'] {
    switch (reason) {
      case 'stop': return 'stop';
      case 'length': return 'length';
      case 'tool_calls': return 'tool_calls';
      case 'content_filter': return 'content_filter';
      default: return 'stop';
    }
  }

  private normalizeSchema(schema: any): any {
    // If it's a Zod schema, convert to JSON schema
    if (schema && typeof schema.parse === 'function' && typeof schema._def === 'object') {
      // This is a Zod schema - we need zod-to-json-schema
      // For now, throw an error suggesting to use JSON schema directly
      throw new Error('Zod schemas require zod-to-json-schema. Please use JSON schema directly or install zod-to-json-schema.');
    }
    return schema;
  }
}
