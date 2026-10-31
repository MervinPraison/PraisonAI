import { Memory } from '../../../src/memory/memory';
import { FileMemory } from '../../../src/memory/file-memory';
import * as os from 'os';
import * as path from 'path';

describe('maxEntries validation (#6146)', () => {
  const filePath = path.join(os.tmpdir(), `praisonai-maxentries-${process.pid}.jsonl`);

  it.each([-1, -0.5, -Infinity])('Memory rejects negative maxEntries %p', (n) => {
    expect(() => new Memory({ maxEntries: n })).toThrow(RangeError);
  });

  it.each([-1, -0.5, -Infinity])('FileMemory rejects negative maxEntries %p', (n) => {
    expect(() => new FileMemory({ filePath, maxEntries: n })).toThrow(RangeError);
  });

  it('Memory with maxEntries 0 retains no entries', async () => {
    const m = new Memory({ maxEntries: 0 });
    await m.add('hello', 'user');
    expect(m.getAll()).toHaveLength(0);
  });

  it('Memory with positive maxEntries keeps the newest entries', async () => {
    const m = new Memory({ maxEntries: 2 });
    await m.add('a', 'user');
    await m.add('b', 'user');
    await m.add('c', 'user');
    expect(m.getAll()).toHaveLength(2);
  });
});
