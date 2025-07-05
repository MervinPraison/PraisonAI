import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { Transport } from '@modelcontextprotocol/sdk/shared/transport.js';
import { MCPTool, MCPToolInfo } from './mcpSse';

interface ToolDefinition {
  name: string;
  description?: string;
  inputSchema?: Record<string, any>;
}

export class HTTPStreamingTransport implements Transport {
  private url: URL;
  private headers: Record<string, string>;
  private closed = false;
  private reader: ReadableStreamDefaultReader<Uint8Array> | null = null;
  private writer: WritableStreamDefaultWriter<Uint8Array> | null = null;
  private messageQueue: Array<any> = [];
  private initialized = false;

  constructor(url: URL, headers: Record<string, string> = {}) {
    this.url = url;
    this.headers = headers;
  }

  async start(): Promise<void> {
    // Minimal implementation: mark as initialized
    this.initialized = true;
  }

  async close(): Promise<void> {
    this.closed = true;
    if (this.reader) {
      await this.reader.cancel();
      this.reader = null;
    }
    if (this.writer) {
      await this.writer.close();
      this.writer = null;
    }
  }

  async send(message: any): Promise<void> {
    if (this.closed) {
      throw new Error('Transport is closed');
    }
    // Minimal implementation: process message locally
    // In a real implementation, this would send via HTTP
    if (message.method === 'initialize') {
      const response = {
        jsonrpc: '2.0',
        id: message.id,
        result: {
          protocolVersion: '0.1.0',
          capabilities: {}
        }
      };
      this.messageQueue.push(response);
    } else if (message.method === 'tools/list') {
      const response = {
        jsonrpc: '2.0',
        id: message.id,
        result: {
          tools: []
        }
      };
      this.messageQueue.push(response);
    }
  }

  async receive(): Promise<any> {
    if (this.closed) {
      throw new Error('Transport is closed');
    }
    // Minimal implementation: return queued messages
    if (this.messageQueue.length > 0) {
      return this.messageQueue.shift();
    }
    // Return empty response if no messages
    return new Promise((resolve) => {
      setTimeout(() => {
        resolve({ jsonrpc: "2.0", id: null, result: {} });
      }, 100);
    });
  }
}

export class MCPHttpStreaming implements Iterable<MCPTool> {
  tools: MCPTool[] = [];
  private client: Client | null = null;

  constructor(private url: string, private debug = false) {
    if (debug) {
      console.log(`MCP HTTP-Streaming client initialized for URL: ${url}`);
    }
  }

  async initialize(): Promise<void> {
    if (this.client) {
      if (this.debug) console.log('MCP HTTP-Streaming client already initialized');
      return;
    }
    
    try {
      this.client = new Client({ name: 'praisonai-ts-mcp', version: '1.0.0' });
      const transport = new HTTPStreamingTransport(new URL(this.url));
      await this.client.connect(transport);
      const { tools } = await this.client.listTools();
      this.tools = tools.map((t: ToolDefinition) => new MCPTool({
        name: t.name,
        description: t.description,
        inputSchema: t.inputSchema
      }, this.client as Client));
      
      if (this.debug) console.log(`Initialized MCP HTTP-Streaming with ${this.tools.length} tools`);
    } catch (error) {
      if (this.client) {
        await this.client.close().catch(() => {});
        this.client = null;
      }
      throw new Error(`Failed to initialize MCP HTTP-Streaming client: ${error instanceof Error ? error.message : 'Unknown error'}`);
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
          console.warn('Error closing MCP HTTP-Streaming client:', error);
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
}