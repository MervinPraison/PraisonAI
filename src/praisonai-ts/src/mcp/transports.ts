/**
 * MCP Transports - Transport implementations for MCP
 * 
 * Provides WebSocket, SSE, and HTTP streaming transports.
 */

import { randomUUID } from 'crypto';

/**
 * Transport message
 */
export interface TransportMessage {
    jsonrpc: '2.0';
    id?: string | number;
    method?: string;
    params?: any;
    result?: any;
    error?: { code: number; message: string; data?: any };
}

/**
 * Transport interface
 */
export interface MCPTransport {
    /** Transport type */
    readonly type: string;
    /** Connection status */
    isConnected(): boolean;
    /** Connect to server */
    connect(): Promise<void>;
    /** Disconnect */
    disconnect(): Promise<void>;
    /** Send message */
    send(message: TransportMessage): Promise<TransportMessage | void>;
    /** Set message handler */
    onMessage(handler: (message: TransportMessage) => void): void;
    /** Set error handler */
    onError(handler: (error: Error) => void): void;
}

/**
 * WebSocket Transport
 */
export class WebSocketTransport implements MCPTransport {
    readonly type = 'websocket';
    private url: string;
    private ws: any = null;
    private connected: boolean = false;
    private messageHandler?: (message: TransportMessage) => void;
    private errorHandler?: (error: Error) => void;
    private pendingRequests: Map<string, { resolve: Function; reject: Function }>;

    constructor(url: string) {
        this.url = url;
        this.pendingRequests = new Map();
    }

    isConnected(): boolean {
        return this.connected;
    }

    async connect(): Promise<void> {
        if (this.connected) return;

        // Lazy load ws (optional dependency)
        // @ts-ignore - optional dependency may not have types
        const wsModule = await import('ws').catch(() => null);
        if (!wsModule) {
            throw new Error('WebSocket transport requires ws package. Run: npm install ws');
        }
        const WebSocket = wsModule.default;

        this.ws = new WebSocket(this.url);

        await new Promise<void>((resolve, reject) => {
            this.ws.on('open', () => {
                this.connected = true;
                resolve();
            });
            this.ws.on('error', (err: Error) => reject(err));
        });

        this.ws.on('message', (data: Buffer | string) => {
            try {
                const message = JSON.parse(data.toString()) as TransportMessage;

                // Handle response
                if (message.id && this.pendingRequests.has(String(message.id))) {
                    const { resolve, reject } = this.pendingRequests.get(String(message.id))!;
                    this.pendingRequests.delete(String(message.id));
                    if (message.error) {
                        reject(new Error(message.error.message));
                    } else {
                        resolve(message);
                    }
                }

                // Call message handler
                this.messageHandler?.(message);
            } catch (e) {
                this.errorHandler?.(e as Error);
            }
        });

        this.ws.on('error', (err: Error) => this.errorHandler?.(err));
        this.ws.on('close', () => { this.connected = false; });
    }

    async disconnect(): Promise<void> {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
            this.connected = false;
        }
    }

    async send(message: TransportMessage): Promise<TransportMessage> {
        if (!this.connected || !this.ws) {
            throw new Error('Not connected');
        }

        const id = message.id ?? randomUUID();
        const msg = { ...message, id };

        return new Promise((resolve, reject) => {
            this.pendingRequests.set(String(id), { resolve, reject });
            this.ws.send(JSON.stringify(msg));
        });
    }

    onMessage(handler: (message: TransportMessage) => void): void {
        this.messageHandler = handler;
    }

    onError(handler: (error: Error) => void): void {
        this.errorHandler = handler;
    }
}

/**
 * SSE (Server-Sent Events) Transport
 */
export class SSETransport implements MCPTransport {
    readonly type = 'sse';
    private url: string;
    private apiKey?: string;
    private connected: boolean = false;
    private eventSource: any = null;
    private messageHandler?: (message: TransportMessage) => void;
    private errorHandler?: (error: Error) => void;

    constructor(url: string, apiKey?: string) {
        this.url = url;
        this.apiKey = apiKey;
    }

    isConnected(): boolean {
        return this.connected;
    }

    async connect(): Promise<void> {
        if (this.connected) return;

        // Use native EventSource if available, otherwise use eventsource package
        // @ts-ignore - browser global or optional dependency
        const EventSourceClass = typeof EventSource !== 'undefined'
            ? EventSource
            // @ts-ignore - optional dependency
            : (await import('eventsource').catch(() => null))?.default;

        if (!EventSourceClass) {
            throw new Error('SSE transport requires eventsource package in Node.js. Run: npm install eventsource');
        }

        const headers: Record<string, string> = {};
        if (this.apiKey) {
            headers['Authorization'] = `Bearer ${this.apiKey}`;
        }

        // @ts-ignore - compatible API
        this.eventSource = new EventSourceClass(this.url, { headers } as any);

        await new Promise<void>((resolve, reject) => {
            this.eventSource.onopen = () => {
                this.connected = true;
                resolve();
            };
            this.eventSource.onerror = (e: Event) => {
                if (!this.connected) reject(new Error('SSE connection failed'));
            };
        });

        this.eventSource.onmessage = (event: MessageEvent) => {
            try {
                const message = JSON.parse(event.data) as TransportMessage;
                this.messageHandler?.(message);
            } catch (e) {
                this.errorHandler?.(e as Error);
            }
        };

        this.eventSource.onerror = (e: Event) => {
            this.errorHandler?.(new Error('SSE error'));
        };
    }

    async disconnect(): Promise<void> {
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
            this.connected = false;
        }
    }

    async send(message: TransportMessage): Promise<void> {
        // SSE is receive-only, send via HTTP POST
        const response = await fetch(this.url.replace('/sse', '/message'), {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(this.apiKey ? { 'Authorization': `Bearer ${this.apiKey}` } : {}),
            },
            body: JSON.stringify(message),
        });

        if (!response.ok) {
            throw new Error(`SSE send failed: ${response.status}`);
        }
    }

    onMessage(handler: (message: TransportMessage) => void): void {
        this.messageHandler = handler;
    }

    onError(handler: (error: Error) => void): void {
        this.errorHandler = handler;
    }
}

/**
 * HTTP Streaming Transport
 */
export class HTTPStreamTransport implements MCPTransport {
    readonly type = 'http-stream';
    private url: string;
    private apiKey?: string;
    private connected: boolean = false;
    private abortController: AbortController | null = null;
    private messageHandler?: (message: TransportMessage) => void;
    private errorHandler?: (error: Error) => void;

    constructor(url: string, apiKey?: string) {
        this.url = url;
        this.apiKey = apiKey;
    }

    isConnected(): boolean {
        return this.connected;
    }

    async connect(): Promise<void> {
        if (this.connected) return;

        this.abortController = new AbortController();
        this.connected = true;
    }

    async disconnect(): Promise<void> {
        if (this.abortController) {
            this.abortController.abort();
            this.abortController = null;
        }
        this.connected = false;
    }

    async send(message: TransportMessage): Promise<TransportMessage> {
        if (!this.connected) {
            throw new Error('Not connected');
        }

        const response = await fetch(this.url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(this.apiKey ? { 'Authorization': `Bearer ${this.apiKey}` } : {}),
            },
            body: JSON.stringify(message),
            signal: this.abortController?.signal,
        });

        if (!response.ok) {
            throw new Error(`HTTP request failed: ${response.status}`);
        }

        const result = await response.json();
        return result as TransportMessage;
    }

    onMessage(handler: (message: TransportMessage) => void): void {
        this.messageHandler = handler;
    }

    onError(handler: (error: Error) => void): void {
        this.errorHandler = handler;
    }
}

/**
 * Create transport by type
 */
export function createTransport(
    type: 'websocket' | 'sse' | 'http-stream',
    url: string,
    options?: { apiKey?: string }
): MCPTransport {
    switch (type) {
        case 'websocket':
            return new WebSocketTransport(url);
        case 'sse':
            return new SSETransport(url, options?.apiKey);
        case 'http-stream':
            return new HTTPStreamTransport(url, options?.apiKey);
        default:
            throw new Error(`Unknown transport type: ${type}`);
    }
}

// Default exports
export default {
    WebSocketTransport,
    SSETransport,
    HTTPStreamTransport,
    createTransport,
};
