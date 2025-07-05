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

  constructor(url: URL, headers: Record<string, string> = {}) {
    this.url = url;
    this.headers = headers;
  }

  async start(): Promise<void> {
    // Initialize HTTP streaming connection
    // This would establish a chunked transfer-encoding connection
    // For now, this is a placeholder implementation
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
    // Send message through HTTP streaming
    // This would send the message as a chunked HTTP request
    const response = await fetch(this.url.toString(), {
      method: 'POST',
      headers: {
        ...this.headers,
        'Content-Type': 'application/json',
        'Transfer-Encoding': 'chunked'
      },
      body: JSON.stringify(message)
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
  }

  async receive(): Promise<any> {
    if (this.closed) {
      throw new Error('Transport is closed');
    }
    // Receive message from HTTP streaming
    // This would read from the chunked HTTP response stream
    // For now, return a placeholder to prevent runtime errors
    return { jsonrpc: "2.0", id: null, result: {} };
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