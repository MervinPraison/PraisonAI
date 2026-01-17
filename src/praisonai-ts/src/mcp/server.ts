/**
 * MCP Server - Model Context Protocol Server Implementation
 * 
 * Exposes agent tools and capabilities via MCP protocol.
 * 
 * @example
 * ```typescript
 * import { MCPServer, Agent } from 'praisonai';
 * 
 * const agent = new Agent({ name: 'Helper', tools: [...] });
 * const server = new MCPServer({ agent });
 * 
 * await server.start({ port: 3000 });
 * ```
 */

import { randomUUID } from 'crypto';

/**
 * MCP Tool definition
 */
export interface MCPServerTool {
    name: string;
    description: string;
    inputSchema: {
        type: 'object';
        properties: Record<string, { type: string; description?: string }>;
        required?: string[];
    };
    handler: (params: Record<string, any>) => Promise<any>;
}

/**
 * MCP Resource definition
 */
export interface MCPResource {
    uri: string;
    name: string;
    description?: string;
    mimeType?: string;
    handler: () => Promise<{ contents: Array<{ uri: string; text?: string; blob?: string }> }>;
}

/**
 * MCP Prompt definition
 */
export interface MCPPrompt {
    name: string;
    description?: string;
    arguments?: Array<{ name: string; description?: string; required?: boolean }>;
    handler: (args: Record<string, string>) => Promise<{ messages: Array<{ role: string; content: any }> }>;
}

/**
 * MCP Server configuration
 */
export interface MCPServerConfig {
    /** Server name */
    name?: string;
    /** Server version */
    version?: string;
    /** Agent to expose */
    agent?: any;
    /** Tools to expose */
    tools?: MCPServerTool[];
    /** Resources to expose */
    resources?: MCPResource[];
    /** Prompts to expose */
    prompts?: MCPPrompt[];
    /** Enable stdio transport */
    stdio?: boolean;
    /** HTTP port (null = disabled) */
    port?: number | null;
    /** Enable logging */
    logging?: boolean;
}

/**
 * MCP Request
 */
interface MCPRequest {
    jsonrpc: '2.0';
    id?: string | number;
    method: string;
    params?: Record<string, any>;
}

/**
 * MCP Response
 */
interface MCPResponse {
    jsonrpc: '2.0';
    id?: string | number;
    result?: any;
    error?: { code: number; message: string; data?: any };
}

/**
 * MCP Server - Expose tools via Model Context Protocol
 */
export class MCPServer {
    readonly id: string;
    private name: string;
    private version: string;
    private tools: Map<string, MCPServerTool>;
    private resources: Map<string, MCPResource>;
    private prompts: Map<string, MCPPrompt>;
    private logging: boolean;
    private running: boolean = false;
    private httpServer: any = null;

    constructor(config: MCPServerConfig = {}) {
        this.id = randomUUID();
        this.name = config.name ?? 'praisonai-mcp-server';
        this.version = config.version ?? '1.0.0';
        this.tools = new Map();
        this.resources = new Map();
        this.prompts = new Map();
        this.logging = config.logging ?? false;

        // Register initial tools
        if (config.tools) {
            for (const tool of config.tools) {
                this.registerTool(tool);
            }
        }

        // Register resources
        if (config.resources) {
            for (const resource of config.resources) {
                this.registerResource(resource);
            }
        }

        // Register prompts
        if (config.prompts) {
            for (const prompt of config.prompts) {
                this.registerPrompt(prompt);
            }
        }

        // Extract tools from agent
        if (config.agent) {
            this.registerAgentTools(config.agent);
        }
    }

    /**
     * Register a tool
     */
    registerTool(tool: MCPServerTool): void {
        this.tools.set(tool.name, tool);
        if (this.logging) {
            console.log(`[MCPServer] Registered tool: ${tool.name}`);
        }
    }

    /**
     * Register a resource
     */
    registerResource(resource: MCPResource): void {
        this.resources.set(resource.uri, resource);
    }

    /**
     * Register a prompt
     */
    registerPrompt(prompt: MCPPrompt): void {
        this.prompts.set(prompt.name, prompt);
    }

    /**
     * Extract and register tools from an agent
     */
    private registerAgentTools(agent: any): void {
        // Check if agent has tools array
        const tools = agent.tools ?? agent.config?.tools ?? [];

        for (const tool of tools) {
            if (typeof tool === 'function') {
                // Function tool
                this.registerTool({
                    name: tool.name ?? 'unnamed_tool',
                    description: tool.description ?? 'No description',
                    inputSchema: tool.parameters ?? { type: 'object', properties: {} },
                    handler: async (params) => tool(params),
                });
            } else if (tool.name && (tool.execute || tool.handler)) {
                // Object tool
                this.registerTool({
                    name: tool.name,
                    description: tool.description ?? 'No description',
                    inputSchema: tool.inputSchema ?? tool.parameters ?? { type: 'object', properties: {} },
                    handler: tool.execute ?? tool.handler,
                });
            }
        }
    }

    /**
     * Handle MCP request
     */
    async handleRequest(request: MCPRequest): Promise<MCPResponse> {
        const { method, params, id } = request;

        try {
            let result: any;

            switch (method) {
                case 'initialize':
                    result = this.handleInitialize(params);
                    break;
                case 'initialized':
                    result = {};
                    break;
                case 'tools/list':
                    result = this.handleToolsList();
                    break;
                case 'tools/call':
                    result = await this.handleToolCall(params);
                    break;
                case 'resources/list':
                    result = this.handleResourcesList();
                    break;
                case 'resources/read':
                    result = await this.handleResourceRead(params);
                    break;
                case 'prompts/list':
                    result = this.handlePromptsList();
                    break;
                case 'prompts/get':
                    result = await this.handlePromptGet(params);
                    break;
                case 'ping':
                    result = {};
                    break;
                default:
                    throw { code: -32601, message: `Method not found: ${method}` };
            }

            return { jsonrpc: '2.0', id, result };
        } catch (error: any) {
            return {
                jsonrpc: '2.0',
                id,
                error: {
                    code: error.code ?? -32000,
                    message: error.message ?? 'Unknown error',
                },
            };
        }
    }

    /**
     * Handle initialize request
     */
    private handleInitialize(params?: any): any {
        return {
            protocolVersion: '2024-11-05',
            capabilities: {
                tools: this.tools.size > 0 ? {} : undefined,
                resources: this.resources.size > 0 ? { subscribe: false, listChanged: false } : undefined,
                prompts: this.prompts.size > 0 ? { listChanged: false } : undefined,
            },
            serverInfo: {
                name: this.name,
                version: this.version,
            },
        };
    }

    /**
     * Handle tools/list
     */
    private handleToolsList(): any {
        const tools = Array.from(this.tools.values()).map(t => ({
            name: t.name,
            description: t.description,
            inputSchema: t.inputSchema,
        }));
        return { tools };
    }

    /**
     * Handle tools/call
     */
    private async handleToolCall(params?: any): Promise<any> {
        const { name, arguments: args } = params ?? {};

        const tool = this.tools.get(name);
        if (!tool) {
            throw { code: -32602, message: `Tool not found: ${name}` };
        }

        if (this.logging) {
            console.log(`[MCPServer] Calling tool: ${name}`);
        }

        const result = await tool.handler(args ?? {});

        return {
            content: [
                {
                    type: 'text',
                    text: typeof result === 'string' ? result : JSON.stringify(result),
                },
            ],
        };
    }

    /**
     * Handle resources/list
     */
    private handleResourcesList(): any {
        const resources = Array.from(this.resources.values()).map(r => ({
            uri: r.uri,
            name: r.name,
            description: r.description,
            mimeType: r.mimeType,
        }));
        return { resources };
    }

    /**
     * Handle resources/read
     */
    private async handleResourceRead(params?: any): Promise<any> {
        const { uri } = params ?? {};

        const resource = this.resources.get(uri);
        if (!resource) {
            throw { code: -32602, message: `Resource not found: ${uri}` };
        }

        return resource.handler();
    }

    /**
     * Handle prompts/list
     */
    private handlePromptsList(): any {
        const prompts = Array.from(this.prompts.values()).map(p => ({
            name: p.name,
            description: p.description,
            arguments: p.arguments,
        }));
        return { prompts };
    }

    /**
     * Handle prompts/get
     */
    private async handlePromptGet(params?: any): Promise<any> {
        const { name, arguments: args } = params ?? {};

        const prompt = this.prompts.get(name);
        if (!prompt) {
            throw { code: -32602, message: `Prompt not found: ${name}` };
        }

        return prompt.handler(args ?? {});
    }

    /**
     * Start stdio transport
     */
    async startStdio(): Promise<void> {
        if (this.running) return;
        this.running = true;

        if (this.logging) {
            console.error(`[MCPServer] Starting stdio transport...`);
        }

        const readline = await import('readline');
        const rl = readline.createInterface({
            input: process.stdin,
            output: process.stdout,
            terminal: false,
        });

        rl.on('line', async (line: string) => {
            try {
                const request = JSON.parse(line) as MCPRequest;
                const response = await this.handleRequest(request);
                console.log(JSON.stringify(response));
            } catch (error: any) {
                console.log(JSON.stringify({
                    jsonrpc: '2.0',
                    error: { code: -32700, message: 'Parse error' },
                }));
            }
        });

        rl.on('close', () => {
            this.running = false;
        });
    }

    /**
     * Start HTTP transport
     */
    async startHttp(port: number): Promise<void> {
        if (this.running) return;

        // Lazy load http
        const http = await import('http');

        this.httpServer = http.createServer(async (req, res) => {
            if (req.method === 'POST') {
                let body = '';
                req.on('data', chunk => body += chunk);
                req.on('end', async () => {
                    try {
                        const request = JSON.parse(body) as MCPRequest;
                        const response = await this.handleRequest(request);
                        res.writeHead(200, { 'Content-Type': 'application/json' });
                        res.end(JSON.stringify(response));
                    } catch {
                        res.writeHead(400, { 'Content-Type': 'application/json' });
                        res.end(JSON.stringify({ error: 'Invalid request' }));
                    }
                });
            } else if (req.method === 'GET' && req.url === '/health') {
                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ status: 'ok', server: this.name }));
            } else {
                res.writeHead(404);
                res.end();
            }
        });

        await new Promise<void>((resolve) => {
            this.httpServer.listen(port, () => {
                this.running = true;
                if (this.logging) {
                    console.log(`[MCPServer] HTTP server listening on port ${port}`);
                }
                resolve();
            });
        });
    }

    /**
     * Start server
     */
    async start(options?: { port?: number; stdio?: boolean }): Promise<void> {
        if (options?.stdio) {
            await this.startStdio();
        }
        if (options?.port) {
            await this.startHttp(options.port);
        }
    }

    /**
     * Stop server
     */
    async stop(): Promise<void> {
        if (this.httpServer) {
            await new Promise<void>((resolve) => {
                this.httpServer.close(() => resolve());
            });
            this.httpServer = null;
        }
        this.running = false;
    }

    /**
     * Check if running
     */
    isRunning(): boolean {
        return this.running;
    }

    /**
     * Get server info
     */
    getInfo(): { name: string; version: string; tools: number; resources: number; prompts: number } {
        return {
            name: this.name,
            version: this.version,
            tools: this.tools.size,
            resources: this.resources.size,
            prompts: this.prompts.size,
        };
    }
}

/**
 * Create an MCP server
 */
export function createMCPServer(config?: MCPServerConfig): MCPServer {
    return new MCPServer(config);
}

// Default export
export default MCPServer;
