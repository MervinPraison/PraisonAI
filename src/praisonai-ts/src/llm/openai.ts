import OpenAI from 'openai';
import { buildOpenAIClientOptions, getEnv } from './openaiClientOptions';
import { Logger } from '../utils/logger';
import type { ChatCompletionTool, ChatCompletionToolChoiceOption, ChatCompletionMessageParam } from 'openai/resources/chat/completions';

// The API-key check lives in getOpenAIClient(), where the client is actually
// created — importing the package must not throw for users of non-OpenAI
// providers (anthropic/..., google/...) who never touch the OpenAI path.

export interface LLMResponse {
    content: string;
    role: string;
    tool_calls?: Array<{
        id: string;
        type: string;
        function: {
            name: string;
            arguments: string;
        };
    }>;
}

// Using OpenAI's types for compatibility
type ChatRole = 'system' | 'user' | 'assistant' | 'tool';

// Our internal message format, compatible with OpenAI's API
interface ChatMessage {
    role: ChatRole;
    content: string | null;
    tool_call_id?: string;
    tool_calls?: Array<{
        id: string;
        type: string;
        function: {
            name: string;
            arguments: string;
        };
    }>;
}

// Convert our ChatMessage to OpenAI's ChatCompletionMessageParam
function convertToOpenAIMessage(message: ChatMessage): ChatCompletionMessageParam {
    // Basic conversion for common message types
    if (message.role === 'system' || message.role === 'user' || message.role === 'assistant') {
        return {
            role: message.role,
            content: message.content || '',
            ...(message.tool_calls ? { tool_calls: message.tool_calls } : {})
        } as ChatCompletionMessageParam;
    }
    
    // Handle tool messages
    if (message.role === 'tool') {
        return {
            role: 'tool',
            content: message.content || '',
            tool_call_id: message.tool_call_id || ''
        } as ChatCompletionMessageParam;
    }
    
    // Default fallback
    return {
        role: 'user',
        content: message.content || ''
    };
}

// Convert custom tool format to OpenAI's ChatCompletionTool format
function convertToOpenAITool(tool: any): ChatCompletionTool {
    // If it's already in the correct format, return it
    if (tool.type === 'function' && typeof tool.type === 'string') {
        // Ensure the function name is valid
        if (!tool.function?.name || tool.function.name.trim() === '') {
            tool.function.name = `function_${Math.random().toString(36).substring(2, 9)}`;
        }
        return tool as ChatCompletionTool;
    }
    
    // Generate a valid function name if none is provided
    const functionName = tool.function?.name && tool.function.name.trim() !== '' 
        ? tool.function.name 
        : `function_${Math.random().toString(36).substring(2, 9)}`;
    
    // Otherwise, try to convert it
    return {
        type: 'function',
        function: {
            name: functionName,
            description: tool.function?.description || `Function ${functionName}`,
            parameters: tool.function?.parameters || {}
        }
    };
}

// Cached OpenAI client for the env-only fallback path, keyed on the
// credentials that determine client identity (API key + base URL). Keying on
// existence alone would reuse a client built from a stale key even after the
// environment changed — a real defect for long-lived processes (e.g. a mobile
// app whose settings screen updates the key without restarting).
let cachedClient: OpenAI | null = null;
let cachedIdentity: string | null = null;

// Get cached OpenAI client instance. Rebuilds when the API key or base URL
// changes so a rotated/updated credential is picked up without a restart.
export async function getOpenAIClient(): Promise<OpenAI> {
    const apiKey = getEnv('OPENAI_API_KEY');
    if (!apiKey) {
        throw new Error('OPENAI_API_KEY not found in environment variables');
    }
    const baseURL = getEnv('OPENAI_BASE_URL') ?? '';
    // Never log `identity`: it contains the secret API key.
    const identity = `${apiKey}\u0000${baseURL}`;
    if (cachedClient !== null && cachedIdentity === identity) {
        return cachedClient;
    }
    // Build synchronously and capture in a local before any await. Returning
    // the local (not the shared field) makes the result immune to a concurrent
    // credential change or resetOpenAIClient() that runs during the await —
    // each caller keeps the client it actually built for its own identity.
    const client = new OpenAI(buildOpenAIClientOptions({
        apiKey,
        ...(baseURL ? { baseURL } : {})
    }));
    cachedClient = client;
    cachedIdentity = identity;
    await Logger.debug('OpenAI client initialized');
    return client;
}

/**
 * Reset the cached env-only OpenAI client so the next call rebuilds it.
 *
 * Useful for tests and for a settings screen that wants to force a rebuild
 * after updating credentials without depending on the cache-invalidation rule.
 *
 * @example
 * resetOpenAIClient();
 */
export function resetOpenAIClient(): void {
    cachedClient = null;
    cachedIdentity = null;
}

/** response_format payload for Chat Completions (json_schema / json_object). */
export type ResponseFormat =
    | { type: 'json_object' }
    | { type: 'json_schema'; json_schema: { name: string; schema: Record<string, any>; strict?: boolean } };

/**
 * Per-service credential/transport options. Mirrors Python's per-agent
 * `api_key` / `base_url` so callers can pass credentials without relying on
 * process env, and can inject a custom `fetch` for browser-like runtimes.
 */
export interface OpenAIServiceOptions {
    apiKey?: string;
    baseURL?: string;
    fetch?: typeof fetch;
    dangerouslyAllowBrowser?: boolean;
}

export class OpenAIService {
    private model: string;
    private client: OpenAI | null = null;
    private options: OpenAIServiceOptions;

    constructor(model: string = 'gpt-5-nano', options: OpenAIServiceOptions = {}) {
        this.model = model;
        this.options = options;
        Logger.debug(`OpenAIService initialized with model: ${model}`);
    }

    // Lazy initialization of client
    private async getClient(): Promise<OpenAI> {
        if (!this.client) {
            // When explicit credentials/transport are supplied, build a
            // dedicated client so they are honoured instead of the shared
            // env-only singleton.
            if (this.options.apiKey || this.options.baseURL || this.options.fetch) {
                this.client = new OpenAI(buildOpenAIClientOptions(
                    {
                        apiKey: this.options.apiKey || getEnv('OPENAI_API_KEY'),
                        ...(this.options.baseURL ? { baseURL: this.options.baseURL } : {}),
                    },
                    {
                        fetch: this.options.fetch,
                        dangerouslyAllowBrowser: this.options.dangerouslyAllowBrowser,
                    }
                ));
            } else {
                this.client = await getOpenAIClient();
            }
        }
        return this.client;
    }

    // Reasoning-family models (gpt-5*, o1*, o3*, o4*) reject non-default
    // temperature with a 400; omit the param for them unless caller-set
    // temperature differs from the legacy 0.7 default.
    private temperatureParam(temperature: number): { temperature?: number } {
        const reasoningFamily = /^(gpt-5|o1|o3|o4)/.test(this.model);
        if (reasoningFamily && temperature === 0.7) {
            return {};
        }
        return { temperature };
    }

    async generateText(
        prompt: string,
        systemPrompt: string = '',
        temperature: number = 0.7,
        tools?: ChatCompletionTool[],
        tool_choice?: ChatCompletionToolChoiceOption,
        responseFormat?: ResponseFormat,
        signal?: AbortSignal
    ): Promise<string> {
        await Logger.startSpinner('Generating text with OpenAI...');
        
        const messages: ChatMessage[] = [];
        if (systemPrompt) {
            messages.push({ role: 'system', content: systemPrompt });
        }
        messages.push({ role: 'user', content: prompt });

        try {
            // Convert messages to OpenAI format
            const openAIMessages = messages.map(convertToOpenAIMessage);
            
            // Convert tools to OpenAI format if provided
            const openAITools = tools ? tools.map(convertToOpenAITool) : undefined;
            
            const completion = await this.getClient().then(client =>
                client.chat.completions.create({
                    model: this.model,
                    ...this.temperatureParam(temperature),
                    messages: openAIMessages,
                    tools: openAITools,
                    tool_choice,
                    ...(responseFormat ? { response_format: responseFormat } : {})
                }, { signal })
            );

            const message = completion.choices[0]?.message;
            if (!message) {
                throw new Error('No response from OpenAI');
            }
            
            // Check for tool calls
            if (message.tool_calls && message.tool_calls.length > 0) {
                await Logger.debug('Tool calls detected in generateText', { tool_calls: message.tool_calls });
                // For backward compatibility, we return a message about tool calls
                return 'The model wants to use tools. Please use generateChat or chatCompletion instead.';
            }
            
            const response = message.content;
            if (!response) {
                throw new Error('No content in response from OpenAI');
            }

            await Logger.stopSpinner(true);
            await Logger.section('Generated Response', response);
            return response;
        } catch (error) {
            await Logger.stopSpinner(false);
            await Logger.error('Error generating text', error);
            throw error;
        }
    }

    async generateChat(
        messages: ChatMessage[],
        temperature: number = 0.7,
        tools?: ChatCompletionTool[],
        tool_choice?: ChatCompletionToolChoiceOption,
        responseFormat?: ResponseFormat,
        signal?: AbortSignal
    ): Promise<LLMResponse> {
        await Logger.startSpinner('Generating chat response...');

        try {
            // Convert messages to OpenAI format
            const openAIMessages = messages.map(convertToOpenAIMessage);
            
            // Convert tools to OpenAI format if provided
            const openAITools = tools ? tools.map(convertToOpenAITool) : undefined;
            
            const completion = await this.getClient().then(client =>
                client.chat.completions.create({
                    model: this.model,
                    ...this.temperatureParam(temperature),
                    messages: openAIMessages,
                    tools: openAITools,
                    tool_choice,
                    ...(responseFormat ? { response_format: responseFormat } : {})
                }, { signal })
            );

            const response = completion.choices[0]?.message;
            if (!response) {
                throw new Error('No response from OpenAI');
            }

            await Logger.stopSpinner(true);
            const result: LLMResponse = {
                content: response.content || '',
                role: response.role
            };
            
            // Add tool calls if they exist
            if (response.tool_calls && response.tool_calls.length > 0) {
                result.tool_calls = response.tool_calls;
                await Logger.debug('Tool calls detected', { tool_calls: result.tool_calls });
            }
            await Logger.section('Chat Response', result.content);
            return result;
        } catch (error) {
            await Logger.stopSpinner(false);
            await Logger.error('Error generating chat response', error);
            throw error;
        }
    }

    async streamText(
        prompt: string,
        systemPrompt: string = '',
        temperature: number = 0.7,
        onToken: (token: string) => void,
        tools?: ChatCompletionTool[],
        tool_choice?: ChatCompletionToolChoiceOption,
        onToolCall?: (toolCall: any) => void,
        signal?: AbortSignal
    ): Promise<void> {
        await Logger.debug('Starting text stream...', {
            model: this.model,
            temperature
        });

        const messages: ChatMessage[] = [];
        if (systemPrompt) {
            messages.push({ role: 'system', content: systemPrompt });
        }
        messages.push({ role: 'user', content: prompt });

        try {
            // Convert messages to OpenAI format
            const openAIMessages = messages.map(convertToOpenAIMessage);
            
            // Convert tools to OpenAI format if provided
            const openAITools = tools ? tools.map(convertToOpenAITool) : undefined;
            
            const stream = await this.getClient().then(client =>
                client.chat.completions.create({
                    model: this.model,
                    ...this.temperatureParam(temperature),
                    messages: openAIMessages,
                    stream: true,
                    tools: openAITools,
                    tool_choice
                }, { signal })
            );

            let fullResponse = '';
            const toolCalls: Record<number, any> = {};
            
            for await (const chunk of stream) {
                const delta = chunk.choices[0]?.delta;
                
                // Handle content tokens
                if (delta?.content) {
                    const token = delta.content;
                    fullResponse += token;
                    onToken(token);
                }
                
                // Handle tool calls
                if (delta?.tool_calls && delta.tool_calls.length > 0) {
                    for (const toolCall of delta.tool_calls) {
                        const { index } = toolCall;
                        
                        if (!toolCalls[index]) {
                            toolCalls[index] = {
                                id: toolCall.id,
                                type: toolCall.type,
                                function: {
                                    name: toolCall.function?.name || '',
                                    arguments: ''
                                }
                            };
                        }
                        
                        // Accumulate function arguments
                        if (toolCall.function?.arguments) {
                            toolCalls[index].function.arguments += toolCall.function.arguments;
                        }
                        
                        // Call the onToolCall callback if provided
                        if (onToolCall) {
                            onToolCall(toolCalls[index]);
                        }
                    }
                }
            }

            await Logger.debug('Stream completed successfully');
        } catch (error) {
            await Logger.error('Error in text stream', error);
            throw error;
        }
    }

    async streamChat(
        messages: ChatMessage[],
        temperature: number = 0.7,
        onToken: (token: string) => void,
        signal?: AbortSignal
    ): Promise<string> {
        await Logger.debug('Starting chat stream with messages...', {
            model: this.model,
            messageCount: messages.length
        });

        try {
            const openAIMessages = messages.map(convertToOpenAIMessage);
            
            const stream = await this.getClient().then(client =>
                client.chat.completions.create({
                    model: this.model,
                    ...this.temperatureParam(temperature),
                    messages: openAIMessages,
                    stream: true
                }, { signal })
            );

            let fullResponse = '';
            
            for await (const chunk of stream) {
                const delta = chunk.choices[0]?.delta;
                if (delta?.content) {
                    const token = delta.content;
                    fullResponse += token;
                    onToken(token);
                }
            }

            await Logger.debug('Chat stream completed');
            return fullResponse;
        } catch (error) {
            await Logger.error('Error in chat stream', error);
            throw error;
        }
    }

    /**
     * Streaming chat that also surfaces tool calls. Text deltas are emitted
     * through `onToken` as they arrive; tool-call fragments are accumulated
     * across chunks and returned once the stream ends. This is the building
     * block that lets a streaming agent interleave reasoning text with tool
     * use in a single request (instead of streaming XOR tools).
     *
     * @returns The full streamed text plus any accumulated tool calls.
     */
    async streamChatWithTools(
        messages: ChatMessage[],
        temperature: number = 0.7,
        tools?: ChatCompletionTool[],
        onToken?: (token: string) => void,
        tool_choice?: ChatCompletionToolChoiceOption,
        responseFormat?: ResponseFormat,
        signal?: AbortSignal
    ): Promise<LLMResponse> {
        await Logger.debug('Starting chat stream with tools...', {
            model: this.model,
            messageCount: messages.length
        });

        try {
            const openAIMessages = messages.map(convertToOpenAIMessage);
            const openAITools = tools ? tools.map(convertToOpenAITool) : undefined;

            const stream = await this.getClient().then(client =>
                client.chat.completions.create({
                    model: this.model,
                    ...this.temperatureParam(temperature),
                    messages: openAIMessages,
                    stream: true,
                    tools: openAITools,
                    tool_choice,
                    ...(responseFormat ? { response_format: responseFormat } : {})
                }, { signal })
            );

            let fullResponse = '';
            const toolCalls: Record<number, any> = {};

            for await (const chunk of stream) {
                const delta = chunk.choices[0]?.delta;
                if (!delta) continue;

                // Stream text deltas as they arrive.
                if (delta.content) {
                    const token = delta.content;
                    fullResponse += token;
                    if (onToken) onToken(token);
                }

                // Accumulate tool-call fragments across chunks. The id/name
                // arrive on the first fragment; arguments stream in pieces.
                if (delta.tool_calls && delta.tool_calls.length > 0) {
                    for (const toolCall of delta.tool_calls) {
                        const index = toolCall.index ?? 0;
                        if (!toolCalls[index]) {
                            toolCalls[index] = {
                                id: toolCall.id || '',
                                type: toolCall.type || 'function',
                                function: {
                                    name: toolCall.function?.name || '',
                                    arguments: ''
                                }
                            };
                        }
                        if (toolCall.id) toolCalls[index].id = toolCall.id;
                        if (toolCall.function?.name) {
                            toolCalls[index].function.name = toolCall.function.name;
                        }
                        if (toolCall.function?.arguments) {
                            toolCalls[index].function.arguments += toolCall.function.arguments;
                        }
                    }
                }
            }

            const result: LLMResponse = {
                content: fullResponse,
                role: 'assistant'
            };
            const collected = Object.keys(toolCalls)
                .map(k => Number(k))
                .sort((a, b) => a - b)
                .map(i => toolCalls[i]);
            if (collected.length > 0) {
                result.tool_calls = collected;
                await Logger.debug('Tool calls detected in stream', { tool_calls: collected });
            }

            await Logger.debug('Chat stream with tools completed');
            return result;
        } catch (error) {
            await Logger.error('Error in chat stream with tools', error);
            throw error;
        }
    }

    async chatCompletion(
        messages: ChatMessage[],
        temperature: number = 0.7,
        tools?: ChatCompletionTool[],
        tool_choice?: ChatCompletionToolChoiceOption
    ): Promise<LLMResponse> {
        await Logger.startSpinner('Chat completion with OpenAI...');

        try {
            // Convert messages to OpenAI format
            const openAIMessages = messages.map(convertToOpenAIMessage);
            
            // Convert tools to OpenAI format if provided
            const openAITools = tools ? tools.map(convertToOpenAITool) : undefined;
            
            const completion = await this.getClient().then(client =>
                client.chat.completions.create({
                    model: this.model,
                    ...this.temperatureParam(temperature),
                    messages: openAIMessages,
                    tools: openAITools,
                    tool_choice
                })
            );

            // Safely access the message
            if (!completion.choices || completion.choices.length === 0 || !completion.choices[0].message) {
                throw new Error('No response from OpenAI');
            }
            
            const message = completion.choices[0].message;
            const response: LLMResponse = {
                content: message.content || '',
                role: message.role
            };
            
            // Add tool calls if they exist
            if (message.tool_calls && message.tool_calls.length > 0) {
                response.tool_calls = message.tool_calls;
                await Logger.debug('Tool calls detected', { tool_calls: response.tool_calls });
            }

            await Logger.stopSpinner(true);
            await Logger.section('Chat Completion Response', response.content);
            return response;
        } catch (error) {
            await Logger.stopSpinner(false);
            await Logger.error('Error in chat completion', error);
            throw error;
        }
    }
}
