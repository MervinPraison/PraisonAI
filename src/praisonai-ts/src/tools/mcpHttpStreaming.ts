import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { BaseTool } from './index';
import { Transport } from '@modelcontextprotocol/sdk/shared/transport.js';
import { JSONRPCRequest, JSONRPCResponse } from '@modelcontextprotocol/sdk/types.js';

/**
 * HTTP-Streaming transport implementation for MCP
 */
class HTTPStreamingTransport implements Transport {
  private url: URL;
  private headers: Record<string, string>;
  private requestId = 0;
  private abortController?: AbortController;

  constructor(url: URL, headers?: Record<string, string>) {
    this.url = url;
    this.headers = {
      'Content-Type': 'application/json',
      ...headers
    };
  }

  private getNextId(): number {
    return ++this.requestId;
  }

  async start(): Promise<void> {
    // Initialize transport if needed
    this.abortController = new AbortController();
  }

  async close(): Promise<void> {
    if (this.abortController) {
      this.abortController.abort();
      this.abortController = undefined;
    }
  }

  async send(message: JSONRPCRequest): Promise<void> {
    const response = await fetch(this.url.toString(), {
      method: 'POST',
      headers: this.headers,
      body: JSON.stringify(message),
      signal: this.abortController?.signal
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
  }

  onmessage?: (message: JSONRPCResponse) => void;
  onerror?: (error: Error) => void;
  onclose?: () => void;

  async *getMessages(): AsyncGenerator<JSONRPCResponse> {
    const streamUrl = new URL(this.url.toString());
    if (streamUrl.pathname.includes('/stream')) {
      streamUrl.pathname = streamUrl.pathname.replace('/stream', '/stream/read');
    } else {
      streamUrl.pathname += '/read';
    }

    const response = await fetch(streamUrl.toString(), {
      method: 'GET',
      headers: this.headers,
      signal: this.abortController?.signal
    });

    if (!response.ok || !response.body) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        
        // Process complete lines
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.trim()) {
            try {
              const message = JSON.parse(line) as JSONRPCResponse;
              yield message;
            } catch (e) {
              // Skip invalid JSON
            }
          }
        }
      }

      // Process remaining buffer
      if (buffer.trim()) {
        try {
          const message = JSON.parse(buffer) as JSONRPCResponse;
          yield message;
        } catch (e) {
          // Skip invalid JSON
        }
      }
    } finally {
      reader.releaseLock();
    }
  }

  // Helper method for request-response pattern
  async sendAndReceive(request: any): Promise<any> {
    request.id = this.getNextId();
    await this.send(request);

    // Read from stream until we get our response
    for await (const message of this.getMessages()) {
      if (message.id === request.id) {
        if ('error' in message && message.error) {
          throw new Error(`JSON-RPC error: ${message.error.message}`);
        }
        return message.result;
      }
    }

    throw new Error('No response received');
  }
}

export interface MCPToolInfo {
  name: string;
  description?: string;
  inputSchema?: any;
}

export class MCPTool extends BaseTool {
  private client: Client;
  private inputSchema: any;

  constructor(info: MCPToolInfo, client: Client) {
    super(info.name, info.description || `Call the ${info.name} tool`);
    this.client = client;
    this.inputSchema = info.inputSchema || { type: 'object', properties: {}, required: [] };
  }

  get schemaProperties(): Record<string, any> | undefined {
    return this.inputSchema?.properties;
  }

  async execute(args: any = {}): Promise<any> {
    try {
      const result: any = await this.client.callTool({ name: this.name, arguments: args });
      if (result.structuredContent) {
        return result.structuredContent;
      }
      if (Array.isArray(result.content) && result.content.length > 0) {
        const item = result.content[0];
        if (typeof item.text === 'string') return item.text;
      }
      return result;
    } catch (error) {
      throw new Error(`Failed to execute tool ${this.name}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  toOpenAITool() {
    return {
      type: 'function',
      function: {
        name: this.name,
        description: this.description,
        parameters: this.inputSchema
      }
    };
  }
}

export class MCPHttpStreaming implements Iterable<MCPTool> {
  tools: MCPTool[] = [];
  private client: Client | null = null;
  private transport: HTTPStreamingTransport | null = null;

  constructor(private url: string, private debug = false) {
    if (debug) {
      console.log(`MCP HTTP-Streaming client initialized for URL: ${url}`);
    }
  }

  async initialize(): Promise<void> {
    if (this.client) {
      if (this.debug) console.log('MCP client already initialized');
      return;
    }
    
    try {
      this.client = new Client({ name: 'praisonai-ts-mcp-http', version: '1.0.0' });
      this.transport = new HTTPStreamingTransport(new URL(this.url));
      await this.client.connect(this.transport);
      const { tools } = await this.client.listTools();
      this.tools = tools.map((t: any) => new MCPTool({
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
          console.warn('Error closing MCP client:', error);
        }
      } finally {
        this.client = null;
        this.transport = null;
        this.tools = [];
      }
    }
  }

  get isConnected(): boolean {
    return this.client !== null;
  }
}