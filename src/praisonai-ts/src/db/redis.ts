/**
 * Redis Database Adapter
 * For session state, caching, and pub/sub
 */

export interface RedisConfig {
  url?: string;
  host?: string;
  port?: number;
  password?: string;
  db?: number;
  keyPrefix?: string;
}

export interface RedisAdapter {
  get<T = any>(key: string): Promise<T | null>;
  set<T = any>(key: string, value: T, ttl?: number): Promise<void>;
  delete(key: string): Promise<boolean>;
  exists(key: string): Promise<boolean>;
  keys(pattern: string): Promise<string[]>;
  expire(key: string, seconds: number): Promise<boolean>;
  ttl(key: string): Promise<number>;
  
  // Hash operations
  hget<T = any>(key: string, field: string): Promise<T | null>;
  hset<T = any>(key: string, field: string, value: T): Promise<void>;
  hgetall<T = any>(key: string): Promise<Record<string, T>>;
  hdel(key: string, ...fields: string[]): Promise<number>;
  
  // List operations
  lpush<T = any>(key: string, ...values: T[]): Promise<number>;
  rpush<T = any>(key: string, ...values: T[]): Promise<number>;
  lrange<T = any>(key: string, start: number, stop: number): Promise<T[]>;
  llen(key: string): Promise<number>;
  
  // Pub/Sub
  publish(channel: string, message: string): Promise<number>;
  subscribe(channel: string, callback: (message: string) => void): Promise<void>;
  unsubscribe(channel: string): Promise<void>;
  
  // Connection
  connect(): Promise<void>;
  disconnect(): Promise<void>;
  isConnected(): boolean;
}

/**
 * Redis Adapter using native fetch (for Upstash REST API)
 */
export class UpstashRedisAdapter implements RedisAdapter {
  private url: string;
  private token: string;
  private keyPrefix: string;
  private connected: boolean = false;

  constructor(config: { url: string; token: string; keyPrefix?: string }) {
    this.url = config.url;
    this.token = config.token;
    this.keyPrefix = config.keyPrefix || '';
  }

  private prefixKey(key: string): string {
    return this.keyPrefix ? `${this.keyPrefix}:${key}` : key;
  }

  private async request(command: string[]): Promise<any> {
    const response = await fetch(this.url, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(command)
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Upstash Redis error: ${response.status} - ${error}`);
    }

    const data = await response.json();
    if (data.error) {
      throw new Error(`Redis error: ${data.error}`);
    }
    return data.result;
  }

  async get<T = any>(key: string): Promise<T | null> {
    const result = await this.request(['GET', this.prefixKey(key)]);
    if (result === null) return null;
    try {
      return JSON.parse(result);
    } catch {
      return result as T;
    }
  }

  async set<T = any>(key: string, value: T, ttl?: number): Promise<void> {
    const serialized = typeof value === 'string' ? value : JSON.stringify(value);
    const command = ['SET', this.prefixKey(key), serialized];
    if (ttl) {
      command.push('EX', String(ttl));
    }
    await this.request(command);
  }

  async delete(key: string): Promise<boolean> {
    const result = await this.request(['DEL', this.prefixKey(key)]);
    return result > 0;
  }

  async exists(key: string): Promise<boolean> {
    const result = await this.request(['EXISTS', this.prefixKey(key)]);
    return result > 0;
  }

  async keys(pattern: string): Promise<string[]> {
    const result = await this.request(['KEYS', this.prefixKey(pattern)]);
    return (result || []).map((k: string) => 
      this.keyPrefix ? k.replace(`${this.keyPrefix}:`, '') : k
    );
  }

  async expire(key: string, seconds: number): Promise<boolean> {
    const result = await this.request(['EXPIRE', this.prefixKey(key), String(seconds)]);
    return result === 1;
  }

  async ttl(key: string): Promise<number> {
    return await this.request(['TTL', this.prefixKey(key)]);
  }

  async hget<T = any>(key: string, field: string): Promise<T | null> {
    const result = await this.request(['HGET', this.prefixKey(key), field]);
    if (result === null) return null;
    try {
      return JSON.parse(result);
    } catch {
      return result as T;
    }
  }

  async hset<T = any>(key: string, field: string, value: T): Promise<void> {
    const serialized = typeof value === 'string' ? value : JSON.stringify(value);
    await this.request(['HSET', this.prefixKey(key), field, serialized]);
  }

  async hgetall<T = any>(key: string): Promise<Record<string, T>> {
    const result = await this.request(['HGETALL', this.prefixKey(key)]);
    if (!result || !Array.isArray(result)) return {};
    
    const obj: Record<string, T> = {};
    for (let i = 0; i < result.length; i += 2) {
      try {
        obj[result[i]] = JSON.parse(result[i + 1]);
      } catch {
        obj[result[i]] = result[i + 1];
      }
    }
    return obj;
  }

  async hdel(key: string, ...fields: string[]): Promise<number> {
    return await this.request(['HDEL', this.prefixKey(key), ...fields]);
  }

  async lpush<T = any>(key: string, ...values: T[]): Promise<number> {
    const serialized = values.map(v => typeof v === 'string' ? v : JSON.stringify(v));
    return await this.request(['LPUSH', this.prefixKey(key), ...serialized]);
  }

  async rpush<T = any>(key: string, ...values: T[]): Promise<number> {
    const serialized = values.map(v => typeof v === 'string' ? v : JSON.stringify(v));
    return await this.request(['RPUSH', this.prefixKey(key), ...serialized]);
  }

  async lrange<T = any>(key: string, start: number, stop: number): Promise<T[]> {
    const result = await this.request(['LRANGE', this.prefixKey(key), String(start), String(stop)]);
    return (result || []).map((item: string) => {
      try {
        return JSON.parse(item);
      } catch {
        return item;
      }
    });
  }

  async llen(key: string): Promise<number> {
    return await this.request(['LLEN', this.prefixKey(key)]);
  }

  async publish(channel: string, message: string): Promise<number> {
    return await this.request(['PUBLISH', channel, message]);
  }

  async subscribe(_channel: string, _callback: (message: string) => void): Promise<void> {
    // Upstash REST API doesn't support true pub/sub subscriptions
    throw new Error('Subscribe not supported in REST mode. Use ioredis for pub/sub.');
  }

  async unsubscribe(_channel: string): Promise<void> {
    throw new Error('Unsubscribe not supported in REST mode.');
  }

  async connect(): Promise<void> {
    // Test connection
    await this.request(['PING']);
    this.connected = true;
  }

  async disconnect(): Promise<void> {
    this.connected = false;
  }

  isConnected(): boolean {
    return this.connected;
  }
}

/**
 * In-memory Redis-like adapter for testing
 */
export class MemoryRedisAdapter implements RedisAdapter {
  private store: Map<string, { value: any; expiresAt?: number }> = new Map();
  private hashes: Map<string, Map<string, any>> = new Map();
  private lists: Map<string, any[]> = new Map();
  private subscribers: Map<string, Set<(message: string) => void>> = new Map();
  private connected: boolean = false;

  async get<T = any>(key: string): Promise<T | null> {
    const entry = this.store.get(key);
    if (!entry) return null;
    if (entry.expiresAt && Date.now() > entry.expiresAt) {
      this.store.delete(key);
      return null;
    }
    return entry.value;
  }

  async set<T = any>(key: string, value: T, ttl?: number): Promise<void> {
    this.store.set(key, {
      value,
      expiresAt: ttl ? Date.now() + ttl * 1000 : undefined
    });
  }

  async delete(key: string): Promise<boolean> {
    const existed = this.store.has(key);
    this.store.delete(key);
    this.hashes.delete(key);
    this.lists.delete(key);
    return existed;
  }

  async exists(key: string): Promise<boolean> {
    const entry = this.store.get(key);
    if (!entry) return false;
    if (entry.expiresAt && Date.now() > entry.expiresAt) {
      this.store.delete(key);
      return false;
    }
    return true;
  }

  async keys(pattern: string): Promise<string[]> {
    const regex = new RegExp('^' + pattern.replace(/\*/g, '.*') + '$');
    return Array.from(this.store.keys()).filter(k => regex.test(k));
  }

  async expire(key: string, seconds: number): Promise<boolean> {
    const entry = this.store.get(key);
    if (!entry) return false;
    entry.expiresAt = Date.now() + seconds * 1000;
    return true;
  }

  async ttl(key: string): Promise<number> {
    const entry = this.store.get(key);
    if (!entry) return -2;
    if (!entry.expiresAt) return -1;
    const remaining = Math.ceil((entry.expiresAt - Date.now()) / 1000);
    return remaining > 0 ? remaining : -2;
  }

  async hget<T = any>(key: string, field: string): Promise<T | null> {
    return this.hashes.get(key)?.get(field) ?? null;
  }

  async hset<T = any>(key: string, field: string, value: T): Promise<void> {
    if (!this.hashes.has(key)) {
      this.hashes.set(key, new Map());
    }
    this.hashes.get(key)!.set(field, value);
  }

  async hgetall<T = any>(key: string): Promise<Record<string, T>> {
    const hash = this.hashes.get(key);
    if (!hash) return {};
    return Object.fromEntries(hash.entries());
  }

  async hdel(key: string, ...fields: string[]): Promise<number> {
    const hash = this.hashes.get(key);
    if (!hash) return 0;
    let count = 0;
    for (const field of fields) {
      if (hash.delete(field)) count++;
    }
    return count;
  }

  async lpush<T = any>(key: string, ...values: T[]): Promise<number> {
    if (!this.lists.has(key)) {
      this.lists.set(key, []);
    }
    this.lists.get(key)!.unshift(...values);
    return this.lists.get(key)!.length;
  }

  async rpush<T = any>(key: string, ...values: T[]): Promise<number> {
    if (!this.lists.has(key)) {
      this.lists.set(key, []);
    }
    this.lists.get(key)!.push(...values);
    return this.lists.get(key)!.length;
  }

  async lrange<T = any>(key: string, start: number, stop: number): Promise<T[]> {
    const list = this.lists.get(key) || [];
    const end = stop === -1 ? list.length : stop + 1;
    return list.slice(start, end);
  }

  async llen(key: string): Promise<number> {
    return this.lists.get(key)?.length ?? 0;
  }

  async publish(channel: string, message: string): Promise<number> {
    const subs = this.subscribers.get(channel);
    if (!subs) return 0;
    subs.forEach(cb => cb(message));
    return subs.size;
  }

  async subscribe(channel: string, callback: (message: string) => void): Promise<void> {
    if (!this.subscribers.has(channel)) {
      this.subscribers.set(channel, new Set());
    }
    this.subscribers.get(channel)!.add(callback);
  }

  async unsubscribe(channel: string): Promise<void> {
    this.subscribers.delete(channel);
  }

  async connect(): Promise<void> {
    this.connected = true;
  }

  async disconnect(): Promise<void> {
    this.connected = false;
    this.store.clear();
    this.hashes.clear();
    this.lists.clear();
    this.subscribers.clear();
  }

  isConnected(): boolean {
    return this.connected;
  }
}

// Factory functions
export function createUpstashRedis(config: { url: string; token: string; keyPrefix?: string }): UpstashRedisAdapter {
  return new UpstashRedisAdapter(config);
}

export function createMemoryRedis(): MemoryRedisAdapter {
  return new MemoryRedisAdapter();
}
