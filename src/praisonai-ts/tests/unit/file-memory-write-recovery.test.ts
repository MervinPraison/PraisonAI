import { promises as fs } from 'fs';
import * as os from 'os';
import * as path from 'path';
import { FileMemory } from '../../src/memory/file-memory';

describe('FileMemory write recovery', () => {
  let tempDir: string;

  beforeEach(async () => {
    tempDir = await fs.mkdtemp(path.join(os.tmpdir(), 'praisonai-write-recovery-'));
  });

  afterEach(async () => {
    jest.restoreAllMocks();
    await fs.rm(tempDir, { recursive: true, force: true });
  });

  test('persists later writes after the filesystem becomes available again', async () => {
    const directory = path.join(tempDir, 'store');
    const unavailableDirectory = path.join(tempDir, 'unavailable');
    await fs.mkdir(directory);
    const filePath = path.join(directory, 'memory.jsonl');
    const memory = new FileMemory({ filePath });
    const initial = await memory.add('Before interruption', 'user');

    await fs.rename(directory, unavailableDirectory);
    await expect(memory.add('During interruption', 'user')).rejects.toMatchObject({ code: 'ENOENT' });
    await fs.rename(unavailableDirectory, directory);

    const recovered = await memory.add('After recovery', 'assistant');
    const reopened = new FileMemory({ filePath });
    expect(await reopened.getAll()).toEqual([initial, recovered]);
  });

  test('preserves each write result and continues queued writes after a rejection', async () => {
    const filePath = path.join(tempDir, 'memory.jsonl');
    const memory = new FileMemory({ filePath });
    const initial = await memory.add('Before interruption', 'user');
    const appendFile = fs.appendFile;
    const failure = new Error('Temporary append failure');
    let releaseFailure!: () => void;
    let notifyAppend!: () => void;
    const blocked = new Promise<void>(resolve => { releaseFailure = resolve; });
    const started = new Promise<void>(resolve => { notifyAppend = resolve; });
    jest.spyOn(fs, 'appendFile').mockImplementationOnce(async () => {
      notifyAppend();
      await blocked;
      throw failure;
    }).mockImplementation(appendFile);

    const failed = memory.add('Failed write', 'user');
    const queued = memory.add('Queued write', 'assistant');
    const settled = Promise.allSettled([failed, queued]);
    await started;
    releaseFailure();
    const [first, second] = await settled;

    expect(first).toEqual({ status: 'rejected', reason: failure });
    expect(second.status).toBe('fulfilled');
    if (second.status !== 'fulfilled') throw second.reason;
    const later = await memory.add('Later write', 'user');
    const reopened = new FileMemory({ filePath });
    expect(await reopened.getAll()).toEqual([initial, second.value, later]);
  });

  test.each([1, 2])('preserves later records after %i partial append failures', async (failures) => {
    const filePath = path.join(tempDir, 'memory.jsonl');
    const memory = new FileMemory({ filePath });
    const initial = await memory.add('Before interruption', 'user');
    const appendFile = fs.appendFile;
    const failure = Object.assign(new Error('Disk full after a partial write'), { code: 'ENOSPC' });
    let attempts = 0;
    jest.spyOn(fs, 'appendFile').mockImplementation(async (file, data, options) => {
      if (attempts++ < failures) {
        // Write an actual unterminated JSON prefix before reporting failure.
        await appendFile(file, String(data).slice(0, 20), options);
        throw failure;
      }
      await appendFile(file, data, options);
    });

    for (let attempt = 0; attempt < failures; attempt++) {
      await expect(memory.add('Interrupted write', 'user')).rejects.toBe(failure);
    }
    const recovered = await memory.add('Recovered write', 'assistant');
    const later = await memory.add('Later write', 'user');
    const reopened = new FileMemory({ filePath });
    expect(await reopened.getAll()).toEqual([initial, recovered, later]);
  });
});
