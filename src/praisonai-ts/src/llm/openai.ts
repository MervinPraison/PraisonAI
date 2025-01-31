import OpenAI from 'openai';
import dotenv from 'dotenv';
import { Logger } from '../utils/logger';

// Load environment variables once at the application level
dotenv.config();

if (!process.env.OPENAI_API_KEY) {
    throw new Error('OPENAI_API_KEY not found in environment variables');
}

export interface LLMResponse {
    content: string;
    role: string;
}

type ChatRole = 'system' | 'user' | 'assistant';

interface ChatMessage {
    role: ChatRole;
    content: string;
}

// Singleton instance for OpenAI client
let openAIInstance: OpenAI | null = null;

// Get cached OpenAI client instance
async function getOpenAIClient(): Promise<OpenAI> {
    if (!openAIInstance) {
        openAIInstance = new OpenAI({
            apiKey: process.env.OPENAI_API_KEY
        });
        await Logger.success('OpenAI client initialized');
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
        temperature: number = 0.7
    ): Promise<string> {
        await Logger.startSpinner('Generating text with OpenAI...');
        
        const messages: ChatMessage[] = [];
        if (systemPrompt) {
            messages.push({ role: 'system', content: systemPrompt });
        }
        messages.push({ role: 'user', content: prompt });

        try {
            const completion = await this.getClient().then(client => 
                client.chat.completions.create({
                    model: this.model,
                    temperature,
                    messages
                })
            );

            const response = completion.choices[0]?.message?.content;
            if (!response) {
                throw new Error('No response from OpenAI');
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
        temperature: number = 0.7
    ): Promise<LLMResponse> {
        await Logger.startSpinner('Generating chat response...');

        try {
            const completion = await this.getClient().then(client =>
                client.chat.completions.create({
                    model: this.model,
                    temperature,
                    messages
                })
            );

            const response = completion.choices[0]?.message;
            if (!response) {
                throw new Error('No response from OpenAI');
            }

            await Logger.stopSpinner(true);
            const result = {
                content: response.content || '',
                role: response.role
            };
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
        onToken: (token: string) => void
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
            const stream = await this.getClient().then(client =>
                client.chat.completions.create({
                    model: this.model,
                    temperature,
                    messages,
                    stream: true,
                })
            );

            let fullResponse = '';
            for await (const chunk of stream) {
                const token = chunk.choices[0]?.delta?.content || '';
                fullResponse += token;
                onToken(token);
            }

            await Logger.success('Stream completed successfully');
        } catch (error) {
            await Logger.error('Error in text stream', error);
            throw error;
        }
    }

    async chatCompletion(
        messages: ChatMessage[],
        temperature: number = 0.7
    ): Promise<LLMResponse> {
        await Logger.startSpinner('Chat completion with OpenAI...');

        try {
            const completion = await this.getClient().then(client =>
                client.chat.completions.create({
                    model: this.model,
                    temperature,
                    messages
                })
            );

            const response = {
                content: completion.choices[0].message.content || '',
                role: completion.choices[0].message.role
            };

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
