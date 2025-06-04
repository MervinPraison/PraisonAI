import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { SSEClientTransport } from '@modelcontextprotocol/sdk/client/sse.js';
import { BaseTool } from './index';

export interface MCPPToolInfo {
  name: string;
  description?: string;
  inputSchema?: any;
}

export class MCPTool extends BaseTool {
  private client: Client;
  private inputSchema: any;

  constructor(info: MCPPToolInfo, client: Client) {
    super(info.name, info.description || `Call the ${info.name} tool`);
    this.client = client;
    this.inputSchema = info.inputSchema || { type: 'object', properties: {}, required: [] };
  }

  async execute(args: any = {}): Promise<any> {
    const result: any = await this.client.callTool({ name: this.name, arguments: args });
    if (result.structuredContent) {
      return result.structuredContent;
    }
    if (Array.isArray(result.content) && result.content.length > 0) {
      const item = result.content[0];
      if (typeof item.text === 'string') return item.text;
    }
    return result;
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

  constructor(private url: string, private debug = false) {}

  async initialize(): Promise<void> {
    this.client = new Client({ name: 'praisonai-ts-mcp', version: '1.0.0' });
    const transport = new SSEClientTransport(new URL(this.url));
    await this.client.connect(transport);
    const { tools } = await this.client.listTools();
    this.tools = tools.map((t: any) => new MCPTool({
      name: t.name,
      description: t.description,
      inputSchema: t.inputSchema
    }, this.client as Client));
  }

  [Symbol.iterator](): Iterator<MCPTool> {
    return this.tools[Symbol.iterator]();
  }

  toOpenAITools() {
    return this.tools.map(t => t.toOpenAITool());
  }
}
