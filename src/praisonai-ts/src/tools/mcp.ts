/**
 * Unified MCP client with transport selection support.
 * Provides automatic detection and explicit transport selection for SSE and HTTP-Streaming.
 */

import { MCP as MCPSse } from './mcpSse';
import { MCPHttpStreaming } from './mcpHttpStreaming';
import { MCPTool } from './mcpSse';
import { BaseTool } from './index';

export type TransportType = 'sse' | 'http-streaming' | 'http' | 'auto';

export interface MCPOptions {
  /** Enable debug logging */
  debug?: boolean;
  /** Explicit transport type selection */
  transport?: TransportType;
  /** Request timeout in milliseconds */
  timeout?: number;
  /** Additional headers for HTTP requests */
  headers?: Record<string, string>;
  /** MCP client name */
  clientName?: string;
  /** MCP client version */
  clientVersion?: string;
}

/**
 * Unified MCP client that supports both SSE and HTTP-Streaming transports.
 * Automatically detects the appropriate transport based on URL patterns,
 * or allows explicit transport selection.
 */
export class MCP implements Iterable<MCPTool> {
  tools: MCPTool[] = [];
  private client: MCPSse | MCPHttpStreaming | null = null;
  private url: string;
  private transportType: 'sse' | 'http-streaming';
  private options: MCPOptions;

  constructor(url: string, options: MCPOptions = {}) {
    this.url = url;
    this.options = {
      transport: 'auto',
      debug: false,
      ...options
    };

    // Detect transport type
    this.transportType = this.detectTransport(url, this.options.transport);

    if (this.options.debug) {
      console.log(`MCP client initialized for URL: ${url} with transport: ${this.transportType}`);
    }
  }

  /**
   * Detect the appropriate transport based on URL pattern or explicit selection.
   */
  private detectTransport(url: string, explicitTransport?: TransportType): 'sse' | 'http-streaming' {
    // If explicit transport is provided and not 'auto', use it
    if (explicitTransport && explicitTransport !== 'auto') {
      // Normalize 'http' to 'http-streaming'
      return explicitTransport === 'sse' ? 'sse' : 'http-streaming';
    }

    // Auto-detect based on URL pattern
    const ssePatterns = [
      /\/sse$/i,
      /\/sse\//i,
      /\/events$/i,
      /\/stream$/i,
      /\/server-sent-events/i,
      /[?&]transport=sse/i,
    ];

    for (const pattern of ssePatterns) {
      if (pattern.test(url)) {
        return 'sse';
      }
    }

    // Default to HTTP-Streaming transport
    return 'http-streaming';
  }

  /**
   * Initialize the MCP client with the selected transport.
   */
  async initialize(): Promise<void> {
    if (this.client) {
      if (this.options.debug) console.log('MCP client already initialized');
      return;
    }

    try {
      // Create appropriate client based on transport type
      if (this.transportType === 'sse') {
        this.client = new MCPSse(this.url, this.options.debug);
      } else {
        this.client = new MCPHttpStreaming(this.url, {
          debug: this.options.debug,
          timeout: this.options.timeout,
          headers: this.options.headers,
          clientName: this.options.clientName,
          clientVersion: this.options.clientVersion
        });
      }

      // Initialize the client
      await this.client.initialize();

      // Copy tools from the client
      this.tools = [...this.client.tools];

      if (this.options.debug) {
        console.log(`Initialized MCP with ${this.tools.length} tools using ${this.transportType} transport`);
      }
    } catch (error) {
      // Clean up on error
      if (this.client) {
        await this.client.close().catch(() => {});
        this.client = null;
      }
      throw error;
    }
  }

  /**
   * Close the MCP client connection.
   */
  async close(): Promise<void> {
    if (this.client) {
      await this.client.close();
      this.client = null;
      this.tools = [];
    }
  }

  /**
   * Convert all tools to OpenAI function calling format.
   */
  toOpenAITools(): any[] {
    if (this.client) {
      return this.client.toOpenAITools();
    }
    return [];
  }

  /**
   * Make MCP instance iterable for easy tool access.
   */
  [Symbol.iterator](): Iterator<MCPTool> {
    return this.tools[Symbol.iterator]();
  }

  /**
   * Get the current transport type being used.
   */
  getTransportType(): 'sse' | 'http-streaming' {
    return this.transportType;
  }

  /**
   * Get connection statistics.
   */
  getStats(): { connected: boolean; toolCount: number; transport: string } {
    return {
      connected: this.client !== null,
      toolCount: this.tools.length,
      transport: this.transportType
    };
  }
}

// Export related types and classes for convenience
export { MCPTool } from './mcpSse';
export { MCPSse } from './mcpSse';
export { MCPHttpStreaming } from './mcpHttpStreaming';
export { HTTPStreamingTransportOptions } from './httpStreamingTransport';

/**
 * Helper function to create and initialize an MCP client with automatic transport detection.
 */
export async function createMCPClient(url: string, options?: MCPOptions): Promise<MCP> {
  const client = new MCP(url, options);
  await client.initialize();
  return client;
}