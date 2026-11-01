import { afterEach, beforeEach, describe, expect, it, jest } from '@jest/globals';
import { promises as fs } from 'fs';
import { tmpdir } from 'os';
import { join } from 'path';
import { FileSessionStore, createStoredSession } from '../../../src/session/store';

function gate(): { promise: Promise<void>; release: () => void } {
    let release!: () => void;
    const promise = new Promise<void>(resolve => { release = resolve; });
    return { promise, release };
}

describe('FileSessionStore save ordering', () => {
    let directory: string;
    let filePath: string;

    beforeEach(async () => {
        directory = await fs.mkdtemp(join(tmpdir(), 'praison-session-save-'));
        filePath = join(directory, 'sessions.json');
    });

    afterEach(async () => {
        jest.restoreAllMocks();
        jest.useRealTimers();
        await fs.rm(directory, { recursive: true, force: true });
    });

    function pauseFirstWrite() {
        const entered = gate();
        const blocked = gate();
        const writeFile = fs.writeFile.bind(fs);
        let writes = 0;
        jest.spyOn(fs, 'writeFile').mockImplementation(async (...args: Parameters<typeof fs.writeFile>) => {
            if (++writes === 1) {
                entered.release();
                await blocked.promise;
            }
            return writeFile(...args);
        });
        return { entered: entered.promise, release: blocked.release, writes: () => writes };
    }

    it.each(['set', 'delete', 'clear'] as const)('persists %s during an in-flight save on close', async operation => {
        const store = new FileSessionStore(filePath);
        const first = createStoredSession({ turn: 1 });
        const second = createStoredSession({ turn: 2 });
        await store.set(first);
        const paused = pauseFirstWrite();
        const saving = store.save();
        await paused.entered;
        if (operation === 'set') await store.set(second);
        else if (operation === 'delete') await store.delete(first.id);
        else await store.clear();
        paused.release();
        await saving;
        await store.close();

        const reloaded = new FileSessionStore(filePath);
        await reloaded.load();
        expect((await reloaded.list()).map(session => session.id)).toEqual(operation === 'set' ? [first.id, second.id] : []);
    });

    it('serializes saves so an older snapshot cannot overwrite a newer one', async () => {
        const store = new FileSessionStore(filePath);
        const session = createStoredSession({ turn: 1 });
        await store.set(session);
        const paused = pauseFirstWrite();
        const firstSave = store.save();
        await paused.entered;
        await store.set({ ...session, data: { turn: 2 } });
        const secondSave = store.save();
        await new Promise<void>(resolve => setImmediate(resolve));
        const writesBeforeRelease = paused.writes();
        paused.release();
        await Promise.all([firstSave, secondSave]);
        await store.close();

        const reloaded = new FileSessionStore(filePath);
        await reloaded.load();
        expect(writesBeforeRelease).toBe(1);
        expect((await reloaded.get(session.id))?.data).toEqual({ turn: 2 });
    });

    it('waits for an outstanding save before closing', async () => {
        const store = new FileSessionStore(filePath);
        await store.set(createStoredSession());
        const paused = pauseFirstWrite();
        const saving = store.save();
        await paused.entered;
        let closed = false;
        const closing = store.close().then(() => { closed = true; });
        await new Promise<void>(resolve => setImmediate(resolve));
        const writesBeforeRelease = paused.writes();
        const closedBeforeRelease = closed;
        paused.release();
        await Promise.all([saving, closing]);
        expect(writesBeforeRelease).toBe(1);
        expect(closedBeforeRelease).toBe(false);
    });

    it('does not queue repeated autosaves behind a blocked write', async () => {
        jest.useFakeTimers();
        const store = new FileSessionStore(filePath, { autoSaveInterval: 10 });
        const save = jest.spyOn(store, 'save');
        const first = createStoredSession({ turn: 1 });
        const second = createStoredSession({ turn: 2 });
        await store.set(first);
        const paused = pauseFirstWrite();
        const saving = store.save();
        await paused.entered;
        await store.set(second);
        jest.advanceTimersByTime(100);
        const saveCallsBeforeRelease = save.mock.calls.length;
        paused.release();
        await saving;
        jest.advanceTimersByTime(10);
        const saveCallsAfterRelease = save.mock.calls.length;
        await store.close();

        const reloaded = new FileSessionStore(filePath);
        await reloaded.load();
        expect(saveCallsBeforeRelease).toBe(1);
        expect(saveCallsAfterRelease).toBe(2);
        expect((await reloaded.list()).map(session => session.id)).toEqual([first.id, second.id]);
    });

    it('retries a failed save on close without poisoning later saves', async () => {
        const store = new FileSessionStore(filePath);
        const session = createStoredSession({ turn: 1 });
        await store.set(session);
        jest.spyOn(fs, 'writeFile').mockRejectedValueOnce(new Error('disk unavailable'));
        await expect(store.save()).rejects.toThrow('disk unavailable');
        await store.close();
        const reloaded = new FileSessionStore(filePath);
        await reloaded.load();
        expect((await reloaded.get(session.id))?.data).toEqual({ turn: 1 });
    });
});
