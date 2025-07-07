/**
 * HTTP-Streaming transport implementation for MCP (Model Context Protocol).
 * Provides bidirectional streaming over HTTP using chunked transfer encoding.
 */

export interface HTTPStreamingTransportOptions {
  /** Request timeout in milliseconds */
  timeout?: number;
  /** Additional headers to include in requests */
  headers?: Record<string, string>;
  /** Enable debug logging */
  debug?: boolean;
  /** Use fallback mode for browsers without duplex streaming support */
  fallbackMode?: boolean;
}

/**
 * Transport interface expected by MCP SDK
 */
export interface Transport {
  read(): Promise<string | null>;
  write(data: string): Promise<void>;
  close(): Promise<void>;
}

/**
 * HTTP-Streaming transport using modern Fetch API with duplex streaming.
 * Falls back to polling-based approach for older browsers.
 */
export class HTTPStreamingTransport implements Transport {
  private url: URL;
  private options: HTTPStreamingTransportOptions;
  private reader: ReadableStreamDefaultReader<Uint8Array> | null = null;
  private writer: WritableStreamDefaultWriter<Uint8Array> | null = null;
  private encoder = new TextEncoder();
  private decoder = new TextDecoder();
  private buffer = '';
  private closed = false;
  private abortController: AbortController;

  constructor(url: URL, options: HTTPStreamingTransportOptions = {}) {
    this.url = new URL('/mcp/v1/stream', url);
    this.options = {
      timeout: 60000,
      fallbackMode: false,
      debug: false,
      ...options
    };
    this.abortController = new AbortController();
  }

  async connect(): Promise<void> {
    if (this.options.debug) {
      console.log('[HTTPStreamingTransport] Connecting to:', this.url.toString());
    }

    // Check if browser supports duplex streaming
    const supportsDuplex = this.checkDuplexSupport();
    
    if (!supportsDuplex || this.options.fallbackMode) {
      if (this.options.debug) {
        console.log('[HTTPStreamingTransport] Using fallback mode');
      }
      throw new Error('Fallback mode not implemented - use HTTPStreamingTransportFallback');
    }

    try {
      const response = await fetch(this.url.toString(), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/x-ndjson',
          'Transfer-Encoding': 'chunked',
          ...this.options.headers
        },
        // @ts-ignore - duplex is not in standard TypeScript types yet
        duplex: 'half',
        body: new ReadableStream({
          start: (controller) => {
            this.writer = {
              write: async (chunk: Uint8Array) => {
                controller.enqueue(chunk);
              },
              close: async () => {
                controller.close();
              },
              abort: async (reason?: any) => {
                controller.error(reason);
              },
              get closed() { return Promise.resolve(); },
              get ready() { return Promise.resolve(); },
              get desiredSize() { return null; },
              releaseLock: () => {}
            };
          }
        }),
        signal: this.abortController.signal
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      if (!response.body) {
        throw new Error('Response body is null');
      }

      this.reader = response.body.getReader();
      
      if (this.options.debug) {
        console.log('[HTTPStreamingTransport] Connected successfully');
      }
    } catch (error) {
      if (this.options.debug) {
        console.error('[HTTPStreamingTransport] Connection error:', error);
      }
      throw error;
    }
  }

  async read(): Promise<string | null> {
    if (this.closed || !this.reader) {
      return null;
    }

    try {
      // Read chunks until we have a complete message
      while (true) {
        const { done, value } = await this.reader.read();
        
        if (done) {
          this.closed = true;
          return null;
        }

        // Append to buffer
        this.buffer += this.decoder.decode(value, { stream: true });

        // Check for complete messages (newline-delimited)
        const lines = this.buffer.split('\n');
        
        if (lines.length > 1) {
          // We have at least one complete message
          const message = lines[0];
          this.buffer = lines.slice(1).join('\n');
          
          if (message.trim()) {
            if (this.options.debug) {
              console.log('[HTTPStreamingTransport] Read message:', message);
            }
            return message;
          }
        }
      }
    } catch (error) {
      if (this.options.debug) {
        console.error('[HTTPStreamingTransport] Read error:', error);
      }
      this.closed = true;
      return null;
    }
  }

  async write(data: string): Promise<void> {
    if (this.closed || !this.writer) {
      throw new Error('Transport is closed or not connected');
    }

    try {
      const message = data.trim() + '\n';
      const chunk = this.encoder.encode(message);
      
      await this.writer.write(chunk);
      
      if (this.options.debug) {
        console.log('[HTTPStreamingTransport] Wrote message:', data);
      }
    } catch (error) {
      if (this.options.debug) {
        console.error('[HTTPStreamingTransport] Write error:', error);
      }
      throw error;
    }
  }

  async close(): Promise<void> {
    if (this.closed) {
      return;
    }

    this.closed = true;
    this.abortController.abort();

    if (this.reader) {
      try {
        await this.reader.cancel();
      } catch (error) {
        // Ignore errors during cleanup
      }
    }

    if (this.writer) {
      try {
        await this.writer.close();
      } catch (error) {
        // Ignore errors during cleanup
      }
    }

    if (this.options.debug) {
      console.log('[HTTPStreamingTransport] Closed');
    }
  }

  private checkDuplexSupport(): boolean {
    // Check if the browser supports duplex streaming
    // This is a simple heuristic - more sophisticated detection may be needed
    if (typeof ReadableStream === 'undefined' || typeof WritableStream === 'undefined') {
      return false;
    }

    // Check for fetch duplex support (Chrome 105+, Safari 16.5+)
    // This is a best-effort check
    const userAgent = navigator.userAgent.toLowerCase();
    const isChrome = userAgent.includes('chrome') && !userAgent.includes('edge');
    const isSafari = userAgent.includes('safari') && !userAgent.includes('chrome');
    
    if (isChrome) {
      const match = userAgent.match(/chrome\/(\d+)/);
      if (match && parseInt(match[1]) >= 105) {
        return true;
      }
    }
    
    if (isSafari) {
      const match = userAgent.match(/version\/(\d+)/);
      if (match && parseInt(match[1]) >= 16) {
        return true;
      }
    }

    // Default to false for unsupported browsers
    return false;
  }
}

/**
 * Fallback transport for browsers without duplex streaming support.
 * Uses separate connections for reading and writing.
 */
export class HTTPStreamingTransportFallback implements Transport {
  private url: URL;
  private options: HTTPStreamingTransportOptions;
  private sessionId: string;
  private readQueue: string[] = [];
  private writeQueue: string[] = [];
  private closed = false;
  private pollInterval: number | null = null;

  constructor(url: URL, options: HTTPStreamingTransportOptions = {}) {
    this.url = url;
    this.options = {
      timeout: 60000,
      debug: false,
      ...options
    };
    this.sessionId = this.generateSessionId();
  }

  async connect(): Promise<void> {
    if (this.options.debug) {
      console.log('[HTTPStreamingTransportFallback] Connecting with session:', this.sessionId);
    }

    // Start polling for messages
    this.startPolling();

    // Send initial connection message
    await this.sendRequest('connect', {});
  }

  async read(): Promise<string | null> {
    if (this.closed) {
      return null;
    }

    // Wait for messages in the queue
    while (this.readQueue.length === 0 && !this.closed) {
      await new Promise(resolve => setTimeout(resolve, 10));
    }

    if (this.closed) {
      return null;
    }

    const message = this.readQueue.shift();
    
    if (this.options.debug && message) {
      console.log('[HTTPStreamingTransportFallback] Read message:', message);
    }

    return message || null;
  }

  async write(data: string): Promise<void> {
    if (this.closed) {
      throw new Error('Transport is closed');
    }

    // Send message immediately
    await this.sendRequest('message', { data });

    if (this.options.debug) {
      console.log('[HTTPStreamingTransportFallback] Wrote message:', data);
    }
  }

  async close(): Promise<void> {
    if (this.closed) {
      return;
    }

    this.closed = true;

    // Stop polling
    if (this.pollInterval !== null) {
      clearInterval(this.pollInterval);
      this.pollInterval = null;
    }

    // Send disconnect message
    try {
      await this.sendRequest('disconnect', {});
    } catch (error) {
      // Ignore errors during cleanup
    }

    if (this.options.debug) {
      console.log('[HTTPStreamingTransportFallback] Closed');
    }
  }

  private startPolling(): void {
    // Poll for messages every 100ms
    this.pollInterval = window.setInterval(async () => {
      if (this.closed) {
        return;
      }

      try {
        const messages = await this.sendRequest('poll', {});
        if (Array.isArray(messages)) {
          for (const message of messages) {
            if (typeof message === 'string') {
              this.readQueue.push(message);
            } else {
              this.readQueue.push(JSON.stringify(message));
            }
          }
        }
      } catch (error) {
        if (this.options.debug) {
          console.error('[HTTPStreamingTransportFallback] Poll error:', error);
        }
      }
    }, 100);
  }

  private async sendRequest(action: string, payload: any): Promise<any> {
    const response = await fetch(new URL('/mcp/v1/fallback', this.url).toString(), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Session-ID': this.sessionId,
        ...this.options.headers
      },
      body: JSON.stringify({
        action,
        sessionId: this.sessionId,
        payload
      })
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    return response.json();
  }

  private generateSessionId(): string {
    return `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }
}

/**
 * Factory function to create appropriate transport based on browser capabilities.
 */
export function createHTTPStreamingTransport(
  url: URL, 
  options: HTTPStreamingTransportOptions = {}
): Transport {
  const transport = new HTTPStreamingTransport(url, options);
  
  // Try to check duplex support
  try {
    // @ts-ignore
    if (!transport.checkDuplexSupport() || options.fallbackMode) {
      return new HTTPStreamingTransportFallback(url, options);
    }
  } catch (error) {
    // If check fails, use fallback
    return new HTTPStreamingTransportFallback(url, options);
  }

  return transport;
}