import { afterEach, beforeEach, describe, expect, it, jest } from '@jest/globals';
import { mkdtemp, mkdir, rm } from 'fs/promises';
import { tmpdir } from 'os';
import { join } from 'path';
import { createFileCache } from '../../../src/cache';

describe('FileCache concurrent list appends', () => {
  let directory: string;
  beforeEach(async () => { directory = await mkdtemp(join(tmpdir(), 'praison-list-')); });
  afterEach(async () => { await rm(directory, { recursive: true, force: true }); });

  it('persists every successful concurrent append in call order', async () => {
    const cache = createFileCache({ cacheDir: directory });
    await cache.listPush('events', 'existing');
    const values = Array.from({ length: 25 }, (_, index) => `event-${index}`);
    await Promise.all(values.map(value => cache.listPush('events', value)));
    const reopened = createFileCache({ cacheDir: directory });
    expect(await reopened.listRange('events', 0)).toEqual(['existing', ...values]);
    expect(await reopened.listLength('events')).toBe(26);
  });

  it('retains each list when different keys receive concurrent appends', async () => {
    const cache = createFileCache({ cacheDir: directory });
    await cache.keys();
    const values = Array.from({ length: 12 }, (_, index) => index + 1);
    await Promise.all(values.flatMap(value => [cache.listPush('left', value), cache.listPush('right', -value)]));
    const reopened = createFileCache({ cacheDir: directory });
    expect(await reopened.listRange('left', 0)).toEqual(values);
    expect(await reopened.listRange('right', 0)).toEqual(values.map(value => -value));
  });

  it('recovers after a failed append without persisting that value', async () => {
    const cache = createFileCache({ cacheDir: directory });
    const blockedFile = join(directory, 'list_events.json');
    await mkdir(blockedFile);
    await expect(cache.listPush('events', 'failed')).rejects.toThrow();
    await rm(blockedFile, { recursive: true });
    await cache.listPush('events', 'retry');
    expect(await cache.listRange('events', 0)).toEqual(['retry']);
  });

  it('continues an already queued append after a transient write failure', async () => {
    const cache = createFileCache({ cacheDir: directory });
    let releaseFailure!: () => void;
    let signalWrite!: () => void;
    const blocked = new Promise<void>(resolve => { releaseFailure = resolve; });
    const writing = new Promise<void>(resolve => { signalWrite = resolve; });
    // Inject one failed public write; the queued retry uses the real filesystem.
    jest.spyOn(cache, 'set').mockImplementationOnce(async () => {
      signalWrite();
      await blocked;
      throw new Error('transient write failure');
    });
    const failed = expect(cache.listPush('events', 'failed')).rejects.toThrow('transient write failure');
    const retry = cache.listPush('events', 'retry');
    await writing;
    releaseFailure();
    await failed;
    await retry;
    const reopened = createFileCache({ cacheDir: directory });
    expect(await reopened.listRange('events', 0)).toEqual(['retry']);
  });

  it('preserves sequential appends and list slicing', async () => {
    const cache = createFileCache({ cacheDir: directory });
    for (const value of [1, 2, 3]) await cache.listPush('events', value);
    expect(await cache.listRange('events', 1, 2)).toEqual([2]);
    expect(await cache.listRange('events', -1)).toEqual([3]);
  });
});
