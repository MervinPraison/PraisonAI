/**
 * MCP Session - Session management for MCP connections
 * 
 * Handles lifecycle, state, and context for MCP client/server sessions.
 * 
 * @example
 * ```typescript
 * import { MCPSession } from 'praisonai';
 * 
 * const session = new MCPSession({ id: 'session-1' });
 * session.setContext('user', { name: 'John' });
 * ```
 */

import { randomUUID } from 'crypto';

/**
 * Session state
 */
export type SessionState = 'created' | 'initializing' | 'active' | 'suspended' | 'closed';

/**
 * Session context data
 */
export interface SessionContext {
    [key: string]: any;
}

/**
 * Session event
 */
export interface SessionEvent {
    type: 'created' | 'initialized' | 'suspended' | 'resumed' | 'closed' | 'error' | 'message';
    timestamp: number;
    data?: any;
}

/**
 * Session configuration
 */
export interface MCPSessionConfig {
    /** Session ID (auto-generated if not provided) */
    id?: string;
    /** Session name */
    name?: string;
    /** Initial context */
    context?: SessionContext;
    /** Session timeout in ms */
    timeout?: number;
    /** Enable event logging */
    logging?: boolean;
    /** Parent session ID */
    parentId?: string;
    /** Metadata */
    metadata?: Record<string, any>;
}

/**
 * MCPSession - Manages MCP session lifecycle
 */
export class MCPSession {
    readonly id: string;
    readonly name: string;
    readonly parentId?: string;
    readonly createdAt: number;

    private state: SessionState;
    private context: SessionContext;
    private events: SessionEvent[];
    private timeout: number;
    private logging: boolean;
    private metadata: Record<string, any>;
    private lastActivityAt: number;
    private timeoutHandle?: NodeJS.Timeout;

    constructor(config: MCPSessionConfig = {}) {
        this.id = config.id ?? randomUUID();
        this.name = config.name ?? `session-${this.id.slice(0, 8)}`;
        this.parentId = config.parentId;
        this.createdAt = Date.now();
        this.state = 'created';
        this.context = config.context ?? {};
        this.events = [];
        this.timeout = config.timeout ?? 30 * 60 * 1000; // 30 minutes
        this.logging = config.logging ?? false;
        this.metadata = config.metadata ?? {};
        this.lastActivityAt = this.createdAt;

        this.addEvent('created');
    }

    /**
     * Initialize the session
     */
    async initialize(): Promise<void> {
        if (this.state !== 'created') {
            throw new Error(`Cannot initialize session in state: ${this.state}`);
        }

        this.state = 'initializing';
        this.addEvent('initialized');
        this.state = 'active';
        this.startTimeoutTimer();
    }

    /**
     * Suspend the session
     */
    suspend(): void {
        if (this.state !== 'active') return;

        this.state = 'suspended';
        this.clearTimeoutTimer();
        this.addEvent('suspended');
    }

    /**
     * Resume the session
     */
    resume(): void {
        if (this.state !== 'suspended') return;

        this.state = 'active';
        this.touch();
        this.startTimeoutTimer();
        this.addEvent('resumed');
    }

    /**
     * Close the session
     */
    close(): void {
        if (this.state === 'closed') return;

        this.state = 'closed';
        this.clearTimeoutTimer();
        this.addEvent('closed');
    }

    /**
     * Get session state
     */
    getState(): SessionState {
        return this.state;
    }

    /**
     * Check if session is active
     */
    isActive(): boolean {
        return this.state === 'active';
    }

    /**
     * Set context value
     */
    setContext(key: string, value: any): void {
        this.context[key] = value;
        this.touch();
    }

    /**
     * Get context value
     */
    getContext(key: string): any {
        return this.context[key];
    }

    /**
     * Get all context
     */
    getAllContext(): SessionContext {
        return { ...this.context };
    }

    /**
     * Clear context
     */
    clearContext(): void {
        this.context = {};
        this.touch();
    }

    /**
     * Set metadata
     */
    setMetadata(key: string, value: any): void {
        this.metadata[key] = value;
    }

    /**
     * Get metadata
     */
    getMetadata(key: string): any {
        return this.metadata[key];
    }

    /**
     * Get all events
     */
    getEvents(): SessionEvent[] {
        return [...this.events];
    }

    /**
     * Get session info
     */
    getInfo(): {
        id: string;
        name: string;
        state: SessionState;
        createdAt: number;
        lastActivityAt: number;
        eventCount: number;
        parentId?: string;
    } {
        return {
            id: this.id,
            name: this.name,
            state: this.state,
            createdAt: this.createdAt,
            lastActivityAt: this.lastActivityAt,
            eventCount: this.events.length,
            parentId: this.parentId,
        };
    }

    /**
     * Touch - update last activity time
     */
    private touch(): void {
        this.lastActivityAt = Date.now();
        this.resetTimeoutTimer();
    }

    /**
     * Add event
     */
    private addEvent(type: SessionEvent['type'], data?: any): void {
        const event: SessionEvent = {
            type,
            timestamp: Date.now(),
            data,
        };
        this.events.push(event);

        if (this.logging) {
            console.log(`[MCPSession:${this.id.slice(0, 8)}] ${type}`);
        }
    }

    /**
     * Start timeout timer
     */
    private startTimeoutTimer(): void {
        this.clearTimeoutTimer();
        this.timeoutHandle = setTimeout(() => {
            if (this.state === 'active') {
                this.suspend();
            }
        }, this.timeout);
    }

    /**
     * Reset timeout timer
     */
    private resetTimeoutTimer(): void {
        if (this.state === 'active') {
            this.startTimeoutTimer();
        }
    }

    /**
     * Clear timeout timer
     */
    private clearTimeoutTimer(): void {
        if (this.timeoutHandle) {
            clearTimeout(this.timeoutHandle);
            this.timeoutHandle = undefined;
        }
    }

    /**
     * Export session state
     */
    export(): {
        id: string;
        name: string;
        state: SessionState;
        context: SessionContext;
        metadata: Record<string, any>;
        createdAt: number;
        events: SessionEvent[];
    } {
        return {
            id: this.id,
            name: this.name,
            state: this.state,
            context: this.context,
            metadata: this.metadata,
            createdAt: this.createdAt,
            events: this.events,
        };
    }

    /**
     * Import session state
     */
    static import(data: ReturnType<MCPSession['export']>): MCPSession {
        const session = new MCPSession({
            id: data.id,
            name: data.name,
            context: data.context,
            metadata: data.metadata,
        });
        session.events = data.events;
        return session;
    }
}

/**
 * Session Manager - Manages multiple sessions
 */
export class SessionManager {
    private sessions: Map<string, MCPSession>;
    private logging: boolean;

    constructor(config?: { logging?: boolean }) {
        this.sessions = new Map();
        this.logging = config?.logging ?? false;
    }

    /**
     * Create a new session
     */
    create(config?: MCPSessionConfig): MCPSession {
        const session = new MCPSession({ ...config, logging: this.logging });
        this.sessions.set(session.id, session);
        return session;
    }

    /**
     * Get session by ID
     */
    get(id: string): MCPSession | undefined {
        return this.sessions.get(id);
    }

    /**
     * Get all sessions
     */
    getAll(): MCPSession[] {
        return Array.from(this.sessions.values());
    }

    /**
     * Get active sessions
     */
    getActive(): MCPSession[] {
        return this.getAll().filter(s => s.isActive());
    }

    /**
     * Close session
     */
    close(id: string): boolean {
        const session = this.sessions.get(id);
        if (session) {
            session.close();
            this.sessions.delete(id);
            return true;
        }
        return false;
    }

    /**
     * Close all sessions
     */
    closeAll(): void {
        for (const session of this.sessions.values()) {
            session.close();
        }
        this.sessions.clear();
    }

    /**
     * Get stats
     */
    getStats(): { total: number; active: number; suspended: number; closed: number } {
        let active = 0, suspended = 0, closed = 0;
        for (const session of this.sessions.values()) {
            switch (session.getState()) {
                case 'active': active++; break;
                case 'suspended': suspended++; break;
                case 'closed': closed++; break;
            }
        }
        return { total: this.sessions.size, active, suspended, closed };
    }
}

/**
 * Create a session
 */
export function createMCPSession(config?: MCPSessionConfig): MCPSession {
    return new MCPSession(config);
}

/**
 * Create a session manager
 */
export function createSessionManager(config?: { logging?: boolean }): SessionManager {
    return new SessionManager(config);
}

// Default export
export default MCPSession;
