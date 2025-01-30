import OpenAI from 'openai';
import dotenv from 'dotenv';
import { Logger } from '../utils/logger';

dotenv.config();

export interface LLMResponse {
    content: string;
    role: string;
}

export class OpenAIService {
    private client: OpenAI;
    private model: string;

    constructor(model: string = 'gpt-4o-mini') {
        if (!process.env.OPENAI_API_KEY) {
            throw new Error('OPENAI_API_KEY not found in environment variables');
        }

        this.client = new OpenAI({
            apiKey: process.env.OPENAI_API_KEY
        });
        this.model = model;
        Logger.debug(`OpenAIService initialized with model: ${model}`);
    }

    async generateText(
        prompt: string,
        systemPrompt: string = '',
        temperature: number = 0.7
    ): Promise<string> {
        Logger.debug('Generating text with OpenAI', {
            model: this.model,
            temperature,
            systemPrompt,
            prompt
        });

        const completion = await this.client.chat.completions.create({
            model: this.model,
            messages: [
                { role: 'system', content: systemPrompt },
                { role: 'user', content: prompt }
            ],
            temperature,
        });

        const response = completion.choices[0].message.content || '';
        Logger.debug('OpenAI response received', { response });
        return response;
    }

    async streamText(
        prompt: string,
        systemPrompt: string = '',
        temperature: number = 0.7,
        onToken: (token: string) => void
    ): Promise<void> {
        Logger.debug('Streaming text with OpenAI', {
            model: this.model,
            temperature,
            systemPrompt,
            prompt
        });

        const stream = await this.client.chat.completions.create({
            model: this.model,
            messages: [
                { role: 'system', content: systemPrompt },
                { role: 'user', content: prompt }
            ],
            temperature,
            stream: true,
        });

        let fullResponse = '';
        for await (const chunk of stream) {
            const content = chunk.choices[0]?.delta?.content;
            if (content) {
                onToken(content);
                fullResponse += content;
            }
        }
        Logger.debug('OpenAI streaming completed', { fullResponse });
    }

    async chatCompletion(
        messages: Array<{ role: 'system' | 'user' | 'assistant'; content: string }>,
        temperature: number = 0.7
    ): Promise<LLMResponse> {
        Logger.debug('Chat completion with OpenAI', {
            model: this.model,
            temperature,
            messages
        });

        const completion = await this.client.chat.completions.create({
            model: this.model,
            messages,
            temperature,
        });

        const response = {
            content: completion.choices[0].message.content || '',
            role: completion.choices[0].message.role
        };

        Logger.debug('OpenAI chat completion response received', { response });
        return response;
    }
}
