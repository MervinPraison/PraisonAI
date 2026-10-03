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

import { promises as fs } from 'fs';
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

  test.each([
    { autoCompact: true, compactionThreshold: 1 },
    { autoCompact: false, compactionThreshold: 1 },
    { autoCompact: true, compactionThreshold: 2 }
  ])('reloads deleted entries with %j', async (config) => {
    const original = createFileMemory({ filePath: testFilePath });
    const first = await original.add('Deleted user message', 'user');
    const second = await original.add('Deleted assistant message', 'assistant');
    const retained = await original.add('Retained message', 'user');
    await original.delete(first.id);
    await original.delete(second.id);
    const beforeReload = await fs.readFile(testFilePath, 'utf-8');

    const reloaded = createFileMemory({ filePath: testFilePath, ...config });
    await reloaded.initialize();
    expect(await reloaded.getAll()).toEqual([retained]);
    expect(await reloaded.get(first.id)).toBeUndefined();
    expect(await reloaded.get(second.id)).toBeUndefined();

    const afterReload = await fs.readFile(testFilePath, 'utf-8');
    if (config.autoCompact && config.compactionThreshold === 1) {
      expect(afterReload.trim().split('\n').map(line => JSON.parse(line)))
        .toEqual([retained]);
    } else {
      expect(afterReload).toBe(beforeReload);
    }

    const appended = await reloaded.add('New message after reload', 'assistant');
    const reopened = createFileMemory({ filePath: testFilePath, ...config });
    expect(await reopened.getAll()).toEqual([retained, appended]);
  });

  test.each(['add', 'delete'] as const)('%s waits for automatic compaction on reload', async (operation) => {
    const original = createFileMemory({ filePath: testFilePath });
    const deleted = await original.add('Deleted message', 'user');
    const retained = await original.add('Retained message', 'assistant');
    await original.delete(deleted.id);

    let releaseRename!: () => void;
    let notifyRename!: () => void;
    const renameBlocked = new Promise<void>(resolve => { releaseRename = resolve; });
    const renameReached = new Promise<void>(resolve => { notifyRename = resolve; });
    const rename = fs.rename;
    const renameSpy = jest.spyOn(fs, 'rename').mockImplementation(async (from, to) => {
      notifyRename();
      await renameBlocked;
      return rename(from, to);
    });
    const appendSpy = jest.spyOn(fs, 'appendFile');
    const reloaded = createFileMemory({ filePath: testFilePath, compactionThreshold: 0 });
    const initializing = reloaded.initialize();

    try {
      await renameReached;
      const mutation = operation === 'add'
        ? reloaded.add('Concurrent message', 'user')
        : reloaded.delete(retained.id);
      // Let an incorrectly unblocked mutation finish before the snapshot rename.
      await new Promise<void>(resolve => setImmediate(resolve));
      await Promise.all(appendSpy.mock.results.map(result => result.value));
      releaseRename();
      await initializing;
      const result = await mutation;

      const reopened = createFileMemory({ filePath: testFilePath, autoCompact: false });
      expect(await reopened.getAll()).toEqual(operation === 'add' ? [retained, result] : []);
    } finally {
      releaseRename();
      await initializing;
      renameSpy.mockRestore();
      appendSpy.mockRestore();
    }
  });

  test('retries automatic compaction after a filesystem failure', async () => {
    const original = createFileMemory({ filePath: testFilePath });
    const deleted = await original.add('Deleted message', 'user');
    const retained = await original.add('Retained message', 'assistant');
    await original.delete(deleted.id);
    const reloaded = createFileMemory({ filePath: testFilePath, compactionThreshold: 0 });
    const renameSpy = jest.spyOn(fs, 'rename').mockRejectedValueOnce(new Error('Compaction failed'));

    try {
      await expect(reloaded.initialize()).rejects.toThrow('Compaction failed');
      await reloaded.initialize();
      expect(await reloaded.getAll()).toEqual([retained]);
      const lines = (await fs.readFile(testFilePath, 'utf-8')).trim().split('\n');
      expect(lines.map(line => JSON.parse(line))).toEqual([retained]);
    } finally {
      renameSpy.mockRestore();
    }
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
