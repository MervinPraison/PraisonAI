import OpenAI from 'openai';
import dotenv from 'dotenv';
import { Logger } from '../utils/logger';
import type { ChatCompletionTool, ChatCompletionToolChoiceOption, ChatCompletionMessageParam } from 'openai/resources/chat/completions';

// Load environment variables once at the application level
dotenv.config();

if (!process.env.OPENAI_API_KEY) {
    throw new Error('OPENAI_API_KEY not found in environment variables');
}

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
        return tool as ChatCompletionTool;
    }
    
    // Otherwise, try to convert it
    return {
        type: 'function',
        function: {
            name: tool.function?.name || '',
            description: tool.function?.description || '',
            parameters: tool.function?.parameters || {}
        }
    };
}

// Singleton instance for OpenAI client
let openAIInstance: OpenAI | null = null;

// Get cached OpenAI client instance
async function getOpenAIClient(): Promise<OpenAI> {
    if (!openAIInstance) {
        openAIInstance = new OpenAI({
            apiKey: process.env.OPENAI_API_KEY
        });
        await Logger.debug('OpenAI client initialized');
    }
    return openAIInstance;
}

export class OpenAIService {
    private model: string;
    private client: OpenAI | null = null;

    constructor(model: string = 'gpt-4o-mini') {
        this.model = model;
        Logger.debug(`OpenAIService initialized with model: ${model}`);
    }

    // Lazy initialization of client
    private async getClient(): Promise<OpenAI> {
        if (!this.client) {
            this.client = await getOpenAIClient();
        }
        return this.client;
    }

    async generateText(
        prompt: string,
        systemPrompt: string = '',
        temperature: number = 0.7,
        tools?: ChatCompletionTool[],
        tool_choice?: ChatCompletionToolChoiceOption
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
                    temperature,
                    messages: openAIMessages,
                    tools: openAITools,
                    tool_choice
                })
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
        tool_choice?: ChatCompletionToolChoiceOption
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
                    temperature,
                    messages: openAIMessages,
                    tools: openAITools,
                    tool_choice
                })
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
        onToolCall?: (toolCall: any) => void
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
                    temperature,
                    messages: openAIMessages,
                    stream: true,
                    tools: openAITools,
                    tool_choice
                })
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
                    temperature,
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
