/**
 * Unit tests for AgentOS implementation
 */

import {
    AgentOS,
    AgentApp,
    AgentOSOptions,
    DEFAULT_AGENTOS_CONFIG,
} from '../../../src/os';

// Mock agent for testing
const createMockAgent = (name: string = 'test-agent') => ({
    name,
    role: 'assistant',
    instructions: 'Be helpful',
    chat: jest.fn().mockResolvedValue(`Response from ${name}`),
});

// Mock team for testing
const createMockTeam = () => ({
    agents: [createMockAgent('team-agent')],
    start: jest.fn().mockResolvedValue(['Result 1', 'Result 2']),
});

// Mock flow for testing
const createMockFlow = (name: string = 'test-flow') => ({
    name,
    run: jest.fn().mockResolvedValue({ output: 'flow result' }),
});

describe('AgentOS', () => {
    describe('constructor', () => {
        it('should create with default options', () => {
            const app = new AgentOS();

            expect(app.name).toBe(DEFAULT_AGENTOS_CONFIG.name);
            expect(app.agents).toEqual([]);
            expect(app.teams).toEqual([]);
            expect(app.flows).toEqual([]);
            expect(app.config.port).toBe(8000);
        });

        it('should accept custom name', () => {
            const app = new AgentOS({ name: 'My App' });

            expect(app.name).toBe('My App');
            expect(app.config.name).toBe('My App');
        });

        it('should accept agents', () => {
            const agent = createMockAgent();
            const app = new AgentOS({ agents: [agent] });

            expect(app.agents).toHaveLength(1);
            expect(app.agents[0].name).toBe('test-agent');
        });

        it('should accept teams', () => {
            const team = createMockTeam();
            const app = new AgentOS({ teams: [team] });

            expect(app.teams).toHaveLength(1);
        });

        it('should accept flows', () => {
            const flow = createMockFlow();
            const app = new AgentOS({ flows: [flow] });

            expect(app.flows).toHaveLength(1);
            expect(app.flows[0].name).toBe('test-flow');
        });

        it('should accept config', () => {
            const app = new AgentOS({
                config: {
                    port: 9000,
                    debug: true,
                    corsOrigins: ['http://localhost:3000'],
                },
            });

            expect(app.config.port).toBe(9000);
            expect(app.config.debug).toBe(true);
            expect(app.config.corsOrigins).toEqual(['http://localhost:3000']);
        });

        // Backward compatibility tests
        it('should accept managers as alias for teams', () => {
            const team = createMockTeam();
            const app = new AgentOS({ managers: [team] });

            expect(app.teams).toHaveLength(1);
        });

        it('should accept workflows as alias for flows', () => {
            const flow = createMockFlow();
            const app = new AgentOS({ workflows: [flow] });

            expect(app.flows).toHaveLength(1);
        });

        it('should prefer teams over managers', () => {
            const team1 = createMockTeam();
            const team2 = createMockTeam();
            const app = new AgentOS({
                teams: [team1],
                managers: [team2]
            });

            // teams should be used, not managers
            expect(app.teams).toHaveLength(1);
        });
    });

    describe('getApp', () => {
        beforeEach(() => {
            // Mock express
            jest.resetModules();
        });

        it('should create app lazily', () => {
            const app = new AgentOS();

            // First call creates the app
            const expressApp = app.getApp();
            expect(expressApp).toBeDefined();

            // Second call returns the same app
            const sameApp = app.getApp();
            expect(sameApp).toBe(expressApp);
        });
    });
});

describe('AgentApp alias', () => {
    it('should be the same as AgentOS', () => {
        expect(AgentApp).toBe(AgentOS);
    });

    it('should create instance with same API', () => {
        const agent = createMockAgent();
        const app = new AgentApp({
            name: 'Test App',
            agents: [agent]
        });

        expect(app.name).toBe('Test App');
        expect(app.agents).toHaveLength(1);
        expect(app instanceof AgentOS).toBe(true);
    });
});

describe('Full AgentOS configuration', () => {
    it('should accept all configuration options', () => {
        const options: AgentOSOptions = {
            name: 'Full App',
            agents: [createMockAgent()],
            teams: [createMockTeam()],
            flows: [createMockFlow()],
            config: {
                host: '127.0.0.1',
                port: 4000,
                reload: true,
                corsOrigins: ['http://example.com'],
                apiPrefix: '/v1',
                docsUrl: '/documentation',
                openapiUrl: '/schema.json',
                debug: true,
                logLevel: 'debug',
                workers: 4,
                timeout: 120,
                metadata: { version: '1.0.0' },
            },
        };

        const app = new AgentOS(options);

        expect(app.name).toBe('Full App');
        expect(app.agents).toHaveLength(1);
        expect(app.teams).toHaveLength(1);
        expect(app.flows).toHaveLength(1);
        expect(app.config.host).toBe('127.0.0.1');
        expect(app.config.port).toBe(4000);
        expect(app.config.reload).toBe(true);
        expect(app.config.apiPrefix).toBe('/v1');
        expect(app.config.logLevel).toBe('debug');
        expect(app.config.workers).toBe(4);
        expect(app.config.timeout).toBe(120);
        expect(app.config.metadata).toEqual({ version: '1.0.0' });
    });
});
