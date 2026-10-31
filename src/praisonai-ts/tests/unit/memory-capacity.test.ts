import { promises as fs } from 'fs';
import * as os from 'os';
import * as path from 'path';
import { Memory, createMemory } from '../../src/memory/memory';
import { FileMemory, createFileMemory } from '../../src/memory/file-memory';

describe('memory capacity', () => {
  const constructors: Array<[string, (maxEntries: number) => Memory | FileMemory]> = [
    ['Memory', maxEntries => createMemory({ maxEntries })],
    ['FileMemory', maxEntries => createFileMemory({ filePath: 'unused-memory.jsonl', maxEntries })],
  ];

  describe.each(constructors)('%s', (_name, create) => {
    test.each([-1, -0.5, -Infinity])('rejects negative maxEntries %s before any add', maxEntries => {
      expect(() => create(maxEntries)).toThrow(RangeError);
      expect(() => create(maxEntries)).toThrow('maxEntries must be non-negative');
    });
  });

  test.each([0, 1])('both stores still enforce capacity %s', async maxEntries => {
    const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'praisonai-capacity-'));
    try {
      const stores = [
        createMemory({ maxEntries }),
        createFileMemory({ filePath: path.join(directory, 'memory.jsonl'), maxEntries }),
      ];
      for (const store of stores) {
        await store.add('first', 'user');
        await store.add('second', 'assistant');
        const entries = await store.getAll();
        expect(entries).toHaveLength(maxEntries);
        if (maxEntries === 1) expect(entries[0].content).toBe('second');
      }
    } finally {
      await fs.rm(directory, { recursive: true, force: true });
    }
  });
});
