/**
 * MCP (Model Context Protocol) - AI SDK Wrapper
 * 
 * Provides MCP client utilities for connecting to MCP servers and using their tools.
 */

export interface MCPConfig {
  /** Transport configuration */
  transport: MCPTransportConfig;
  /** Client name */
  name?: string;
  /** Client version */
  version?: string;
  /** Callback for uncaught errors */
  onUncaughtError?: (error: unknown) => void;
}

export type MCPTransportConfig =
  | { type: 'stdio'; command: string; args?: string[]; env?: Record<string, string> }
  | { type: 'sse'; url: string; headers?: Record<string, string>; authProvider?: OAuthClientProvider }
  | { type: 'http'; url: string; headers?: Record<string, string>; authProvider?: OAuthClientProvider }
  | { type: 'websocket'; url: string; headers?: Record<string, string> };

/**
 * OAuth client provider for MCP authentication.
 */
export interface OAuthClientProvider {
  /** Get the current access token */
  getAccessToken(): Promise<string | null>;
  /** Refresh the access token */
  refreshToken?(): Promise<string | null>;
  /** Handle OAuth redirect */
  handleRedirect?(url: string): Promise<void>;
}

export interface MCPClient {
  /** Get tools from the MCP server */
  tools(): Promise<Record<string, MCPTool>>;
  /** List available resources */
  listResources(): Promise<MCPResource[]>;
  /** Read a resource */
  readResource(uri: string): Promise<MCPResourceContent>;
  /** List available prompts */
  listPrompts(): Promise<MCPPrompt[]>;
  /** Get a prompt */
  getPrompt(name: string, args?: Record<string, string>): Promise<MCPPromptResult>;
  /** Close the connection */
  close(): Promise<void>;
}

export interface MCPTool {
  /** Tool name */
  name: string;
  /** Tool description */
  description?: string;
  /** Input schema */
  inputSchema: any;
  /** Execute the tool */
  execute: (args: any) => Promise<any>;
}

export interface MCPResource {
  /** Resource URI */
  uri: string;
  /** Resource name */
  name: string;
  /** Resource description */
  description?: string;
  /** MIME type */
  mimeType?: string;
}

export interface MCPResourceContent {
  /** Content URI */
  uri: string;
  /** Content MIME type */
  mimeType?: string;
  /** Text content */
  text?: string;
  /** Binary content (base64) */
  blob?: string;
}

export interface MCPPrompt {
  /** Prompt name */
  name: string;
  /** Prompt description */
  description?: string;
  /** Arguments */
  arguments?: Array<{
    name: string;
    description?: string;
    required?: boolean;
  }>;
}

export interface MCPPromptResult {
  /** Prompt description */
  description?: string;
  /** Messages */
  messages: Array<{
    role: 'user' | 'assistant';
    content: { type: 'text'; text: string } | { type: 'image'; data: string; mimeType: string };
  }>;
}

// Connection pool for MCP clients
const clientPool = new Map<string, MCPClient>();

/**
 * Create an MCP client.
 * 
 * @example Stdio transport (local server)
 * ```typescript
 * const client = await createMCP({
 *   transport: {
 *     type: 'stdio',
 *     command: 'npx',
 *     args: ['-y', '@modelcontextprotocol/server-filesystem', '/path/to/dir']
 *   }
 * });
 * 
 * const tools = await client.tools();
 * ```
 * 
 * @example SSE transport (remote server)
 * ```typescript
 * const client = await createMCP({
 *   transport: {
 *     type: 'sse',
 *     url: 'https://mcp-server.example.com/sse'
 *   }
 * });
 * ```
 */
export async function createMCP(config: MCPConfig): Promise<MCPClient> {
  // Try to use AI SDK MCP client (optional dependency)
  try {
    // @ts-ignore - Optional dependency
    const mcpModule = await import('@ai-sdk/mcp');
    
    const transport = createTransport(config.transport);
    const client = await mcpModule.createMCPClient({
      transport,
      name: config.name,
      version: config.version,
      onUncaughtError: config.onUncaughtError,
    });

    return {
      tools: async () => {
        const toolSet = await client.tools();
        return toolSet as Record<string, MCPTool>;
      },
      listResources: async () => {
        const result = await client.listResources();
        return result.resources || [];
      },
      readResource: async (uri: string) => {
        const result = await client.readResource({ uri });
        return result.contents?.[0] || { uri };
      },
      listPrompts: async () => {
        const result = await client.listPrompts();
        return result.prompts || [];
      },
      getPrompt: async (name: string, args?: Record<string, string>) => {
        const result = await client.getPrompt({ name, arguments: args });
        return result as MCPPromptResult;
      },
      close: async () => {
        await client.close();
      },
    };
  } catch (error: any) {
    // Fall back to native implementation
    return createNativeMCPClient(config);
  }
}

/**
 * Create transport configuration for AI SDK MCP.
 */
function createTransport(config: MCPTransportConfig): any {
  switch (config.type) {
    case 'stdio':
      return {
        type: 'stdio',
        command: config.command,
        args: config.args,
        env: config.env,
      };
    case 'sse':
      return {
        type: 'sse',
        url: config.url,
        headers: config.headers,
        authProvider: config.authProvider,
      };
    case 'http':
      return {
        type: 'http',
        url: config.url,
        headers: config.headers,
        authProvider: config.authProvider,
      };
    case 'websocket':
      return {
        type: 'websocket',
        url: config.url,
        headers: config.headers,
      };
    default:
      throw new Error(`Unknown transport type: ${(config as any).type}`);
  }
}

/**
 * Native MCP client implementation (fallback).
 */
async function createNativeMCPClient(config: MCPConfig): Promise<MCPClient> {
  // This is a simplified native implementation
  // In production, this would use the @modelcontextprotocol/sdk directly
  
  const tools: Record<string, MCPTool> = {};
  const resources: MCPResource[] = [];
  const prompts: MCPPrompt[] = [];

  return {
    tools: async () => tools,
    listResources: async () => resources,
    readResource: async (uri: string) => ({ uri }),
    listPrompts: async () => prompts,
    getPrompt: async (name: string) => ({ messages: [] }),
    close: async () => {},
  };
}

/**
 * Get or create a pooled MCP client.
 * 
 * @example
 * ```typescript
 * const client = await getMCPClient('filesystem', {
 *   transport: { type: 'stdio', command: 'npx', args: ['-y', '@mcp/server-fs'] }
 * });
 * ```
 */
export async function getMCPClient(key: string, config: MCPConfig): Promise<MCPClient> {
  if (clientPool.has(key)) {
    return clientPool.get(key)!;
  }

  const client = await createMCP(config);
  clientPool.set(key, client);
  return client;
}

/**
 * Close and remove a pooled MCP client.
 */
export async function closeMCPClient(key: string): Promise<void> {
  const client = clientPool.get(key);
  if (client) {
    await client.close();
    clientPool.delete(key);
  }
}

/**
 * Close all pooled MCP clients.
 */
export async function closeAllMCPClients(): Promise<void> {
  for (const [key, client] of clientPool) {
    await client.close();
    clientPool.delete(key);
  }
}

/**
 * Convert MCP tools to AI SDK tool format.
 * 
 * @example
 * ```typescript
 * const client = await createMCP({ ... });
 * const mcpTools = await client.tools();
 * const aiTools = mcpToolsToAITools(mcpTools);
 * 
 * const result = await generateText({
 *   model: 'gpt-4o',
 *   prompt: 'List files in the current directory',
 *   tools: aiTools
 * });
 * ```
 */
export function mcpToolsToAITools(mcpTools: Record<string, MCPTool>): Record<string, any> {
  const aiTools: Record<string, any> = {};
  
  for (const [name, tool] of Object.entries(mcpTools)) {
    aiTools[name] = {
      description: tool.description || `MCP tool: ${name}`,
      parameters: tool.inputSchema,
      execute: tool.execute,
    };
  }
  
  return aiTools;
}
