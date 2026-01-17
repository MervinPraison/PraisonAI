/**
 * MCP (Model Context Protocol) Integration
 * 
 * Provides client and server implementations for MCP,
 * enabling tool discovery and invocation across processes.
 * 
 * @example Using MCP Client
 * ```typescript
 * import { MCPClient } from 'praisonai';
 * 
 * const client = new MCPClient({ serverUrl: 'http://localhost:3000' });
 * await client.connect();
 * 
 * const tools = await client.listTools();
 * const result = await client.callTool('search', { query: 'AI' });
 * ```
 * 
 * @example Using MCP with Agent
 * ```typescript
 * import { Agent, MCPClient } from 'praisonai';
 * 
 * const mcp = new MCPClient({ serverUrl: 'http://localhost:3000' });
 * await mcp.connect();
 * 
 * const agent = new Agent({
 *   instructions: 'Use available tools',
 *   tools: await mcp.getToolsAsAISDK()
 * });
 * ```
 */

import { randomUUID } from 'crypto';

/**
 * MCP Transport types
 */
export type MCPTransportType = 'stdio' | 'http' | 'websocket' | 'sse';

/**
 * MCP Tool definition
 */
export interface MCPTool {
    name: string;
    description?: string;
    inputSchema?: Record<string, any>;
    annotations?: Record<string, any>;
}

/**
 * MCP Resource definition
 */
export interface MCPResource {
    uri: string;
    name: string;
    description?: string;
    mimeType?: string;
}

/**
 * MCP Prompt definition
 */
export interface MCPPrompt {
    name: string;
    description?: string;
    arguments?: Array<{
        name: string;
        description?: string;
        required?: boolean;
    }>;
}

/**
 * MCP Client configuration
 */
export interface MCPClientConfig {
    /** Server URL or command for stdio */
    serverUrl?: string;
    /** Transport type (default: 'http') */
    transport?: MCPTransportType;
    /** Command for stdio transport */
    command?: string;
    /** Arguments for stdio transport */
    args?: string[];
    /** Environment variables */
    env?: Record<string, string>;
    /** Connection timeout in ms */
    timeout?: number;
    /** Enable verbose logging */
    verbose?: boolean;
    /** API key for authentication */
    apiKey?: string;
}

/**
 * MCP Tool call result
 */
export interface MCPToolResult {
    content: Array<{
        type: 'text' | 'image' | 'resource';
        text?: string;
        mimeType?: string;
        data?: string;
        uri?: string;
    }>;
    isError?: boolean;
}

/**
 * MCP Session state
 */
export interface MCPSession {
    id: string;
    connected: boolean;
    serverInfo?: {
        name: string;
        version: string;
        capabilities?: Record<string, any>;
    };
    tools: MCPTool[];
    resources: MCPResource[];
    prompts: MCPPrompt[];
}

/**
 * MCP Client - Connect to MCP servers
 */
export class MCPClient {
    readonly id: string;
    private config: Required<MCPClientConfig>;
    private session: MCPSession;
    private transport: any = null;

    constructor(config: MCPClientConfig = {}) {
        this.id = randomUUID();
        this.config = {
            serverUrl: config.serverUrl ?? '',
            transport: config.transport ?? 'http',
            command: config.command ?? '',
            args: config.args ?? [],
            env: config.env ?? {},
            timeout: config.timeout ?? 30000,
            verbose: config.verbose ?? false,
            apiKey: config.apiKey ?? '',
        };

        this.session = {
            id: this.id,
            connected: false,
            tools: [],
            resources: [],
            prompts: [],
        };
    }

    /**
     * Connect to the MCP server
     */
    async connect(): Promise<void> {
        if (this.session.connected) return;

        if (this.config.verbose) {
            console.log(`[MCP] Connecting via ${this.config.transport}...`);
        }

        try {
            switch (this.config.transport) {
                case 'stdio':
                    await this.connectStdio();
                    break;
                case 'http':
                case 'sse':
                    await this.connectHttp();
                    break;
                case 'websocket':
                    await this.connectWebSocket();
                    break;
                default:
                    throw new Error(`Unsupported transport: ${this.config.transport}`);
            }

            // Initialize session
            await this.initialize();
            this.session.connected = true;

            if (this.config.verbose) {
                console.log(`[MCP] Connected to ${this.session.serverInfo?.name ?? 'server'}`);
            }
        } catch (error) {
            this.session.connected = false;
            throw error;
        }
    }

    /**
     * Connect via stdio (spawn process)
     */
    private async connectStdio(): Promise<void> {
        if (!this.config.command) {
            throw new Error('Command is required for stdio transport');
        }

        // Lazy import child_process
        const { spawn } = await import('child_process');

        const proc = spawn(this.config.command, this.config.args, {
            env: { ...process.env, ...this.config.env },
            stdio: ['pipe', 'pipe', 'inherit'],
        });

        this.transport = {
            type: 'stdio',
            process: proc,
            send: (message: any) => {
                proc.stdin.write(JSON.stringify(message) + '\n');
            },
            receive: () => new Promise((resolve) => {
                proc.stdout.once('data', (data) => {
                    resolve(JSON.parse(data.toString()));
                });
            }),
        };
    }

    /**
     * Connect via HTTP
     */
    private async connectHttp(): Promise<void> {
        if (!this.config.serverUrl) {
            throw new Error('Server URL is required for HTTP transport');
        }

        this.transport = {
            type: 'http',
            baseUrl: this.config.serverUrl,
            send: async (method: string, params?: any) => {
                const response = await fetch(`${this.config.serverUrl}/mcp`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        ...(this.config.apiKey ? { 'Authorization': `Bearer ${this.config.apiKey}` } : {}),
                    },
                    body: JSON.stringify({
                        jsonrpc: '2.0',
                        id: randomUUID(),
                        method,
                        params: params ?? {},
                    }),
                });

                const result = await response.json();
                if (result.error) {
                    throw new Error(result.error.message);
                }
                return result.result;
            },
        };
    }

    /**
     * Connect via WebSocket
     */
    private async connectWebSocket(): Promise<void> {
        if (!this.config.serverUrl) {
            throw new Error('Server URL is required for WebSocket transport');
        }

        // Lazy import ws with type handling
        // @ts-ignore - optional dependency
        const wsModule = await import('ws').catch(() => null);
        if (!wsModule) {
            throw new Error('WebSocket transport requires ws package. Run: npm install ws');
        }
        const WebSocket = wsModule.default;

        const ws = new WebSocket(this.config.serverUrl);

        await new Promise<void>((resolve, reject) => {
            ws.on('open', () => resolve());
            ws.on('error', (err: Error) => reject(err));
        });

        const pendingRequests = new Map<string, { resolve: Function; reject: Function }>();

        ws.on('message', (data: Buffer | string) => {
            const message = JSON.parse(data.toString());
            const pending = pendingRequests.get(message.id);
            if (pending) {
                if (message.error) {
                    pending.reject(new Error(message.error.message));
                } else {
                    pending.resolve(message.result);
                }
                pendingRequests.delete(message.id);
            }
        });

        this.transport = {
            type: 'websocket',
            ws,
            send: (method: string, params?: any) => new Promise((resolve, reject) => {
                const id = randomUUID();
                pendingRequests.set(id, { resolve, reject });
                ws.send(JSON.stringify({
                    jsonrpc: '2.0',
                    id,
                    method,
                    params: params ?? {},
                }));
            }),
        };
    }

    /**
     * Initialize MCP session
     */
    private async initialize(): Promise<void> {
        // Initialize protocol
        const initResult = await this.rpc('initialize', {
            protocolVersion: '2024-11-05',
            capabilities: {
                tools: {},
                resources: {},
                prompts: {},
            },
            clientInfo: {
                name: 'praisonai-ts',
                version: '1.0.0',
            },
        });

        this.session.serverInfo = initResult.serverInfo;

        // Notify initialized
        await this.rpc('notifications/initialized', {});

        // List available tools
        await this.refreshTools();
    }

    /**
     * Send RPC request
     */
    private async rpc(method: string, params?: any): Promise<any> {
        if (!this.transport) {
            throw new Error('Not connected');
        }

        if (this.transport.type === 'stdio') {
            this.transport.send({ jsonrpc: '2.0', id: randomUUID(), method, params });
            return this.transport.receive();
        }

        return this.transport.send(method, params);
    }

    /**
     * Refresh tools list from server
     */
    async refreshTools(): Promise<void> {
        try {
            const result = await this.rpc('tools/list', {});
            this.session.tools = result.tools ?? [];
        } catch {
            // Server may not support tools
            this.session.tools = [];
        }
    }

    /**
     * List available tools
     */
    async listTools(): Promise<MCPTool[]> {
        if (!this.session.connected) {
            await this.connect();
        }
        return this.session.tools;
    }

    /**
     * Call a tool
     */
    async callTool(name: string, args?: Record<string, any>): Promise<MCPToolResult> {
        if (!this.session.connected) {
            await this.connect();
        }

        return this.rpc('tools/call', {
            name,
            arguments: args ?? {},
        });
    }

    /**
     * Get tools formatted for AI SDK
     */
    async getToolsAsAISDK(): Promise<any[]> {
        const tools = await this.listTools();

        return tools.map(tool => ({
            type: 'function',
            function: {
                name: tool.name,
                description: tool.description ?? `Call ${tool.name}`,
                parameters: tool.inputSchema ?? { type: 'object', properties: {} },
            },
            execute: async (args: any) => {
                const result = await this.callTool(tool.name, args);
                const textContent = result.content.find(c => c.type === 'text');
                return textContent?.text ?? JSON.stringify(result);
            },
        }));
    }

    /**
     * Disconnect from server
     */
    async disconnect(): Promise<void> {
        if (this.transport?.type === 'stdio' && this.transport.process) {
            this.transport.process.kill();
        } else if (this.transport?.type === 'websocket' && this.transport.ws) {
            this.transport.ws.close();
        }

        this.transport = null;
        this.session.connected = false;
    }

    /**
     * Get session info
     */
    getSession(): MCPSession {
        return { ...this.session };
    }

    /**
     * Check if connected
     */
    isConnected(): boolean {
        return this.session.connected;
    }
}

/**
 * Factory function to create MCPClient
 */
export function createMCPClient(config?: MCPClientConfig): MCPClient {
    return new MCPClient(config);
}

/**
 * Connect to an MCP server and return tools
 */
export async function getMCPTools(config: MCPClientConfig): Promise<{ client: MCPClient; tools: any[] }> {
    const client = new MCPClient(config);
    await client.connect();
    const tools = await client.getToolsAsAISDK();
    return { client, tools };
}

// Default export
export default MCPClient;

// Re-export MCP Server
export {
    MCPServer, createMCPServer,
    type MCPServerTool, type MCPResource as MCPServerResource,
    type MCPPrompt as MCPServerPrompt, type MCPServerConfig
} from './server';

// Re-export MCP Session (aliased to avoid conflict with MCPSession interface)
export {
    MCPSession as MCPSessionManager,
    createMCPSession,
    SessionManager as MCPClientSessionManager,
    createSessionManager,
    type MCPSessionConfig,
    type SessionState,
    type SessionContext,
    type SessionEvent
} from './session';

// Re-export MCP Security
export {
    MCPSecurity, createMCPSecurity,
    createApiKeyPolicy, createRateLimitPolicy,
    type SecurityPolicy, type SecurityResult, type SecurityContext,
    type RateLimitConfig, type AuthMethod, type SecurityPolicyType
} from './security';
