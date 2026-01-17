/**
 * Session Store - Persistent storage for sessions
 * 
 * Provides in-memory and file-based session storage.
 */

import { randomUUID } from 'crypto';

/**
 * Session data for storage
 */
export interface StoredSession {
    id: string;
    name?: string;
    data: Record<string, any>;
    metadata: Record<string, any>;
    createdAt: number;
    updatedAt: number;
    expiresAt?: number;
}

/**
 * Store configuration
 */
export interface SessionStoreConfig {
    /** Storage type */
    type?: 'memory' | 'file';
    /** File path for file storage */
    filePath?: string;
    /** Default TTL in ms */
    defaultTTL?: number;
    /** Auto-save interval for file storage */
    autoSaveInterval?: number;
}

/**
 * Session store interface
 */
export interface ISessionStore {
    get(id: string): Promise<StoredSession | null>;
    set(session: StoredSession): Promise<void>;
    delete(id: string): Promise<boolean>;
    list(): Promise<StoredSession[]>;
    clear(): Promise<void>;
}

/**
 * MemorySessionStore - In-memory session storage
 */
export class MemorySessionStore implements ISessionStore {
    private sessions: Map<string, StoredSession>;
    private defaultTTL?: number;

    constructor(defaultTTL?: number) {
        this.sessions = new Map();
        this.defaultTTL = defaultTTL;
    }

    async get(id: string): Promise<StoredSession | null> {
        const session = this.sessions.get(id);
        if (!session) return null;

        // Check expiration
        if (session.expiresAt && Date.now() > session.expiresAt) {
            this.sessions.delete(id);
            return null;
        }

        return session;
    }

    async set(session: StoredSession): Promise<void> {
        if (!session.expiresAt && this.defaultTTL) {
            session.expiresAt = Date.now() + this.defaultTTL;
        }
        session.updatedAt = Date.now();
        this.sessions.set(session.id, session);
    }

    async delete(id: string): Promise<boolean> {
        return this.sessions.delete(id);
    }

    async list(): Promise<StoredSession[]> {
        const now = Date.now();
        const sessions: StoredSession[] = [];

        for (const [id, session] of this.sessions) {
            if (session.expiresAt && now > session.expiresAt) {
                this.sessions.delete(id);
            } else {
                sessions.push(session);
            }
        }

        return sessions;
    }

    async clear(): Promise<void> {
        this.sessions.clear();
    }
}

/**
 * FileSessionStore - File-based session storage
 */
export class FileSessionStore implements ISessionStore {
    private filePath: string;
    private sessions: Map<string, StoredSession>;
    private defaultTTL?: number;
    private autoSaveInterval?: number;
    private saveTimer?: NodeJS.Timeout;
    private dirty: boolean = false;

    constructor(filePath: string, config?: { defaultTTL?: number; autoSaveInterval?: number }) {
        this.filePath = filePath;
        this.sessions = new Map();
        this.defaultTTL = config?.defaultTTL;
        this.autoSaveInterval = config?.autoSaveInterval;

        if (this.autoSaveInterval) {
            this.saveTimer = setInterval(() => {
                if (this.dirty) this.save();
            }, this.autoSaveInterval);
        }
    }

    async load(): Promise<void> {
        try {
            const fs = await import('fs').then(m => m.promises);
            const data = await fs.readFile(this.filePath, 'utf-8');
            const sessions = JSON.parse(data) as StoredSession[];

            this.sessions.clear();
            const now = Date.now();

            for (const session of sessions) {
                if (!session.expiresAt || now <= session.expiresAt) {
                    this.sessions.set(session.id, session);
                }
            }
        } catch {
            // File doesn't exist or invalid, start fresh
            this.sessions.clear();
        }
    }

    async save(): Promise<void> {
        const fs = await import('fs').then(m => m.promises);
        const sessions = Array.from(this.sessions.values());
        await fs.writeFile(this.filePath, JSON.stringify(sessions, null, 2));
        this.dirty = false;
    }

    async get(id: string): Promise<StoredSession | null> {
        const session = this.sessions.get(id);
        if (!session) return null;

        if (session.expiresAt && Date.now() > session.expiresAt) {
            this.sessions.delete(id);
            this.dirty = true;
            return null;
        }

        return session;
    }

    async set(session: StoredSession): Promise<void> {
        if (!session.expiresAt && this.defaultTTL) {
            session.expiresAt = Date.now() + this.defaultTTL;
        }
        session.updatedAt = Date.now();
        this.sessions.set(session.id, session);
        this.dirty = true;
    }

    async delete(id: string): Promise<boolean> {
        const result = this.sessions.delete(id);
        if (result) this.dirty = true;
        return result;
    }

    async list(): Promise<StoredSession[]> {
        const now = Date.now();
        const sessions: StoredSession[] = [];

        for (const [id, session] of this.sessions) {
            if (session.expiresAt && now > session.expiresAt) {
                this.sessions.delete(id);
                this.dirty = true;
            } else {
                sessions.push(session);
            }
        }

        return sessions;
    }

    async clear(): Promise<void> {
        this.sessions.clear();
        this.dirty = true;
    }

    async close(): Promise<void> {
        if (this.saveTimer) {
            clearInterval(this.saveTimer);
        }
        if (this.dirty) {
            await this.save();
        }
    }
}

/**
 * Create session store
 */
export function createSessionStore(config?: SessionStoreConfig): ISessionStore {
    if (config?.type === 'file' && config.filePath) {
        return new FileSessionStore(config.filePath, config);
    }
    return new MemorySessionStore(config?.defaultTTL);
}

/**
 * Create new stored session
 */
export function createStoredSession(data?: Record<string, any>, metadata?: Record<string, any>): StoredSession {
    return {
        id: randomUUID(),
        data: data ?? {},
        metadata: metadata ?? {},
        createdAt: Date.now(),
        updatedAt: Date.now(),
    };
}

// Default export
export default { MemorySessionStore, FileSessionStore, createSessionStore };
