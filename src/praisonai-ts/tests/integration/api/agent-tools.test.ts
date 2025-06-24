import { Agent } from '../../../src/agent/agent';
import { ToolManager } from '../../../src/tools/tools';
import { Task } from '../../../src/types';

jest.mock('../../../src/llm/openai');

describe('Agent Tools Integration', () => {
    let agent: Agent;
    let toolManager: ToolManager;

    beforeEach(() => {
        agent = new Agent();
        toolManager = new ToolManager();
    });

    describe('tool registration', () => {
        it('should register tools', () => {
            const calculatorTool = {
                name: 'calculator',
                description: 'Performs calculations',
                execute: async () => '42'
            };

            const translatorTool = {
                name: 'translator',
                description: 'Translates text',
                execute: async () => 'translated'
            };

            toolManager.register(calculatorTool);
            toolManager.register(translatorTool);

            const tools = toolManager.list();
            expect(tools.map(t => t.name)).toContain('calculator');
            expect(tools.map(t => t.name)).toContain('translator');
        });

        it('should prevent duplicate tool registration', () => {
            const tool = {
                name: 'calculator',
                description: 'Performs calculations',
                execute: async () => '42'
            };

            toolManager.register(tool);
            expect(() => toolManager.register(tool)).toThrow();
        });
    });

    describe('tool execution', () => {
        it('should execute registered tool', async () => {
            const tool = {
                name: 'calculator',
                description: 'Performs calculations',
                execute: async () => '42'
            };

            toolManager.register(tool);
            const result = await toolManager.execute('calculator', '2 + 2');
            expect(result).toBe('42');
        });

        it('should throw error for unregistered tool', async () => {
            await expect(toolManager.execute('unknown', 'input')).rejects.toThrow();
        });
    });

    describe('agent integration', () => {
        it('should configure agent with tools', () => {
            const tool = {
                name: 'calculator',
                description: 'Performs calculations',
                execute: async () => '42'
            };

            agent.configure({ tools: [tool] });
            const tools = agent.getTools();
            expect(tools).toHaveLength(1);
            expect(tools[0].name).toBe('calculator');
        });

        it('should execute task with tools', async () => {
            const task: Task = {
                id: 'test-task',
                name: 'Test Task',
                description: 'A test task',
                config: {
                    priority: 1
                },
                expected_output: 'test output',
                agent: 'test-agent',
                dependencies: [],
                result: null
            };

            const tool = {
                name: 'calculator',
                description: 'Performs calculations',
                execute: async () => '42'
            };

            agent.configure({ tools: [tool] });
            const result = await agent.execute(task);
            expect(result).toBeDefined();
            expect(result.id).toBe('test-task');
        });
    });
});
