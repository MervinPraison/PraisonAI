import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { SSEClientTransport } from '@modelcontextprotocol/sdk/client/sse.js';
import { MCPTool, MCPToolInfo, MCP as SSEMCP } from './mcpSse';
import { HTTPStreamingTransport, MCPHttpStreaming } from './mcpHttpStreaming';

export type TransportType = 'auto' | 'sse' | 'http-streaming';

export class MCP implements Iterable<MCPTool> {
  tools: MCPTool[] = [];
  private client: Client | null = null;
  private transport: TransportType;
  private actualTransport: 'sse' | 'http-streaming' | null = null;

  constructor(
    private url: string, 
    transport: TransportType = 'auto',
    private debug = false
  ) {
    this.transport = transport;
    
    // Auto-detect transport type based on URL
    if (transport === 'auto') {
      this.actualTransport = url.endsWith('/sse') ? 'sse' : 'http-streaming';
    } else if (transport === 'sse' || transport === 'http-streaming') {
      this.actualTransport = transport;
    } else {
      throw new Error(`Unknown transport type: ${transport}`);
    }
    
    if (debug) {
      console.log(`MCP client initialized for URL: ${url} with transport: ${this.actualTransport}`);
    }
  }

  async initialize(): Promise<void> {
    if (this.client) {
      if (this.debug) console.log('MCP client already initialized');
      return;
    }
    
    try {
      this.client = new Client({ name: 'praisonai-ts-mcp', version: '1.0.0' });
      
      // Create transport based on selection
      let transport;
      if (this.actualTransport === 'sse') {
        transport = new SSEClientTransport(new URL(this.url));
      } else if (this.actualTransport === 'http-streaming') {
        transport = new HTTPStreamingTransport(new URL(this.url));
      } else {
        throw new Error(`Invalid transport type: ${this.actualTransport}`);
      }
      
      await this.client.connect(transport);
      const { tools } = await this.client.listTools();
      this.tools = tools.map((t: any) => new MCPTool({
        name: t.name,
        description: t.description,
        inputSchema: t.inputSchema
      }, this.client as Client));
      
      if (this.debug) {
        console.log(`Initialized MCP with ${this.tools.length} tools using ${this.actualTransport} transport`);
      }
    } catch (error) {
      if (this.client) {
        await this.client.close().catch(() => {});
        this.client = null;
      }
      throw new Error(`Failed to initialize MCP client: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  }

  [Symbol.iterator](): Iterator<MCPTool> {
    return this.tools[Symbol.iterator]();
  }

  toOpenAITools() {
    return this.tools.map(t => t.toOpenAITool());
  }

  async close(): Promise<void> {
    if (this.client) {
      try {
        await this.client.close();
      } catch (error) {
        if (this.debug) {
          console.warn('Error closing MCP client:', error);
        }
      } finally {
        this.client = null;
        this.tools = [];
      }
    }
  }

  get isConnected(): boolean {
    return this.client !== null;
  }

  get transportType(): string {
    return this.actualTransport || 'not initialized';
  }
}

// Re-export components for backward compatibility
export { MCPTool, MCPToolInfo } from './mcpSse';
export { HTTPStreamingTransport } from './mcpHttpStreaming';