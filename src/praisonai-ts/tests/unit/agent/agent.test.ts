import { Agent } from '../../../../src/agent/agent';
import { Task, Tool } from '../../../../src/types';

jest.mock('../../../../src/llm/openai');

describe('Agent', () => {
    let agent: Agent;

    beforeEach(() => {
        agent = new Agent();
    });

    describe('configuration', () => {
        it('should configure agent with tools', () => {
            const tool: Tool = {
                name: 'test-tool',
                description: 'A test tool',
                execute: async () => 'test result'
            };

            agent.configure({ tools: [tool] });
            const tools = agent.getTools();
            expect(tools).toHaveLength(1);
            expect(tools[0].name).toBe('test-tool');
        });
    });

    describe('task execution', () => {
        it('should execute simple task', async () => {
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

            const result = await agent.execute(task);
            expect(result).toBeDefined();
            expect(result.id).toBe('test-task');
        });

        it('should execute complex task', async () => {
            const task: Task = {
                id: 'complex-task',
                name: 'Complex Task',
                description: 'A complex task',
                config: {
                    priority: 1
                },
                expected_output: 'test output',
                agent: 'test-agent',
                dependencies: [
                    {
                        id: 'dep-task',
                        name: 'Dependency Task',
                        description: 'A dependency task',
                        config: {
                            priority: 1
                        },
                        expected_output: 'dependency output',
                        agent: 'test-agent',
                        dependencies: [],
                        result: 'dependency result'
                    }
                ],
                result: null
            };

            const result = await agent.execute(task);
            expect(result).toBeDefined();
            expect(result.id).toBe('complex-task');
        });

        it('should handle task failure', async () => {
            const task: Task = {
                id: 'failing-task',
                name: 'Failing Task',
                description: 'A task that fails',
                config: {
                    priority: 1,
                    shouldFail: true
                },
                expected_output: 'test output',
                agent: 'test-agent',
                dependencies: [],
                result: null
            };

            await expect(agent.execute(task)).rejects.toThrow();
        });
    });

    describe('tool management', () => {
        it('should execute tool', async () => {
            const tool: Tool = {
                name: 'test-tool',
                description: 'A test tool',
                execute: async () => 'test result'
            };

            agent.configure({ tools: [tool] });
            const result = await agent.executeTool('test-tool', 'test input');
            expect(result).toBe('test result');
        });

        it('should handle unknown tool', async () => {
            await expect(agent.executeTool('unknown-tool', 'test input')).rejects.toThrow();
        });
    });
});
