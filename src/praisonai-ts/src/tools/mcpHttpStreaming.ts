/**
 * MCP HTTP-Streaming client implementation.
 * Provides HTTP-Streaming transport support for MCP (Model Context Protocol).
 */

import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { createHTTPStreamingTransport, HTTPStreamingTransportOptions } from './httpStreamingTransport';
import { BaseTool } from './index';

/**
 * Configuration options for MCP HTTP-Streaming client.
 */
export interface MCPHttpStreamingOptions extends HTTPStreamingTransportOptions {
  /** MCP client name */
  clientName?: string;
  /** MCP client version */
  clientVersion?: string;
}

/**
 * Represents a single MCP tool that can be executed remotely.
 */
export class MCPTool extends BaseTool {
  private client: Client;
  private toolInfo: {
    name: string;
    description: string;
    inputSchema?: any;
  };

  constructor(toolInfo: { name: string; description: string; inputSchema?: any }, client: Client) {
    super();
    this.toolInfo = toolInfo;
    this.client = client;
  }

  get name(): string {
    return this.toolInfo.name;
  }

  get description(): string {
    return this.toolInfo.description;
  }

  get schemaProperties(): any {
    return this.toolInfo.inputSchema?.properties || {};
  }

  async execute(args: any): Promise<any> {
    try {
      const result = await this.client.callTool({ 
        name: this.toolInfo.name, 
        arguments: args 
      });
      
      // Extract the actual content from the response
      if (result && result.content) {
        // Handle different content types
        if (Array.isArray(result.content)) {
          // If multiple content items, look for text content first
          for (const item of result.content) {
            if (item.type === 'text' && item.text) {
              return item.text;
            }
          }
          // If no text content, return the first item
          if (result.content.length > 0) {
            return result.content[0].text || result.content[0];
          }
        } else if (typeof result.content === 'object' && result.content.text) {
          return result.content.text;
        }
        return result.content;
      }
      
      return result;
    } catch (error) {
      console.error(`Error executing MCP tool ${this.toolInfo.name}:`, error);
      throw error;
    }
  }

  toOpenAITool(): any {
    const parameters = this.toolInfo.inputSchema || {
      type: 'object',
      properties: {},
      required: []
    };

    return {
      type: 'function',
      function: {
        name: this.toolInfo.name,
        description: this.toolInfo.description,
        parameters: parameters
      }
    };
  }
}

/**
 * MCP client using HTTP-Streaming transport.
 * Provides the same interface as MCP SSE client for compatibility.
 */
export class MCPHttpStreaming implements Iterable<MCPTool> {
  tools: MCPTool[] = [];
  private client: Client | null = null;
  private url: string;
  private options: MCPHttpStreamingOptions;

  constructor(url: string, options: MCPHttpStreamingOptions = {}) {
    this.url = url;
    this.options = {
      clientName: 'praisonai-ts-mcp',
      clientVersion: '1.0.0',
      ...options
    };

    if (this.options.debug) {
      console.log(`MCPHttpStreaming client initialized for URL: ${url}`);
    }
  }

  async initialize(): Promise<void> {
    if (this.client) {
      if (this.options.debug) console.log('MCP client already initialized');
      return;
    }

    try {
      // Create MCP client
      this.client = new Client({
        name: this.options.clientName!,
        version: this.options.clientVersion!
      });

      // Create HTTP-Streaming transport
      const transport = createHTTPStreamingTransport(new URL(this.url), this.options);

      // Connect to the server
      await this.client.connect(transport);

      // List available tools
      const { tools } = await this.client.listTools();

      // Create MCPTool instances for each discovered tool
      this.tools = tools.map((t: any) => new MCPTool({
        name: t.name,
        description: t.description,
        inputSchema: t.inputSchema
      }, this.client as Client));

      if (this.options.debug) {
        console.log(`Initialized MCPHttpStreaming with ${this.tools.length} tools using HTTP-Streaming transport`);
      }
    } catch (error) {
      // Clean up on error
      if (this.client) {
        await this.client.close().catch(() => {});
        this.client = null;
      }
      throw new Error(`Failed to initialize MCP HTTP-Streaming client: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  }

  async close(): Promise<void> {
    if (this.client) {
      await this.client.close();
      this.client = null;
      this.tools = [];
    }
  }

  toOpenAITools(): any[] {
    return this.tools.map(tool => tool.toOpenAITool());
  }

  [Symbol.iterator](): Iterator<MCPTool> {
    return this.tools[Symbol.iterator]();
  }

  /**
   * Get connection statistics (if available).
   */
  getStats(): { connected: boolean; toolCount: number; transport: string } {
    return {
      connected: this.client !== null,
      toolCount: this.tools.length,
      transport: 'http-streaming'
    };
  }
}

/**
 * Backward-compatible alias for the main class.
 */
export { MCPHttpStreaming as MCP };

/**
 * Helper function to create and initialize an MCP HTTP-Streaming client.
 */
export async function createMCPHttpStreamingClient(
  url: string, 
  options?: MCPHttpStreamingOptions
): Promise<MCPHttpStreaming> {
  const client = new MCPHttpStreaming(url, options);
  await client.initialize();
  return client;
}