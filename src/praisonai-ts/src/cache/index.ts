/**
 * Cache System - In-memory and persistent caching for agents
 * Inspired by mastra's cache module
 */

export interface CacheConfig {
  name?: string;
  ttl?: number; // Time to live in milliseconds
  maxSize?: number; // Maximum number of entries
}

export interface CacheEntry<T = any> {
  value: T;
  createdAt: number;
  expiresAt?: number;
}

/**
 * Abstract base class for cache implementations
 */
export abstract class BaseCache {
  readonly name: string;
  
  constructor(config: CacheConfig = {}) {
    this.name = config.name || 'cache';
  }

  abstract get<T = any>(key: string): Promise<T | undefined>;
  abstract set<T = any>(key: string, value: T, ttl?: number): Promise<void>;
  abstract delete(key: string): Promise<boolean>;
  abstract clear(): Promise<void>;
  abstract has(key: string): Promise<boolean>;
  abstract keys(): Promise<string[]>;
  abstract size(): Promise<number>;
  
  // List operations
  abstract listPush<T = any>(key: string, value: T): Promise<void>;
  abstract listLength(key: string): Promise<number>;
  abstract listRange<T = any>(key: string, start: number, end?: number): Promise<T[]>;
}

/**
 * In-memory cache implementation
 */
export class MemoryCache extends BaseCache {
  private cache: Map<string, CacheEntry> = new Map();
  private lists: Map<string, any[]> = new Map();
  private ttl?: number;
  private maxSize?: number;

  constructor(config: CacheConfig = {}) {
    super(config);
    this.ttl = config.ttl;
    this.maxSize = config.maxSize;
  }

  async get<T = any>(key: string): Promise<T | undefined> {
    const entry = this.cache.get(key);
    if (!entry) return undefined;
    
    // Check expiration
    if (entry.expiresAt && Date.now() > entry.expiresAt) {
      this.cache.delete(key);
      return undefined;
    }
    
    return entry.value as T;
  }

  async set<T = any>(key: string, value: T, ttl?: number): Promise<void> {
    // Enforce max size
    if (this.maxSize && this.cache.size >= this.maxSize && !this.cache.has(key)) {
      // Remove oldest entry
      const firstKey = this.cache.keys().next().value;
      if (firstKey) this.cache.delete(firstKey);
    }

    const effectiveTtl = ttl ?? this.ttl;
    const entry: CacheEntry<T> = {
      value,
      createdAt: Date.now(),
      expiresAt: effectiveTtl ? Date.now() + effectiveTtl : undefined
    };
    
    this.cache.set(key, entry);
  }

  async delete(key: string): Promise<boolean> {
    const existed = this.cache.has(key);
    this.cache.delete(key);
    this.lists.delete(key);
    return existed;
  }

  async clear(): Promise<void> {
    this.cache.clear();
    this.lists.clear();
  }

  async has(key: string): Promise<boolean> {
    const entry = this.cache.get(key);
    if (!entry) return false;
    if (entry.expiresAt && Date.now() > entry.expiresAt) {
      this.cache.delete(key);
      return false;
    }
    return true;
  }

  async keys(): Promise<string[]> {
    return Array.from(this.cache.keys());
  }

  async size(): Promise<number> {
    return this.cache.size;
  }

  async listPush<T = any>(key: string, value: T): Promise<void> {
    if (!this.lists.has(key)) {
      this.lists.set(key, []);
    }
    this.lists.get(key)!.push(value);
  }

  async listLength(key: string): Promise<number> {
    return this.lists.get(key)?.length ?? 0;
  }

  async listRange<T = any>(key: string, start: number, end?: number): Promise<T[]> {
    const list = this.lists.get(key) ?? [];
    return list.slice(start, end) as T[];
  }
}

/**
 * File-based cache implementation
 */
export class FileCache extends BaseCache {
  private cacheDir: string;
  private fs: any;
  private path: any;

  constructor(config: CacheConfig & { cacheDir?: string } = {}) {
    super(config);
    this.cacheDir = config.cacheDir || '.cache';
  }

  private async ensureDir(): Promise<void> {
    if (!this.fs) {
      this.fs = await import('fs/promises');
      this.path = await import('path');
    }
    try {
      await this.fs.mkdir(this.cacheDir, { recursive: true });
    } catch {}
  }

  private getFilePath(key: string): string {
    const safeKey = key.replace(/[^a-zA-Z0-9-_]/g, '_');
    return this.path.join(this.cacheDir, `${safeKey}.json`);
  }

  async get<T = any>(key: string): Promise<T | undefined> {
    await this.ensureDir();
    try {
      const data = await this.fs.readFile(this.getFilePath(key), 'utf-8');
      const entry: CacheEntry<T> = JSON.parse(data);
      if (entry.expiresAt && Date.now() > entry.expiresAt) {
        await this.delete(key);
        return undefined;
      }
      return entry.value;
    } catch {
      return undefined;
    }
  }

  async set<T = any>(key: string, value: T, ttl?: number): Promise<void> {
    await this.ensureDir();
    const entry: CacheEntry<T> = {
      value,
      createdAt: Date.now(),
      expiresAt: ttl ? Date.now() + ttl : undefined
    };
    await this.fs.writeFile(this.getFilePath(key), JSON.stringify(entry));
  }

  async delete(key: string): Promise<boolean> {
    await this.ensureDir();
    try {
      await this.fs.unlink(this.getFilePath(key));
      return true;
    } catch {
      return false;
    }
  }

  async clear(): Promise<void> {
    await this.ensureDir();
    try {
      const files = await this.fs.readdir(this.cacheDir);
      await Promise.all(
        files.filter((f: string) => f.endsWith('.json'))
          .map((f: string) => this.fs.unlink(this.path.join(this.cacheDir, f)))
      );
    } catch {}
  }

  async has(key: string): Promise<boolean> {
    return (await this.get(key)) !== undefined;
  }

  async keys(): Promise<string[]> {
    await this.ensureDir();
    try {
      const files = await this.fs.readdir(this.cacheDir);
      return files
        .filter((f: string) => f.endsWith('.json'))
        .map((f: string) => f.replace('.json', ''));
    } catch {
      return [];
    }
  }

  async size(): Promise<number> {
    return (await this.keys()).length;
  }

  async listPush<T = any>(key: string, value: T): Promise<void> {
    const list = (await this.get<T[]>(`list_${key}`)) || [];
    list.push(value);
    await this.set(`list_${key}`, list);
  }

  async listLength(key: string): Promise<number> {
    const list = (await this.get<any[]>(`list_${key}`)) || [];
    return list.length;
  }

  async listRange<T = any>(key: string, start: number, end?: number): Promise<T[]> {
    const list = (await this.get<T[]>(`list_${key}`)) || [];
    return list.slice(start, end);
  }
}

// Factory functions
export function createMemoryCache(config?: CacheConfig): MemoryCache {
  return new MemoryCache(config);
}

export function createFileCache(config?: CacheConfig & { cacheDir?: string }): FileCache {
  return new FileCache(config);
}
