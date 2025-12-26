/**
 * Anthropic Provider - Implementation for Anthropic Claude API
 */

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

interface AnthropicMessage {
  role: 'user' | 'assistant';
  content: string | Array<{ type: string; text?: string; tool_use_id?: string; content?: string }>;
}

interface AnthropicTool {
  name: string;
  description: string;
  input_schema: Record<string, any>;
}

export class AnthropicProvider extends BaseProvider {
  readonly providerId = 'anthropic';
  private apiKey: string;
  private baseUrl: string;

  constructor(modelId: string, config: ProviderConfig = {}) {
    super(modelId, config);
    this.apiKey = config.apiKey || process.env.ANTHROPIC_API_KEY || '';
    this.baseUrl = config.baseUrl || 'https://api.anthropic.com';
    
    if (!this.apiKey) {
      throw new Error('ANTHROPIC_API_KEY is required');
    }
  }

  async generateText(options: GenerateTextOptions): Promise<GenerateTextResult> {
    return this.withRetry(async () => {
      const { systemPrompt, messages } = this.extractSystemPrompt(options.messages);
      
      const response = await fetch(`${this.baseUrl}/v1/messages`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': this.apiKey,
          'anthropic-version': '2023-06-01',
        },
        body: JSON.stringify({
          model: this.modelId,
          max_tokens: options.maxTokens || 4096,
          system: systemPrompt,
          messages: this.formatMessages(messages),
          temperature: options.temperature ?? 0.7,
          tools: options.tools ? this.formatTools(options.tools) : undefined,
          stop_sequences: options.stop,
          top_p: options.topP,
        }),
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw Object.assign(new Error(error.error?.message || `Anthropic API error: ${response.status}`), {
          status: response.status,
        });
      }

      const data = await response.json();
      
      let text = '';
      const toolCalls: ToolCall[] = [];
      
      for (const block of data.content || []) {
        if (block.type === 'text') {
          text += block.text;
        } else if (block.type === 'tool_use') {
          toolCalls.push({
            id: block.id,
            type: 'function',
            function: {
              name: block.name,
              arguments: JSON.stringify(block.input),
            },
          });
        }
      }

      return {
        text,
        toolCalls: toolCalls.length > 0 ? toolCalls : undefined,
        usage: {
          promptTokens: data.usage?.input_tokens || 0,
          completionTokens: data.usage?.output_tokens || 0,
          totalTokens: (data.usage?.input_tokens || 0) + (data.usage?.output_tokens || 0),
        },
        finishReason: this.mapStopReason(data.stop_reason),
        raw: data,
      };
    });
  }

  async streamText(options: StreamTextOptions): Promise<AsyncIterable<StreamChunk>> {
    const self = this;
    const { systemPrompt, messages } = this.extractSystemPrompt(options.messages);
    
    return {
      async *[Symbol.asyncIterator]() {
        const response = await fetch(`${self.baseUrl}/v1/messages`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'x-api-key': self.apiKey,
            'anthropic-version': '2023-06-01',
          },
          body: JSON.stringify({
            model: self.modelId,
            max_tokens: options.maxTokens || 4096,
            system: systemPrompt,
            messages: self.formatMessages(messages),
            temperature: options.temperature ?? 0.7,
            tools: options.tools ? self.formatTools(options.tools) : undefined,
            stream: true,
          }),
        });

        if (!response.ok) {
          const error = await response.json().catch(() => ({}));
          throw new Error(error.error?.message || `Anthropic API error: ${response.status}`);
        }

        const reader = response.body?.getReader();
        if (!reader) throw new Error('No response body');

        const decoder = new TextDecoder();
        let buffer = '';
        const toolCalls: ToolCall[] = [];
        let currentToolCall: Partial<ToolCall> | null = null;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            const data = line.slice(6);
            if (data === '[DONE]') continue;

            try {
              const event = JSON.parse(data);
              
              if (event.type === 'content_block_delta') {
                if (event.delta?.type === 'text_delta') {
                  const text = event.delta.text;
                  if (options.onToken) options.onToken(text);
                  yield { text };
                } else if (event.delta?.type === 'input_json_delta') {
                  if (currentToolCall) {
                    currentToolCall.function!.arguments += event.delta.partial_json;
                  }
                }
              } else if (event.type === 'content_block_start') {
                if (event.content_block?.type === 'tool_use') {
                  currentToolCall = {
                    id: event.content_block.id,
                    type: 'function',
                    function: {
                      name: event.content_block.name,
                      arguments: '',
                    },
                  };
                }
              } else if (event.type === 'content_block_stop') {
                if (currentToolCall) {
                  toolCalls.push(currentToolCall as ToolCall);
                  currentToolCall = null;
                }
              } else if (event.type === 'message_delta') {
                yield {
                  finishReason: self.mapStopReason(event.delta?.stop_reason),
                  toolCalls: toolCalls.length > 0 ? toolCalls : undefined,
                  usage: event.usage ? {
                    promptTokens: 0,
                    completionTokens: event.usage.output_tokens,
                    totalTokens: event.usage.output_tokens,
                  } : undefined,
                };
              }
            } catch (e) {
              // Skip malformed JSON
            }
          }
        }
      },
    };
  }

  async generateObject<T = any>(options: GenerateObjectOptions<T>): Promise<GenerateObjectResult<T>> {
    const { systemPrompt, messages } = this.extractSystemPrompt(options.messages);
    
    // Add JSON instruction to system prompt
    const jsonSystemPrompt = `${systemPrompt}\n\nYou must respond with valid JSON matching this schema:\n${JSON.stringify(options.schema, null, 2)}`;
    
    return this.withRetry(async () => {
      const response = await fetch(`${this.baseUrl}/v1/messages`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': this.apiKey,
          'anthropic-version': '2023-06-01',
        },
        body: JSON.stringify({
          model: this.modelId,
          max_tokens: options.maxTokens || 4096,
          system: jsonSystemPrompt,
          messages: this.formatMessages(messages),
          temperature: options.temperature ?? 0.7,
        }),
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.error?.message || `Anthropic API error: ${response.status}`);
      }

      const data = await response.json();
      let text = '';
      
      for (const block of data.content || []) {
        if (block.type === 'text') {
          text += block.text;
        }
      }

      // Extract JSON from response
      const jsonMatch = text.match(/\{[\s\S]*\}/);
      if (!jsonMatch) {
        throw new Error(`No JSON found in response: ${text}`);
      }

      let parsed: T;
      try {
        parsed = JSON.parse(jsonMatch[0]);
      } catch (e) {
        throw new Error(`Failed to parse JSON: ${jsonMatch[0]}`);
      }

      return {
        object: parsed,
        usage: {
          promptTokens: data.usage?.input_tokens || 0,
          completionTokens: data.usage?.output_tokens || 0,
          totalTokens: (data.usage?.input_tokens || 0) + (data.usage?.output_tokens || 0),
        },
        raw: data,
      };
    });
  }

  private extractSystemPrompt(messages: Message[]): { systemPrompt: string; messages: Message[] } {
    const systemMessages = messages.filter(m => m.role === 'system');
    const otherMessages = messages.filter(m => m.role !== 'system');
    const systemPrompt = systemMessages.map(m => m.content).join('\n');
    return { systemPrompt, messages: otherMessages };
  }

  protected formatMessages(messages: Message[]): AnthropicMessage[] {
    const result: AnthropicMessage[] = [];
    
    for (const msg of messages) {
      if (msg.role === 'system') continue; // Handled separately
      
      if (msg.role === 'tool') {
        // Tool results need to be part of user message in Anthropic
        result.push({
          role: 'user',
          content: [{
            type: 'tool_result',
            tool_use_id: msg.tool_call_id || '',
            content: msg.content || '',
          }],
        });
      } else if (msg.role === 'assistant' && msg.tool_calls) {
        const content: any[] = [];
        if (msg.content) {
          content.push({ type: 'text', text: msg.content });
        }
        for (const tc of msg.tool_calls) {
          content.push({
            type: 'tool_use',
            id: tc.id,
            name: tc.function.name,
            input: JSON.parse(tc.function.arguments),
          });
        }
        result.push({ role: 'assistant', content });
      } else {
        result.push({
          role: msg.role as 'user' | 'assistant',
          content: msg.content || '',
        });
      }
    }
    
    return result;
  }

  protected formatTools(tools: ToolDefinition[]): AnthropicTool[] {
    return tools.map(tool => ({
      name: tool.name,
      description: tool.description || `Function ${tool.name}`,
      input_schema: tool.parameters || { type: 'object', properties: {} },
    }));
  }

  private mapStopReason(reason: string | null): GenerateTextResult['finishReason'] {
    switch (reason) {
      case 'end_turn': return 'stop';
      case 'max_tokens': return 'length';
      case 'tool_use': return 'tool_calls';
      default: return 'stop';
    }
  }
}
