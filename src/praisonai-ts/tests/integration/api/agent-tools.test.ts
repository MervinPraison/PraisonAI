import { Agent } from '../../../src/agent';

describe('Agent Tools API Integration', () => {
    describe('Agent with Tools', () => {
        it('should create agent with inline tools', () => {
            const calculatorTool = {
                name: 'calculator',
                description: 'Performs calculations',
                parameters: { type: 'object' as const, properties: {} },
                execute: async () => '42'
            };

            const agent = new Agent({
                instructions: 'You are a helpful assistant',
                tools: [calculatorTool]
            });

            expect(agent).toBeDefined();
        });

        it('should create agent with multiple tools', () => {
            const tools = [
                {
                    name: 'calculator',
                    description: 'Performs calculations',
                    parameters: { type: 'object' as const, properties: {} },
                    execute: async () => '42'
                },
                {
                    name: 'translator',
                    description: 'Translates text',
                    parameters: { type: 'object' as const, properties: {} },
                    execute: async () => 'translated'
                }
            ];

            const agent = new Agent({
                instructions: 'You are a helpful assistant',
                tools
            });

            expect(agent).toBeDefined();
        });
    });

    describe('Agent Configuration', () => {
        it('should create agent with name', () => {
            const agent = new Agent({
                name: 'TestAgent',
                instructions: 'Test instructions'
            });
            expect(agent).toBeDefined();
        });

        it('should create agent with LLM config', () => {
            const agent = new Agent({
                instructions: 'Test instructions',
                llm: 'openai/gpt-4o-mini'
            });
            expect(agent).toBeDefined();
        });

        it('should create agent with verbose mode', () => {
            const agent = new Agent({
                instructions: 'Test instructions',
                verbose: true
            });
            expect(agent).toBeDefined();
        });
    });
});
