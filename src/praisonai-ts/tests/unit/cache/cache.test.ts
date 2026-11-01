/**
 * Cache System Unit Tests
 */

import { MemoryCache, FileCache, createMemoryCache, createFileCache } from '../../../src/cache';
import { mkdtemp, rm } from 'fs/promises';
import { tmpdir } from 'os';
import { join } from 'path';

describe('MemoryCache', () => {
  let cache: MemoryCache;

  beforeEach(() => {
    cache = new MemoryCache();
  });

  describe('basic operations', () => {
    it('should set and get values', async () => {
      await cache.set('key1', 'value1');
      const result = await cache.get('key1');
      expect(result).toBe('value1');
    });

    it('should return undefined for missing keys', async () => {
      const result = await cache.get('nonexistent');
      expect(result).toBeUndefined();
    });

    it('should delete values', async () => {
      await cache.set('key1', 'value1');
      const deleted = await cache.delete('key1');
      expect(deleted).toBe(true);
      expect(await cache.get('key1')).toBeUndefined();
    });

    it('should check if key exists', async () => {
      await cache.set('key1', 'value1');
      expect(await cache.has('key1')).toBe(true);
      expect(await cache.has('nonexistent')).toBe(false);
    });

    it('should clear all values', async () => {
      await cache.set('key1', 'value1');
      await cache.set('key2', 'value2');
      await cache.clear();
      expect(await cache.size()).toBe(0);
    });

    it('should return all keys', async () => {
      await cache.set('key1', 'value1');
      await cache.set('key2', 'value2');
      const keys = await cache.keys();
      expect(keys).toContain('key1');
      expect(keys).toContain('key2');
    });

    it('should return size', async () => {
      await cache.set('key1', 'value1');
      await cache.set('key2', 'value2');
      expect(await cache.size()).toBe(2);
    });
  });

  describe('TTL (time to live)', () => {
    it('should expire values after TTL', async () => {
      const shortCache = new MemoryCache({ ttl: 50 });
      await shortCache.set('key1', 'value1');
      
      // Should exist immediately
      expect(await shortCache.get('key1')).toBe('value1');
      
      // Wait for expiration
      await new Promise(r => setTimeout(r, 60));
      expect(await shortCache.get('key1')).toBeUndefined();
    });

    it('should allow per-key TTL override', async () => {
      await cache.set('key1', 'value1', 50);
      expect(await cache.get('key1')).toBe('value1');
      
      await new Promise(r => setTimeout(r, 60));
      expect(await cache.get('key1')).toBeUndefined();
    });
  });

  describe('max size', () => {
    it('should enforce max size by removing oldest', async () => {
      const limitedCache = new MemoryCache({ maxSize: 2 });
      await limitedCache.set('key1', 'value1');
      await limitedCache.set('key2', 'value2');
      await limitedCache.set('key3', 'value3');
      
      expect(await limitedCache.size()).toBe(2);
      expect(await limitedCache.get('key1')).toBeUndefined();
      expect(await limitedCache.get('key2')).toBe('value2');
      expect(await limitedCache.get('key3')).toBe('value3');
    });
  });

  describe('list operations', () => {
    it('should push to list', async () => {
      await cache.listPush('mylist', 'item1');
      await cache.listPush('mylist', 'item2');
      expect(await cache.listLength('mylist')).toBe(2);
    });

    it('should get list range', async () => {
      await cache.listPush('mylist', 'a');
      await cache.listPush('mylist', 'b');
      await cache.listPush('mylist', 'c');
      
      const range = await cache.listRange('mylist', 0, 2);
      expect(range).toEqual(['a', 'b']);
    });

    it('should return empty array for nonexistent list', async () => {
      expect(await cache.listLength('nonexistent')).toBe(0);
      expect(await cache.listRange('nonexistent', 0)).toEqual([]);
    });
  });
});

describe('FileCache', () => {
  let cache: FileCache;
  const testDir = '/tmp/praisonai-test-cache-' + Date.now();

  beforeEach(() => {
    cache = new FileCache({ cacheDir: testDir });
  });

  afterEach(async () => {
    await cache.clear();
  });

  it('should set and get values', async () => {
    await cache.set('key1', { data: 'test' });
    const result = await cache.get<{ data: string }>('key1');
    expect(result?.data).toBe('test');
  });

  it('should return undefined for missing keys', async () => {
    const result = await cache.get('nonexistent');
    expect(result).toBeUndefined();
  });

  it('should delete values', async () => {
    await cache.set('key1', 'value1');
    await cache.delete('key1');
    expect(await cache.get('key1')).toBeUndefined();
  });
});

describe('Factory functions', () => {
  it('should create MemoryCache', () => {
    const cache = createMemoryCache({ ttl: 1000 });
    expect(cache).toBeInstanceOf(MemoryCache);
  });

  it('should create FileCache', () => {
    const cache = createFileCache({ cacheDir: '/tmp/test' });
    expect(cache).toBeInstanceOf(FileCache);
  });
});

describe('FileCache default TTL', () => {
  let cacheDir: string;
  let now: number;

  beforeEach(async () => {
    cacheDir = await mkdtemp(join(tmpdir(), 'praisonai-file-cache-ttl-'));
    now = 1000;
    jest.spyOn(Date, 'now').mockImplementation(() => now);
  });

  afterEach(async () => {
    jest.restoreAllMocks();
    await rm(cacheDir, { recursive: true, force: true });
  });

  it.each(['get', 'has'] as const)('honors the configured TTL through %s after reopening', async (method) => {
    const cache = createFileCache({ cacheDir, ttl: 50 });
    await cache.set('answer', 'old answer');
    expect(await cache.get('answer')).toBe('old answer');

    const reopened = new FileCache({ cacheDir });
    now += 51;
    if (method === 'get') {
      expect(await reopened.get('answer')).toBeUndefined();
    } else {
      expect(await reopened.has('answer')).toBe(false);
    }
    expect(await reopened.keys()).not.toContain('answer');
  });

  it('allows a per-entry TTL to override the configured TTL', async () => {
    const cache = new FileCache({ cacheDir, ttl: 50 });
    await cache.set('answer', 'value', 100);
    now += 51;
    expect(await cache.get('answer')).toBe('value');
    now += 50;
    expect(await cache.get('answer')).toBeUndefined();
  });

  it('allows an explicit zero TTL to disable the configured expiry', async () => {
    const cache = new FileCache({ cacheDir, ttl: 50 });
    await cache.set('answer', 'value', 0);
    now += 1000;
    expect(await cache.get('answer')).toBe('value');
  });

  it('keeps entries without a default or explicit TTL', async () => {
    const cache = new FileCache({ cacheDir });
    await cache.set('answer', 'value');
    now += 1000;
    expect(await cache.get('answer')).toBe('value');
  });
});
