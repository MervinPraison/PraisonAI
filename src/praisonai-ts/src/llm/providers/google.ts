/**
 * Google Provider - Implementation for Google Gemini API
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

interface GeminiContent {
  role: 'user' | 'model';
  parts: Array<{ text?: string; functionCall?: any; functionResponse?: any }>;
}

export class GoogleProvider extends BaseProvider {
  readonly providerId = 'google';
  private apiKey: string;
  private baseUrl: string;

  constructor(modelId: string, config: ProviderConfig = {}) {
    super(modelId, config);
    this.apiKey = config.apiKey || process.env.GOOGLE_API_KEY || '';
    this.baseUrl = config.baseUrl || 'https://generativelanguage.googleapis.com/v1beta';
    
    if (!this.apiKey) {
      throw new Error('GOOGLE_API_KEY is required');
    }
  }

  async generateText(options: GenerateTextOptions): Promise<GenerateTextResult> {
    return this.withRetry(async () => {
      const { systemInstruction, contents } = this.formatRequest(options.messages);
      
      const response = await fetch(
        `${this.baseUrl}/models/${this.modelId}:generateContent?key=${this.apiKey}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            systemInstruction: systemInstruction ? { parts: [{ text: systemInstruction }] } : undefined,
            contents,
            generationConfig: {
              temperature: options.temperature ?? 0.7,
              maxOutputTokens: options.maxTokens,
              topP: options.topP,
              stopSequences: options.stop,
            },
            tools: options.tools ? this.formatTools(options.tools) : undefined,
          }),
        }
      );

      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw Object.assign(new Error(error.error?.message || `Google API error: ${response.status}`), {
          status: response.status,
        });
      }

      const data = await response.json();
      const candidate = data.candidates?.[0];
      
      let text = '';
      const toolCalls: ToolCall[] = [];
      
      for (const part of candidate?.content?.parts || []) {
        if (part.text) {
          text += part.text;
        } else if (part.functionCall) {
          toolCalls.push({
            id: `call_${Math.random().toString(36).substr(2, 9)}`,
            type: 'function',
            function: {
              name: part.functionCall.name,
              arguments: JSON.stringify(part.functionCall.args || {}),
            },
          });
        }
      }

      return {
        text,
        toolCalls: toolCalls.length > 0 ? toolCalls : undefined,
        usage: {
          promptTokens: data.usageMetadata?.promptTokenCount || 0,
          completionTokens: data.usageMetadata?.candidatesTokenCount || 0,
          totalTokens: data.usageMetadata?.totalTokenCount || 0,
        },
        finishReason: this.mapFinishReason(candidate?.finishReason),
        raw: data,
      };
    });
  }

  async streamText(options: StreamTextOptions): Promise<AsyncIterable<StreamChunk>> {
    const self = this;
    const { systemInstruction, contents } = this.formatRequest(options.messages);
    
    return {
      async *[Symbol.asyncIterator]() {
        const response = await fetch(
          `${self.baseUrl}/models/${self.modelId}:streamGenerateContent?key=${self.apiKey}&alt=sse`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              systemInstruction: systemInstruction ? { parts: [{ text: systemInstruction }] } : undefined,
              contents,
              generationConfig: {
                temperature: options.temperature ?? 0.7,
                maxOutputTokens: options.maxTokens,
              },
              tools: options.tools ? self.formatTools(options.tools) : undefined,
            }),
          }
        );

        if (!response.ok) {
          const error = await response.json().catch(() => ({}));
          throw new Error(error.error?.message || `Google API error: ${response.status}`);
        }

        const reader = response.body?.getReader();
        if (!reader) throw new Error('No response body');

        const decoder = new TextDecoder();
        let buffer = '';
        const toolCalls: ToolCall[] = [];

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
              const candidate = event.candidates?.[0];
              
              for (const part of candidate?.content?.parts || []) {
                if (part.text) {
                  if (options.onToken) options.onToken(part.text);
                  yield { text: part.text };
                } else if (part.functionCall) {
                  toolCalls.push({
                    id: `call_${Math.random().toString(36).substr(2, 9)}`,
                    type: 'function',
                    function: {
                      name: part.functionCall.name,
                      arguments: JSON.stringify(part.functionCall.args || {}),
                    },
                  });
                }
              }
              
              if (candidate?.finishReason) {
                yield {
                  finishReason: self.mapFinishReason(candidate.finishReason),
                  toolCalls: toolCalls.length > 0 ? toolCalls : undefined,
                  usage: event.usageMetadata ? {
                    promptTokens: event.usageMetadata.promptTokenCount || 0,
                    completionTokens: event.usageMetadata.candidatesTokenCount || 0,
                    totalTokens: event.usageMetadata.totalTokenCount || 0,
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
    const { systemInstruction, contents } = this.formatRequest(options.messages);
    
    return this.withRetry(async () => {
      const response = await fetch(
        `${this.baseUrl}/models/${this.modelId}:generateContent?key=${this.apiKey}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            systemInstruction: systemInstruction 
              ? { parts: [{ text: `${systemInstruction}\n\nRespond with valid JSON matching this schema:\n${JSON.stringify(options.schema, null, 2)}` }] }
              : { parts: [{ text: `Respond with valid JSON matching this schema:\n${JSON.stringify(options.schema, null, 2)}` }] },
            contents,
            generationConfig: {
              temperature: options.temperature ?? 0.7,
              maxOutputTokens: options.maxTokens,
              responseMimeType: 'application/json',
            },
          }),
        }
      );

      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.error?.message || `Google API error: ${response.status}`);
      }

      const data = await response.json();
      const candidate = data.candidates?.[0];
      let text = '';
      
      for (const part of candidate?.content?.parts || []) {
        if (part.text) text += part.text;
      }

      let parsed: T;
      try {
        parsed = JSON.parse(text);
      } catch (e) {
        // Try to extract JSON from text
        const jsonMatch = text.match(/\{[\s\S]*\}/);
        if (!jsonMatch) throw new Error(`No JSON found: ${text}`);
        parsed = JSON.parse(jsonMatch[0]);
      }

      return {
        object: parsed,
        usage: {
          promptTokens: data.usageMetadata?.promptTokenCount || 0,
          completionTokens: data.usageMetadata?.candidatesTokenCount || 0,
          totalTokens: data.usageMetadata?.totalTokenCount || 0,
        },
        raw: data,
      };
    });
  }

  private formatRequest(messages: Message[]): { systemInstruction: string | null; contents: GeminiContent[] } {
    const systemMessages = messages.filter(m => m.role === 'system');
    const otherMessages = messages.filter(m => m.role !== 'system');
    const systemInstruction = systemMessages.length > 0 
      ? systemMessages.map(m => m.content).join('\n')
      : null;
    
    return {
      systemInstruction,
      contents: this.formatMessages(otherMessages),
    };
  }

  protected formatMessages(messages: Message[]): GeminiContent[] {
    const result: GeminiContent[] = [];
    
    for (const msg of messages) {
      if (msg.role === 'system') continue;
      
      const role = msg.role === 'assistant' ? 'model' : 'user';
      
      if (msg.role === 'tool') {
        result.push({
          role: 'user',
          parts: [{
            functionResponse: {
              name: msg.name || 'function',
              response: { result: msg.content },
            },
          }],
        });
      } else if (msg.role === 'assistant' && msg.tool_calls) {
        const parts: any[] = [];
        if (msg.content) parts.push({ text: msg.content });
        for (const tc of msg.tool_calls) {
          parts.push({
            functionCall: {
              name: tc.function.name,
              args: JSON.parse(tc.function.arguments),
            },
          });
        }
        result.push({ role: 'model', parts });
      } else {
        result.push({
          role,
          parts: [{ text: msg.content || '' }],
        });
      }
    }
    
    return result;
  }

  protected formatTools(tools: ToolDefinition[]): any[] {
    return [{
      functionDeclarations: tools.map(tool => ({
        name: tool.name,
        description: tool.description || `Function ${tool.name}`,
        parameters: tool.parameters || { type: 'object', properties: {} },
      })),
    }];
  }

  private mapFinishReason(reason: string | null): GenerateTextResult['finishReason'] {
    switch (reason) {
      case 'STOP': return 'stop';
      case 'MAX_TOKENS': return 'length';
      case 'SAFETY': return 'content_filter';
      default: return 'stop';
    }
  }
}
