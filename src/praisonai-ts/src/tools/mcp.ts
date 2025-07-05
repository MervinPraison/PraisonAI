import { MCP as MCPSse } from './mcpSse';
import { MCPHttpStreaming } from './mcpHttpStreaming';
import { BaseTool } from './index';

/**
 * Unified MCP client that supports both SSE and HTTP-Streaming transports
 */
export class MCP implements Iterable<BaseTool> {
  private client: MCPSse | MCPHttpStreaming | null = null;
  private transportType: 'sse' | 'http-streaming' | null = null;

  constructor(
    private url: string,
    private options: {
      transport?: 'auto' | 'sse' | 'http-streaming';
      debug?: boolean;
    } = {}
  ) {
    const { transport = 'auto', debug = false } = this.options;

    // Determine transport type
    if (transport === 'auto') {
      // Auto-detect based on URL pattern
      if (url.endsWith('/sse')) {
        this.transportType = 'sse';
      } else {
        this.transportType = 'http-streaming';
      }
    } else if (transport === 'sse' || transport === 'http-streaming') {
      this.transportType = transport;
    } else {
      throw new Error(`Unknown transport type: ${transport}`);
    }

    // Create appropriate client
    if (this.transportType === 'sse') {
      this.client = new MCPSse(url, debug);
    } else {
      this.client = new MCPHttpStreaming(url, debug);
    }
  }

  async initialize(): Promise<void> {
    if (!this.client) {
      throw new Error('MCP client not initialized');
    }
    await this.client.initialize();
  }

  get tools(): BaseTool[] {
    return this.client?.tools || [];
  }

  [Symbol.iterator](): Iterator<BaseTool> {
    return this.tools[Symbol.iterator]();
  }

  toOpenAITools() {
    return this.client?.toOpenAITools() || [];
  }

  async close(): Promise<void> {
    if (this.client) {
      await this.client.close();
      this.client = null;
    }
  }

  get isConnected(): boolean {
    return this.client?.isConnected || false;
  }

  get transport(): string | null {
    return this.transportType;
  }
}

// Export the specific implementations for backward compatibility
export { MCP as MCPSse } from './mcpSse';
export { MCPHttpStreaming } from './mcpHttpStreaming';
export type { MCPTool, MCPToolInfo } from './mcpSse';