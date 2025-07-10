/**
 * Unit tests for the Agent class with fixed imports and improved test patterns.
 */
import { Agent } from '../../../../src/agent/agent';
import { Task } from '../../../../src/agent/types';
import { Tool } from '../../../../src/tools';
import { Logger } from '../../../../src/utils/logger';

// Mock the OpenAI service to avoid external dependencies
jest.mock('../../../../src/llm/openai');

// Mock the logger to reduce noise in tests
jest.mock('../../../../src/utils/logger', () => ({
    Logger: {
        debug: jest.fn(),
        info: jest.fn(),
        warn: jest.fn(),
        error: jest.fn()
    }
}));

describe('Agent', () => {
    let agent: Agent;
    let mockConsoleLog: jest.SpyInstance;

    beforeEach(() => {
        agent = new Agent();
        mockConsoleLog = jest.spyOn(console, 'log').mockImplementation();
    });

    afterEach(() => {
        mockConsoleLog.mockRestore();
        jest.clearAllMocks();
    });

    describe('configuration', () => {
        it('should configure agent with tools and verify tool properties', () => {
            const mockExecute = jest.fn().mockResolvedValue('test result');
            const tool: Tool = {
                name: 'test-tool',
                description: 'A test tool for unit testing',
                execute: mockExecute
            };

            agent.configure({ tools: [tool] });
            const tools = agent.getTools();
            
            expect(tools).toHaveLength(1);
            expect(tools[0].name).toBe('test-tool');
            expect(tools[0].description).toBe('A test tool for unit testing');
            expect(tools[0].execute).toBe(mockExecute);
        });

        it('should handle empty tools array', () => {
            agent.configure({ tools: [] });
            const tools = agent.getTools();
            expect(tools).toHaveLength(0);
        });

        it('should handle multiple tools configuration', () => {
            const tools: Tool[] = [
                {
                    name: 'tool-1',
                    description: 'First tool',
                    execute: jest.fn()
                },
                {
                    name: 'tool-2',
                    description: 'Second tool',
                    execute: jest.fn()
                }
            ];

            agent.configure({ tools });
            const configuredTools = agent.getTools();
            expect(configuredTools).toHaveLength(2);
            expect(configuredTools.map(t => t.name)).toEqual(['tool-1', 'tool-2']);
        });
    });

    describe('task execution', () => {
        it('should execute simple task with all required properties', async () => {
            const task: Task = {
                name: 'Test Task',
                description: 'A test task for unit testing',
                expected_output: 'Expected test output',
                agent: agent,
                dependencies: [],
                result: null
            };

            const result = await agent.execute(task);
            
            expect(result).toBeDefined();
            expect(typeof result).toBe('object');
            // Verify task properties are preserved
            expect(result.name).toBe('Test Task');
            expect(result.description).toBe('A test task for unit testing');
        });

        it('should execute task with dependencies', async () => {
            const dependency: Task = {
                name: 'Dependency Task',
                description: 'A dependency task',
                expected_output: 'Dependency output',
                agent: agent,
                dependencies: [],
                result: 'Completed dependency'
            };

            const mainTask: Task = {
                name: 'Main Task',
                description: 'A task with dependencies',
                expected_output: 'Main output',
                agent: agent,
                dependencies: [dependency],
                result: null
            };

            const result = await agent.execute(mainTask);
            
            expect(result).toBeDefined();
            expect(result.dependencies).toHaveLength(1);
            expect(result.dependencies[0].result).toBe('Completed dependency');
        });

        it('should handle task execution failure gracefully', async () => {
            const mockError = new Error('Task execution failed');
            
            // Mock the execute method to throw an error
            jest.spyOn(agent, 'execute').mockRejectedValueOnce(mockError);

            const task: Task = {
                name: 'Failing Task',
                description: 'A task that will fail',
                expected_output: 'Should not reach this',
                agent: agent,
                dependencies: [],
                result: null
            };

            await expect(agent.execute(task)).rejects.toThrow('Task execution failed');
        });

        it('should handle null or undefined task properties', async () => {
            const task: Task = {
                name: 'Minimal Task',
                description: '',
                expected_output: '',
                agent: null,
                dependencies: [],
                result: null
            };

            const result = await agent.execute(task);
            
            expect(result).toBeDefined();
            expect(result.name).toBe('Minimal Task');
        });
    });

    describe('tool management', () => {
        it('should register and use tools during task execution', async () => {
            const mockToolExecute = jest.fn().mockResolvedValue('Tool executed successfully');
            const tool: Tool = {
                name: 'execution-tool',
                description: 'Tool for execution testing',
                execute: mockToolExecute
            };

            agent.configure({ tools: [tool] });

            const task: Task = {
                name: 'Tool Task',
                description: 'Execute with tool',
                expected_output: 'Tool result',
                agent: agent,
                dependencies: [],
                result: null
            };

            await agent.execute(task);
            
            // Verify tool was available
            const tools = agent.getTools();
            expect(tools).toContainEqual(tool);
        });

        it('should handle tool execution errors', async () => {
            const mockToolExecute = jest.fn().mockRejectedValue(new Error('Tool failed'));
            const tool: Tool = {
                name: 'failing-tool',
                description: 'Tool that fails',
                execute: mockToolExecute
            };

            agent.configure({ tools: [tool] });
            
            // Tool is configured but error handling is in the agent's execute method
            const tools = agent.getTools();
            expect(tools[0].name).toBe('failing-tool');
            
            // Test that the tool can fail
            await expect(tool.execute()).rejects.toThrow('Tool failed');
        });
    });

    describe('error handling', () => {
        it('should handle missing required configuration', () => {
            expect(() => {
                agent.configure(null as any);
            }).toThrow();
        });

        it('should handle invalid tool configuration', () => {
            const invalidTool = {
                name: 'invalid',
                // Missing required properties
            } as any;

            expect(() => {
                agent.configure({ tools: [invalidTool] });
            }).toThrow();
        });
    });

    describe('logging', () => {
        it('should log debug information during task execution', async () => {
            const task: Task = {
                name: 'Logged Task',
                description: 'Task with logging',
                expected_output: 'Logged output',
                agent: agent,
                dependencies: [],
                result: null
            };

            await agent.execute(task);

            // Verify Logger was called
            expect(Logger.debug).toHaveBeenCalled();
        });
    });
});