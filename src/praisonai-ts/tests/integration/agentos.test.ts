/**
 * Integration tests for AgentOS HTTP endpoints
 * 
 * These tests verify the actual HTTP server functionality:
 * - Server starts and stops correctly
 * - All endpoints respond correctly
 * - Chat endpoint works with mock agents
 */

import { AgentOS } from '../../src/os';
import http from 'http';

// Mock agent for testing
const createMockAgent = (name: string, responseText: string = 'Hello!') => ({
    name,
    role: 'assistant',
    instructions: 'Be helpful',
    chat: jest.fn().mockResolvedValue(responseText),
});

// Helper to make HTTP requests with timeout
const httpRequest = async (
    port: number,
    path: string,
    method: string = 'GET',
    body?: any,
    timeout: number = 5000
): Promise<{ status: number; data: any }> => {
    return new Promise((resolve, reject) => {
        const options: http.RequestOptions = {
            hostname: '127.0.0.1',
            port,
            path,
            method,
            headers: {
                'Content-Type': 'application/json',
            },
            timeout,
        };

        const req = http.request(options, (res) => {
            let data = '';
            res.on('data', (chunk) => (data += chunk));
            res.on('end', () => {
                try {
                    resolve({
                        status: res.statusCode || 500,
                        data: data ? JSON.parse(data) : null,
                    });
                } catch {
                    resolve({ status: res.statusCode || 500, data });
                }
            });
        });

        req.on('error', reject);
        req.on('timeout', () => {
            req.destroy();
            reject(new Error('Request timeout'));
        });

        if (body) {
            req.write(JSON.stringify(body));
        }
        req.end();
    });
};

// Helper to wait for server to be ready
const waitForServer = async (port: number, maxAttempts = 10): Promise<void> => {
    for (let i = 0; i < maxAttempts; i++) {
        try {
            await httpRequest(port, '/health', 'GET', undefined, 1000);
            return;
        } catch {
            await new Promise(resolve => setTimeout(resolve, 100));
        }
    }
    throw new Error(`Server on port ${port} not ready after ${maxAttempts} attempts`);
};

describe('AgentOS Integration Tests', () => {
    describe('Server lifecycle', () => {
        it('should start and stop the server', async () => {
            const testPort = 19080;
            const app = new AgentOS({
                name: 'Test App',
                agents: [createMockAgent('agent1', 'Hello from agent1!')],
                config: { port: testPort },
            });

            await app.serve({ port: testPort });
            await waitForServer(testPort);

            // Server should be running
            const response = await httpRequest(testPort, '/health');
            expect(response.status).toBe(200);
            expect(response.data.status).toBe('healthy');

            // Stop the server
            await app.stop();

            // Server should be stopped (request should fail)
            await expect(httpRequest(testPort, '/health', 'GET', undefined, 1000)).rejects.toThrow();
        });
    });

    describe('Root endpoint', () => {
        it('should return app info at GET /', async () => {
            const testPort = 19081;
            const app = new AgentOS({
                name: 'Test App',
                agents: [
                    createMockAgent('agent1', 'Hello from agent1!'),
                    createMockAgent('agent2', 'Hello from agent2!'),
                ],
                teams: [{
                    agents: [],
                    start: jest.fn(),
                }],
                flows: [{
                    name: 'flow1',
                    run: jest.fn(),
                }],
                config: { port: testPort },
            });

            await app.serve({ port: testPort });
            await waitForServer(testPort);

            try {
                const response = await httpRequest(testPort, '/');

                expect(response.status).toBe(200);
                expect(response.data.name).toBe('Test App');
                expect(response.data.status).toBe('running');
                expect(response.data.agents).toEqual(['agent1', 'agent2']);
                expect(response.data.teams).toBe(1);
                expect(response.data.flows).toBe(1);
            } finally {
                await app.stop();
            }
        });
    });

    describe('Health endpoint', () => {
        it('should return healthy status at GET /health', async () => {
            const testPort = 19082;
            const app = new AgentOS({
                name: 'Test App',
                agents: [createMockAgent('agent1')],
                config: { port: testPort },
            });

            await app.serve({ port: testPort });
            await waitForServer(testPort);

            try {
                const response = await httpRequest(testPort, '/health');

                expect(response.status).toBe(200);
                expect(response.data.status).toBe('healthy');
            } finally {
                await app.stop();
            }
        });
    });

    describe('Agents endpoint', () => {
        it('should list all agents at GET /api/agents', async () => {
            const testPort = 19083;
            const app = new AgentOS({
                name: 'Test App',
                agents: [
                    createMockAgent('agent1'),
                    createMockAgent('agent2'),
                ],
                config: { port: testPort },
            });

            await app.serve({ port: testPort });
            await waitForServer(testPort);

            try {
                const response = await httpRequest(testPort, '/api/agents');

                expect(response.status).toBe(200);
                expect(response.data.agents).toHaveLength(2);
                expect(response.data.agents[0]).toEqual({
                    name: 'agent1',
                    role: 'assistant',
                    instructions: 'Be helpful',
                });
                expect(response.data.agents[1].name).toBe('agent2');
            } finally {
                await app.stop();
            }
        });

        it('should list empty agents array when no agents', async () => {
            const testPort = 19084;
            const app = new AgentOS({
                name: 'Empty App',
                config: { port: testPort },
            });

            await app.serve({ port: testPort });
            await waitForServer(testPort);

            try {
                const response = await httpRequest(testPort, '/api/agents');

                expect(response.status).toBe(200);
                expect(response.data.agents).toEqual([]);
            } finally {
                await app.stop();
            }
        });
    });

    describe('Chat endpoint', () => {
        it('should chat with default agent', async () => {
            const testPort = 19085;
            const app = new AgentOS({
                name: 'Test App',
                agents: [createMockAgent('agent1', 'Hello from agent1!')],
                config: { port: testPort },
            });

            await app.serve({ port: testPort });
            await waitForServer(testPort);

            try {
                const response = await httpRequest(testPort, '/api/chat', 'POST', {
                    message: 'Hello!',
                });

                expect(response.status).toBe(200);
                expect(response.data.response).toBe('Hello from agent1!');
                expect(response.data.agent_name).toBe('agent1');
            } finally {
                await app.stop();
            }
        });

        it('should chat with specific agent by name', async () => {
            const testPort = 19086;
            const app = new AgentOS({
                name: 'Test App',
                agents: [
                    createMockAgent('agent1', 'Hello from agent1!'),
                    createMockAgent('agent2', 'Hello from agent2!'),
                ],
                config: { port: testPort },
            });

            await app.serve({ port: testPort });
            await waitForServer(testPort);

            try {
                const response = await httpRequest(testPort, '/api/chat', 'POST', {
                    message: 'Hello!',
                    agent_name: 'agent2',
                });

                expect(response.status).toBe(200);
                expect(response.data.response).toBe('Hello from agent2!');
                expect(response.data.agent_name).toBe('agent2');
            } finally {
                await app.stop();
            }
        });

        it('should return session_id if provided', async () => {
            const testPort = 19087;
            const app = new AgentOS({
                name: 'Test App',
                agents: [createMockAgent('agent1', 'Hello!')],
                config: { port: testPort },
            });

            await app.serve({ port: testPort });
            await waitForServer(testPort);

            try {
                const response = await httpRequest(testPort, '/api/chat', 'POST', {
                    message: 'Hello!',
                    session_id: 'test-session-123',
                });

                expect(response.status).toBe(200);
                expect(response.data.session_id).toBe('test-session-123');
            } finally {
                await app.stop();
            }
        });

        it('should return 400 if message is missing', async () => {
            const testPort = 19088;
            const app = new AgentOS({
                name: 'Test App',
                agents: [createMockAgent('agent1')],
                config: { port: testPort },
            });

            await app.serve({ port: testPort });
            await waitForServer(testPort);

            try {
                const response = await httpRequest(testPort, '/api/chat', 'POST', {});

                expect(response.status).toBe(400);
                expect(response.data.error).toBe('Message is required');
            } finally {
                await app.stop();
            }
        });

        it('should return 404 if agent not found', async () => {
            const testPort = 19089;
            const app = new AgentOS({
                name: 'Test App',
                agents: [createMockAgent('agent1')],
                config: { port: testPort },
            });

            await app.serve({ port: testPort });
            await waitForServer(testPort);

            try {
                const response = await httpRequest(testPort, '/api/chat', 'POST', {
                    message: 'Hello!',
                    agent_name: 'nonexistent',
                });

                expect(response.status).toBe(404);
                expect(response.data.error).toContain('not found');
            } finally {
                await app.stop();
            }
        });

        it('should return 400 for chat when no agents', async () => {
            const testPort = 19090;
            const app = new AgentOS({
                name: 'Empty App',
                config: { port: testPort },
            });

            await app.serve({ port: testPort });
            await waitForServer(testPort);

            try {
                const response = await httpRequest(testPort, '/api/chat', 'POST', {
                    message: 'Hello!',
                });

                expect(response.status).toBe(400);
                expect(response.data.error).toBe('No agents available');
            } finally {
                await app.stop();
            }
        });
    });

    describe('Teams endpoint', () => {
        it('should list all teams at GET /api/teams', async () => {
            const testPort = 19091;
            const app = new AgentOS({
                name: 'Test App',
                agents: [createMockAgent('agent1')],
                teams: [{
                    agents: [],
                    start: jest.fn(),
                }],
                config: { port: testPort },
            });

            await app.serve({ port: testPort });
            await waitForServer(testPort);

            try {
                const response = await httpRequest(testPort, '/api/teams');

                expect(response.status).toBe(200);
                expect(response.data.teams).toHaveLength(1);
                expect(response.data.teams[0].name).toBe('team_0');
            } finally {
                await app.stop();
            }
        });
    });

    describe('Flows endpoint', () => {
        it('should list all flows at GET /api/flows', async () => {
            const testPort = 19092;
            const app = new AgentOS({
                name: 'Test App',
                agents: [createMockAgent('agent1')],
                flows: [{
                    name: 'flow1',
                    run: jest.fn(),
                }],
                config: { port: testPort },
            });

            await app.serve({ port: testPort });
            await waitForServer(testPort);

            try {
                const response = await httpRequest(testPort, '/api/flows');

                expect(response.status).toBe(200);
                expect(response.data.flows).toHaveLength(1);
                expect(response.data.flows[0].name).toBe('flow1');
            } finally {
                await app.stop();
            }
        });
    });

    describe('Custom API prefix', () => {
        it('should use custom API prefix', async () => {
            const testPort = 19093;
            const app = new AgentOS({
                name: 'Custom API App',
                agents: [createMockAgent('agent1')],
                config: {
                    port: testPort,
                    apiPrefix: '/v1',
                },
            });

            await app.serve({ port: testPort });
            await waitForServer(testPort);

            try {
                const response = await httpRequest(testPort, '/v1/agents');

                expect(response.status).toBe(200);
                expect(response.data.agents).toHaveLength(1);
            } finally {
                await app.stop();
            }
        });

        it('should return 404 for default API prefix when custom is set', async () => {
            const testPort = 19094;
            const app = new AgentOS({
                name: 'Custom API App',
                agents: [createMockAgent('agent1')],
                config: {
                    port: testPort,
                    apiPrefix: '/v1',
                },
            });

            await app.serve({ port: testPort });
            await waitForServer(testPort);

            try {
                const response = await httpRequest(testPort, '/api/agents');

                expect(response.status).toBe(404);
            } finally {
                await app.stop();
            }
        });
    });
});
