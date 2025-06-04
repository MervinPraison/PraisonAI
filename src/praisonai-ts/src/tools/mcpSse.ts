import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { SSEClientTransport } from '@modelcontextprotocol/sdk/client/sse.js';
import { BaseTool } from './index';

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

export class MCP implements Iterable<MCPTool> {
  tools: MCPTool[] = [];
  private client: Client | null = null;

  constructor(private url: string, private debug = false) {
    if (debug) {
      console.log(`MCP client initialized for URL: ${url}`);
    }
  }

  async initialize(): Promise<void> {
    if (this.client) {
      if (this.debug) console.log('MCP client already initialized');
      return;
    }
    
    try {
      this.client = new Client({ name: 'praisonai-ts-mcp', version: '1.0.0' });
      const transport = new SSEClientTransport(new URL(this.url));
      await this.client.connect(transport);
      const { tools } = await this.client.listTools();
      this.tools = tools.map((t: any) => new MCPTool({
        name: t.name,
        description: t.description,
        inputSchema: t.inputSchema
      }, this.client as Client));
      
      if (this.debug) console.log(`Initialized MCP with ${this.tools.length} tools`);
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
}
