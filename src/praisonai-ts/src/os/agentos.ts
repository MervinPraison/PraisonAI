/**
 * AgentOS Implementation
 * 
 * Production platform for deploying AI agents as web services.
 * Implements the AgentOSProtocol for serving agents via HTTP.
 * 
 * @example Basic Usage
 * ```typescript
 * import { AgentOS, Agent } from 'praisonai';
 * 
 * const assistant = new Agent({
 *   name: 'assistant',
 *   instructions: 'Be helpful'
 * });
 * 
 * const app = new AgentOS({
 *   name: 'My AI App',
 *   agents: [assistant]
 * });
 * 
 * await app.serve({ port: 8000 });
 * ```
 * 
 * @example With Teams and Flows
 * ```typescript
 * const app = new AgentOS({
 *   name: 'My AI App',
 *   agents: [assistant],
 *   teams: [myTeam],
 *   flows: [myFlow],
 *   config: { port: 9000, debug: true }
 * });
 * ```
 */

import type { AgentOSProtocol } from './protocols';
import type { AgentOSConfig } from './config';
import { DEFAULT_AGENTOS_CONFIG, mergeConfig } from './config';

// Type imports for Agent, AgentTeam, AgentFlow (avoid circular deps)
type Agent = {
    name?: string;
    role?: string;
    instructions?: string;
    chat: (message: string) => Promise<string>;
};

type AgentTeam = {
    agents?: Agent[];
    start: () => Promise<string[]>;
};

type AgentFlow = {
    name?: string;
    run: (input: any) => Promise<any>;
};

/**
 * Chat request body
 */
interface ChatRequest {
    message: string;
    agent_name?: string;
    session_id?: string;
}

/**
 * Chat response body
 */
interface ChatResponse {
    response: string;
    agent_name: string;
    session_id?: string;
}

/**
 * AgentOS constructor options
 */
export interface AgentOSOptions {
    /** Name of the application */
    name?: string;

    /** List of Agent instances to serve */
    agents?: any[];

    /** List of AgentTeam instances to serve */
    teams?: any[];

    /** List of AgentFlow instances to serve */
    flows?: any[];

    /** Server configuration */
    config?: AgentOSConfig;

    // Backward compatibility aliases
    /** @deprecated Use `teams` instead */
    managers?: any[];

    /** @deprecated Use `flows` instead */
    workflows?: any[];
}

/**
 * Production platform for deploying AI agents as web services.
 * 
 * AgentOS wraps agents, teams, and flows into a unified HTTP
 * application with REST endpoints.
 */
export class AgentOS implements AgentOSProtocol {
    /** Application name */
    readonly name: string;

    /** List of Agent instances */
    readonly agents: Agent[];

    /** List of AgentTeam instances */
    readonly teams: AgentTeam[];

    /** List of AgentFlow instances */
    readonly flows: AgentFlow[];

    /** Merged configuration */
    readonly config: Required<Omit<AgentOSConfig, 'metadata'>> & { metadata: Record<string, any> };

    /** HTTP server instance (lazy initialized) */
    private _server: any = null;

    /** Express app instance (lazy initialized) */
    private _app: any = null;

    /**
     * Create a new AgentOS instance.
     * 
     * @param options - AgentOS options
     */
    constructor(options: AgentOSOptions = {}) {
        this.name = options.name || DEFAULT_AGENTOS_CONFIG.name;
        this.agents = options.agents || [];

        // Support both new names and legacy aliases
        this.teams = options.teams || options.managers || [];
        this.flows = options.flows || options.workflows || [];

        // Merge config with defaults
        this.config = mergeConfig({
            name: this.name,
            ...options.config,
        });
    }

    /**
     * Create the Express application.
     * 
     * @returns Express app instance
     */
    private _createApp(): any {
        // Lazy import express
        let express: any;
        let cors: any;

        try {
            express = require('express');
        } catch {
            throw new Error(
                'Express is required for AgentOS. ' +
                'Install with: npm install express'
            );
        }

        try {
            cors = require('cors');
        } catch {
            // cors is optional, we'll handle manually if not available
            cors = null;
        }

        const app = express();

        // Parse JSON bodies
        app.use(express.json());

        // Add CORS middleware
        if (cors) {
            app.use(cors({
                origin: this.config.corsOrigins,
                credentials: true,
                methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
                allowedHeaders: ['Content-Type', 'Authorization'],
            }));
        } else {
            // Manual CORS handling
            app.use((req: any, res: any, next: any) => {
                res.header('Access-Control-Allow-Origin', this.config.corsOrigins[0] || '*');
                res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
                res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization');
                res.header('Access-Control-Allow-Credentials', 'true');
                if (req.method === 'OPTIONS') {
                    return res.sendStatus(200);
                }
                next();
            });
        }

        // Register routes
        this._registerRoutes(app);

        return app;
    }

    /**
     * Register API routes.
     * 
     * @param app - Express app instance
     */
    private _registerRoutes(app: any): void {
        const { apiPrefix } = this.config;

        // GET / - Root info
        app.get('/', (req: any, res: any) => {
            res.json({
                name: this.name,
                status: 'running',
                agents: this.agents.map(a => a.name || 'unnamed'),
                teams: this.teams.length,
                flows: this.flows.length,
            });
        });

        // GET /health - Health check
        app.get('/health', (req: any, res: any) => {
            res.json({ status: 'healthy' });
        });

        // GET /api/agents - List agents
        app.get(`${apiPrefix}/agents`, (req: any, res: any) => {
            res.json({
                agents: this.agents.map((agent, i) => ({
                    name: agent.name || `agent_${i}`,
                    role: agent.role || null,
                    instructions: agent.instructions
                        ? (agent.instructions.length > 100
                            ? agent.instructions.substring(0, 100) + '...'
                            : agent.instructions)
                        : null,
                })),
            });
        });

        // POST /api/chat - Chat with an agent
        app.post(`${apiPrefix}/chat`, async (req: any, res: any) => {
            try {
                const { message, agent_name, session_id }: ChatRequest = req.body;

                if (!message) {
                    return res.status(400).json({ error: 'Message is required' });
                }

                // Find the agent
                let agent: Agent | undefined;

                if (agent_name) {
                    agent = this.agents.find(a => a.name === agent_name);
                    if (!agent) {
                        return res.status(404).json({ error: `Agent '${agent_name}' not found` });
                    }
                } else if (this.agents.length > 0) {
                    agent = this.agents[0];
                } else {
                    return res.status(400).json({ error: 'No agents available' });
                }

                // Call the agent
                const response = await agent.chat(message);

                const result: ChatResponse = {
                    response: String(response),
                    agent_name: agent.name || 'unknown',
                    session_id,
                };

                res.json(result);
            } catch (error: any) {
                console.error('Chat error:', error);
                res.status(500).json({ error: error.message || 'Internal server error' });
            }
        });

        // GET /api/teams - List teams
        app.get(`${apiPrefix}/teams`, (req: any, res: any) => {
            res.json({
                teams: this.teams.map((team, i) => ({
                    name: `team_${i}`,
                    agents: team.agents?.length || 0,
                })),
            });
        });

        // GET /api/flows - List flows
        app.get(`${apiPrefix}/flows`, (req: any, res: any) => {
            res.json({
                flows: this.flows.map((flow, i) => ({
                    name: flow.name || `flow_${i}`,
                })),
            });
        });
    }

    /**
     * Get the Express application instance.
     * 
     * @returns The Express application instance for custom mounting or configuration
     */
    getApp(): any {
        if (!this._app) {
            this._app = this._createApp();
        }
        return this._app;
    }

    /**
     * Start the AgentOS server.
     * 
     * @param options - Server options
     * @returns Promise that resolves when server is listening
     */
    async serve(options: {
        host?: string;
        port?: number;
        reload?: boolean;
    } = {}): Promise<void> {
        const host = options.host || this.config.host;
        const port = options.port || this.config.port;

        const app = this.getApp();

        return new Promise((resolve, reject) => {
            try {
                this._server = app.listen(port, host, () => {
                    console.log(`🚀 AgentOS "${this.name}" running at http://${host}:${port}`);
                    console.log(`   Agents: ${this.agents.length}`);
                    console.log(`   Teams: ${this.teams.length}`);
                    console.log(`   Flows: ${this.flows.length}`);
                    console.log(`   API: http://${host}:${port}${this.config.apiPrefix}`);
                    resolve();
                });

                this._server.on('error', (error: any) => {
                    reject(error);
                });
            } catch (error) {
                reject(error);
            }
        });
    }

    /**
     * Stop the AgentOS server.
     * 
     * @returns Promise that resolves when server is stopped
     */
    async stop(): Promise<void> {
        if (this._server) {
            return new Promise((resolve) => {
                this._server.close(() => {
                    this._server = null;
                    resolve();
                });
            });
        }
    }
}

/**
 * AgentApp - Silent alias for AgentOS (backward compatibility)
 * @deprecated Use AgentOS instead
 */
export const AgentApp = AgentOS;

/**
 * AgentAppOptions - Silent alias for AgentOSOptions (backward compatibility)
 * @deprecated Use AgentOSOptions instead
 */
export type AgentAppOptions = AgentOSOptions;
