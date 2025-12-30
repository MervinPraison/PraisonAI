/**
 * Custom Provider Registry Example
 * 
 * This example demonstrates how to register and use custom LLM providers
 * with the PraisonAI TypeScript SDK.
 */

import {
  registerProvider,
  createProvider,
  BaseProvider,
  listProviders,
  hasProvider,
  type ProviderConfig,
  type GenerateTextOptions,
  type GenerateTextResult,
  type StreamTextOptions,
  type StreamChunk,
  type GenerateObjectOptions,
  type GenerateObjectResult,
  type Message,
  type ToolDefinition
} from 'praisonai';

// Example 1: Simple Custom Provider
// ---------------------------------
// A minimal custom provider that wraps a hypothetical API

class SimpleCustomProvider extends BaseProvider {
  readonly providerId = 'simple-custom';
  private apiEndpoint: string;

  constructor(modelId: string, config?: ProviderConfig) {
    super(modelId, config);
    this.apiEndpoint = (config as any)?.apiEndpoint || 'https://api.example.com';
  }

  async generateText(options: GenerateTextOptions): Promise<GenerateTextResult> {
    // In a real implementation, you would call your API here
    console.log(`[SimpleCustomProvider] Generating text with model: ${this.modelId}`);
    console.log(`[SimpleCustomProvider] Messages:`, options.messages);
    
    // Simulated response
    return {
      text: `Response from ${this.providerId}/${this.modelId}: Hello! This is a simulated response.`,
      usage: {
        promptTokens: 10,
        completionTokens: 20,
        totalTokens: 30
      }
    };
  }

  async *streamText(options: StreamTextOptions): AsyncGenerator<StreamChunk> {
    const words = ['Hello', 'from', 'streaming', 'response!'];
    for (const word of words) {
      yield { text: word + ' ', done: false };
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    yield { text: '', done: true };
  }

  async generateObject<T>(options: GenerateObjectOptions<T>): Promise<GenerateObjectResult<T>> {
    // Simulated structured output
    return {
      object: { message: 'Structured response' } as T,
      usage: {
        promptTokens: 10,
        completionTokens: 20,
        totalTokens: 30
      }
    };
  }

  formatTools(tools: ToolDefinition[]): any[] {
    return tools;
  }

  formatMessages(messages: Message[]): any[] {
    return messages;
  }
}

// Example 2: Ollama Provider
// --------------------------
// A more realistic example for local Ollama integration

class OllamaProvider extends BaseProvider {
  readonly providerId = 'ollama';
  private baseUrl: string;

  constructor(modelId: string, config?: ProviderConfig) {
    super(modelId, config);
    this.baseUrl = (config as any)?.baseUrl || 'http://localhost:11434';
  }

  async generateText(options: GenerateTextOptions): Promise<GenerateTextResult> {
    const response = await fetch(`${this.baseUrl}/api/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: this.modelId,
        prompt: options.messages.map(m => `${m.role}: ${m.content}`).join('\n'),
        stream: false
      })
    });

    if (!response.ok) {
      throw new Error(`Ollama API error: ${response.statusText}`);
    }

    const data = await response.json();
    return {
      text: data.response,
      usage: {
        promptTokens: data.prompt_eval_count || 0,
        completionTokens: data.eval_count || 0,
        totalTokens: (data.prompt_eval_count || 0) + (data.eval_count || 0)
      }
    };
  }

  async *streamText(options: StreamTextOptions): AsyncGenerator<StreamChunk> {
    const response = await fetch(`${this.baseUrl}/api/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: this.modelId,
        prompt: options.messages.map(m => `${m.role}: ${m.content}`).join('\n'),
        stream: true
      })
    });

    if (!response.ok) {
      throw new Error(`Ollama API error: ${response.statusText}`);
    }

    const reader = response.body?.getReader();
    if (!reader) throw new Error('No response body');

    const decoder = new TextDecoder();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      
      const chunk = decoder.decode(value);
      const lines = chunk.split('\n').filter(line => line.trim());
      
      for (const line of lines) {
        try {
          const data = JSON.parse(line);
          yield { text: data.response || '', done: data.done || false };
        } catch {
          // Skip invalid JSON
        }
      }
    }
  }

  async generateObject<T>(options: GenerateObjectOptions<T>): Promise<GenerateObjectResult<T>> {
    const result = await this.generateText({
      messages: [
        ...options.messages,
        { role: 'system', content: `Respond with valid JSON matching this schema: ${JSON.stringify(options.schema)}` }
      ]
    });

    return {
      object: JSON.parse(result.text) as T,
      usage: result.usage
    };
  }

  formatTools(tools: ToolDefinition[]): any[] {
    return tools;
  }

  formatMessages(messages: Message[]): any[] {
    return messages;
  }
}

// Main Example
// ------------

async function main() {
  console.log('=== Provider Registry Example ===\n');

  // Check initial providers
  console.log('Initial providers:', listProviders());
  console.log('Has openai:', hasProvider('openai'));
  console.log('Has ollama:', hasProvider('ollama'));
  console.log();

  // Register custom providers
  console.log('Registering custom providers...');
  registerProvider('simple-custom', SimpleCustomProvider);
  registerProvider('ollama', OllamaProvider, { aliases: ['local'] });
  console.log();

  // Check providers after registration
  console.log('Providers after registration:', listProviders());
  console.log('Has ollama:', hasProvider('ollama'));
  console.log('Has local (alias):', hasProvider('local'));
  console.log();

  // Create and use providers
  console.log('=== Using Custom Providers ===\n');

  // Use simple custom provider
  const simpleProvider = createProvider('simple-custom/test-model');
  console.log(`Created provider: ${simpleProvider.providerId}/${simpleProvider.modelId}`);
  
  const simpleResult = await simpleProvider.generateText({
    messages: [{ role: 'user', content: 'Hello!' }]
  });
  console.log('Response:', simpleResult.text);
  console.log('Usage:', simpleResult.usage);
  console.log();

  // Use ollama provider via alias
  const ollamaProvider = createProvider('local/llama2', {
    baseUrl: 'http://localhost:11434'
  } as any);
  console.log(`Created provider: ${ollamaProvider.providerId}/${ollamaProvider.modelId}`);
  console.log();

  // Demonstrate error handling for unknown provider
  console.log('=== Error Handling ===\n');
  try {
    createProvider('unknown-provider/model');
  } catch (error: any) {
    console.log('Expected error:', error.message);
  }

  console.log('\n=== Example Complete ===');
}

main().catch(console.error);
