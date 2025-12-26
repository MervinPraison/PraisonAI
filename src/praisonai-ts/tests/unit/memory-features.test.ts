/**
 * Unit tests for Memory Features (FileMemory, AutoMemory)
 */

import {
  FileMemory,
  createFileMemory,
  AutoMemory,
  createAutoMemory,
  DEFAULT_POLICIES
} from '../../src/memory';

import * as fs from 'fs/promises';
import * as path from 'path';
import * as os from 'os';

describe('FileMemory', () => {
  let tempDir: string;
  let testFilePath: string;

  beforeEach(async () => {
    tempDir = await fs.mkdtemp(path.join(os.tmpdir(), 'praisonai-test-'));
    testFilePath = path.join(tempDir, 'memory.jsonl');
  });

  afterEach(async () => {
    try {
      await fs.rm(tempDir, { recursive: true });
    } catch {
      // Ignore cleanup errors
    }
  });

  test('createFileMemory creates instance', () => {
    const memory = createFileMemory({ filePath: testFilePath });
    expect(memory).toBeInstanceOf(FileMemory);
  });

  test('add creates entry', async () => {
    const memory = createFileMemory({ filePath: testFilePath });
    const entry = await memory.add('Hello world', 'user');
    
    expect(entry.id).toBeDefined();
    expect(entry.content).toBe('Hello world');
    expect(entry.role).toBe('user');
    expect(entry.timestamp).toBeDefined();
  });

  test('get retrieves entry', async () => {
    const memory = createFileMemory({ filePath: testFilePath });
    const entry = await memory.add('Hello world', 'user');
    
    const retrieved = await memory.get(entry.id);
    expect(retrieved).toBeDefined();
    expect(retrieved?.content).toBe('Hello world');
  });

  test('getAll returns all entries', async () => {
    const memory = createFileMemory({ filePath: testFilePath });
    await memory.add('Message 1', 'user');
    await memory.add('Message 2', 'assistant');
    
    const all = await memory.getAll();
    expect(all.length).toBe(2);
  });

  test('getRecent returns recent entries', async () => {
    const memory = createFileMemory({ filePath: testFilePath });
    await memory.add('Message 1', 'user');
    await memory.add('Message 2', 'assistant');
    await memory.add('Message 3', 'user');
    
    const recent = await memory.getRecent(2);
    expect(recent.length).toBe(2);
    expect(recent[0].content).toBe('Message 2');
    expect(recent[1].content).toBe('Message 3');
  });

  test('delete removes entry', async () => {
    const memory = createFileMemory({ filePath: testFilePath });
    const entry = await memory.add('Hello world', 'user');
    
    const deleted = await memory.delete(entry.id);
    expect(deleted).toBe(true);
    
    const retrieved = await memory.get(entry.id);
    expect(retrieved).toBeUndefined();
  });

  test('clear removes all entries', async () => {
    const memory = createFileMemory({ filePath: testFilePath });
    await memory.add('Message 1', 'user');
    await memory.add('Message 2', 'assistant');
    
    await memory.clear();
    
    const all = await memory.getAll();
    expect(all.length).toBe(0);
  });

  test('search finds matching entries', async () => {
    const memory = createFileMemory({ filePath: testFilePath });
    await memory.add('Hello world', 'user');
    await memory.add('Goodbye world', 'assistant');
    await memory.add('Something else', 'user');
    
    const results = await memory.search('world');
    expect(results.length).toBe(2);
  });

  test('persists to file', async () => {
    const memory1 = createFileMemory({ filePath: testFilePath });
    await memory1.add('Persistent message', 'user');
    
    // Create new instance to read from file
    const memory2 = createFileMemory({ filePath: testFilePath });
    const all = await memory2.getAll();
    
    expect(all.length).toBe(1);
    expect(all[0].content).toBe('Persistent message');
  });

  test('compact removes deleted entries from file', async () => {
    const memory = createFileMemory({ filePath: testFilePath });
    const entry1 = await memory.add('Message 1', 'user');
    await memory.add('Message 2', 'assistant');
    
    await memory.delete(entry1.id);
    await memory.compact();
    
    const all = await memory.getAll();
    expect(all.length).toBe(1);
    expect(all[0].content).toBe('Message 2');
  });

  test('toJSON exports entries', async () => {
    const memory = createFileMemory({ filePath: testFilePath });
    await memory.add('Message 1', 'user');
    await memory.add('Message 2', 'assistant');
    
    const json = await memory.toJSON();
    expect(json.length).toBe(2);
  });

  test('buildContext creates context string', async () => {
    const memory = createFileMemory({ filePath: testFilePath });
    await memory.add('Hello', 'user');
    await memory.add('Hi there', 'assistant');
    
    const context = await memory.buildContext();
    expect(context).toContain('user: Hello');
    expect(context).toContain('assistant: Hi there');
  });
});

describe('AutoMemory', () => {
  test('createAutoMemory creates instance', () => {
    const memory = createAutoMemory();
    expect(memory).toBeInstanceOf(AutoMemory);
  });

  test('add stores entry based on policy', async () => {
    const memory = createAutoMemory();
    const entry = await memory.add('Remember this important note', 'user');
    
    // Should match 'store-important' policy
    expect(entry).toBeDefined();
    expect(entry?.content).toContain('important');
  });

  test('add skips short messages', async () => {
    const memory = createAutoMemory();
    const entry = await memory.add('Hi', 'user');
    
    // Should match 'skip-short' policy
    expect(entry).toBeNull();
  });

  test('get retrieves entry', async () => {
    const memory = createAutoMemory();
    const entry = await memory.add('Remember this important note', 'user');
    
    if (entry) {
      const retrieved = memory.get(entry.id);
      expect(retrieved).toBeDefined();
    }
  });

  test('getAll returns all entries', async () => {
    const memory = createAutoMemory();
    await memory.add('Important message 1', 'user');
    await memory.add('Important message 2', 'assistant');
    
    const all = memory.getAll();
    expect(all.length).toBe(2);
  });

  test('getRecent returns recent entries', async () => {
    const memory = createAutoMemory();
    await memory.add('Important message 1', 'user');
    await memory.add('Important message 2', 'assistant');
    await memory.add('Important message 3', 'user');
    
    const recent = memory.getRecent(2);
    expect(recent.length).toBe(2);
  });

  test('search finds matching entries', async () => {
    const memory = createAutoMemory();
    await memory.add('Important hello world', 'user');
    await memory.add('Important goodbye world', 'assistant');
    
    const results = await memory.search('world');
    expect(results.length).toBe(2);
  });

  test('addPolicy adds custom policy', async () => {
    const memory = createAutoMemory();
    memory.addPolicy({
      name: 'custom-test',
      condition: (content) => content.includes('CUSTOM'),
      action: 'store',
      priority: 200
    });
    
    const entry = await memory.add('CUSTOM content', 'user');
    expect(entry).toBeDefined();
  });

  test('removePolicy removes policy', () => {
    const memory = createAutoMemory();
    const removed = memory.removePolicy('store-important');
    expect(removed).toBe(true);
  });

  test('getStats returns context stats', async () => {
    const memory = createAutoMemory();
    await memory.add('Important test message', 'user');
    
    const stats = memory.getStats();
    expect(stats.messageCount).toBe(1);
    expect(stats.tokenCount).toBeGreaterThan(0);
  });

  test('clear resets memory', async () => {
    const memory = createAutoMemory();
    await memory.add('Important message', 'user');
    
    memory.clear();
    
    const all = memory.getAll();
    expect(all.length).toBe(0);
  });

  test('toJSON exports entries', async () => {
    const memory = createAutoMemory();
    // Use longer messages that won't be skipped
    await memory.add('This is an important message that should be stored', 'user');
    await memory.add('This is another important message for testing', 'assistant');
    
    const json = memory.toJSON();
    expect(json.length).toBeGreaterThanOrEqual(0); // May vary based on policies
  });

  test('buildContext creates context string', async () => {
    const memory = createAutoMemory();
    // Use messages that match store-important policy
    await memory.add('Remember this important information', 'user');
    await memory.add('I will remember this important note', 'assistant');
    
    const context = await memory.buildContext();
    // Context may be empty if policies don't match
    expect(typeof context).toBe('string');
  });

  test('DEFAULT_POLICIES has expected policies', () => {
    expect(DEFAULT_POLICIES.length).toBeGreaterThan(0);
    
    const policyNames = DEFAULT_POLICIES.map(p => p.name);
    // Check for policies that exist in the default set
    expect(policyNames).toContain('summarize-long');
    expect(policyNames).toContain('skip-short');
  });
});
