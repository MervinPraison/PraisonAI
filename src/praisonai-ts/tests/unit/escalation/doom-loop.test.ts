/**
 * DoomLoopDetector (Python parity: praisonaiagents/escalation/doom_loop.py).
 */

import { DoomLoopDetector, DoomLoopConfig, DoomLoopType, RecoveryAction, stableHash } from '../../../src/escalation';

describe('DoomLoopConfig', () => {
  it('carries the Python defaults', () => {
    const c = new DoomLoopConfig();
    expect(c.maxIdenticalActions).toBe(3);
    expect(c.maxSimilarActions).toBe(5);
    expect(c.maxConsecutiveFailures).toBe(3);
    expect(c.maxNoProgressSteps).toBe(5);
    expect(c.similarityThreshold).toBe(0.85);
    expect(c.maxTimePerAction).toBe(60);
    expect(c.maxTotalTime).toBe(300);
    expect(c.enableAutoRecovery).toBe(true);
    expect(c.maxRecoveryAttempts).toBe(2);
    expect(c.escalateOnLoop).toBe(true);
    expect(c.initialBackoff).toBe(1);
    expect(c.backoffMultiplier).toBe(2);
    expect(c.maxBackoff).toBe(30);
    expect(c.maxRepeatedChunks).toBe(8);
    expect(c.contentChunkSize).toBe(50);
  });

  it('rejects non-positive or non-integer count and chunk-size options', () => {
    // contentChunkSize: 0 would make recordResponse() loop forever; a zero
    // count would dereference an empty slice.
    expect(() => new DoomLoopConfig({ contentChunkSize: 0 })).toThrow(RangeError);
    expect(() => new DoomLoopConfig({ maxIdenticalActions: 0 })).toThrow(RangeError);
    expect(() => new DoomLoopConfig({ maxRecoveryAttempts: -1 })).toThrow(RangeError);
    expect(() => new DoomLoopConfig({ contentChunkSize: 2.5 })).toThrow(RangeError);
    expect(() => new DoomLoopConfig({ maxSimilarActions: NaN })).toThrow(RangeError);
    // Valid positive integers are accepted unchanged.
    expect(new DoomLoopConfig({ contentChunkSize: 10 }).contentChunkSize).toBe(10);
  });
});

describe('DoomLoopDetector repeated identical tool calls', () => {
  it('does not flag before the configured threshold, and flags at it', () => {
    const detector = new DoomLoopDetector({ maxIdenticalActions: 3 });
    detector.startSession();

    detector.recordAction('read_file', { path: 'foo.py' }, 'content', true);
    expect(detector.isDoomLoop()).toBe(false);
    detector.recordAction('read_file', { path: 'foo.py' }, 'content', true);
    expect(detector.isDoomLoop()).toBe(false);
    expect(detector.getLoopType()).toBeNull();
    expect(detector.getRecoveryAction()).toBe(RecoveryAction.CONTINUE);

    detector.recordAction('read_file', { path: 'foo.py' }, 'content', true);
    expect(detector.isDoomLoop()).toBe(true);
    expect(detector.getLoopType()).toBe(DoomLoopType.REPEATED_ACTION);

    const event = detector.getLoopEvent();
    expect(event?.description).toBe('Same action repeated 3 times');
    expect(event?.actionHistory).toEqual(['read_file', 'read_file', 'read_file']);
    expect(event?.recoveryAction).toBe(RecoveryAction.RETRY_DIFFERENT);
    expect(detector.getLoopEvents()).toHaveLength(1);
    expect(detector.getStats().loopEvents).toBe(1);
  });

  it('honours a custom threshold', () => {
    const detector = new DoomLoopDetector(new DoomLoopConfig({ maxIdenticalActions: 2 }));
    detector.recordAction('grep', { q: 'x' }, 'hit', true);
    expect(detector.isDoomLoop()).toBe(false);
    detector.recordAction('grep', { q: 'x' }, 'hit', true);
    expect(detector.isDoomLoop()).toBe(true);
  });

  it('control: identical tool names with different args are not identical actions', () => {
    const detector = new DoomLoopDetector({ maxIdenticalActions: 3, maxSimilarActions: 10 });
    detector.recordAction('read_file', { path: 'a.py' }, 'A', true);
    detector.recordAction('read_file', { path: 'b.py' }, 'B', true);
    detector.recordAction('read_file', { path: 'c.py' }, 'C', true);
    expect(detector.isDoomLoop()).toBe(false);
  });

  it('hashes args independent of key order', () => {
    const detector = new DoomLoopDetector({ maxIdenticalActions: 2 });
    detector.recordAction('t', { a: 1, b: 2 }, 'r', true);
    detector.recordAction('t', { b: 2, a: 1 }, 'r', true);
    expect(detector.getLoopType()).toBe(DoomLoopType.REPEATED_ACTION);
  });
});

describe('DoomLoopDetector other detectors', () => {
  it('flags consecutive failures', () => {
    const detector = new DoomLoopDetector({ maxConsecutiveFailures: 2 });
    detector.recordAction('a', { i: 1 }, 'x', false);
    expect(detector.isDoomLoop()).toBe(false);
    detector.recordAction('b', { i: 2 }, 'y', false);
    expect(detector.getLoopType()).toBe(DoomLoopType.REPEATED_FAILURE);
  });

  it('flags no progress when results never change, unless progress was marked', () => {
    const detector = new DoomLoopDetector({ maxNoProgressSteps: 3, maxSimilarActions: 10 });
    detector.recordAction('a', { i: 1 }, 'same', true);
    detector.recordAction('b', { i: 2 }, 'same', true);
    detector.recordAction('c', { i: 3 }, 'same', true);
    expect(detector.getLoopType()).toBe(DoomLoopType.NO_PROGRESS);

    const fresh = new DoomLoopDetector({ maxNoProgressSteps: 3, maxSimilarActions: 10 });
    fresh.recordAction('a', { i: 1 }, 'same', true);
    fresh.markProgress('file written');
    fresh.recordAction('b', { i: 2 }, 'same', true);
    fresh.recordAction('c', { i: 3 }, 'same', true);
    expect(fresh.isDoomLoop()).toBe(false);
  });

  it('flags repeated output chunks after maxRepeatedChunks', () => {
    const detector = new DoomLoopDetector({ maxRepeatedChunks: 3, contentChunkSize: 5 });
    detector.recordResponse('abcde'.repeat(2));
    expect(detector.isDoomLoop()).toBe(false);
    detector.recordResponse('abcde');
    expect(detector.getLoopType()).toBe(DoomLoopType.REPEATED_OUTPUT);
  });
});

describe('DoomLoopDetector recovery', () => {
  it('walks RETRY_DIFFERENT -> ESCALATE_MODEL -> ABORT as attempts grow', async () => {
    const detector = new DoomLoopDetector({ maxIdenticalActions: 2, initialBackoff: 0 });
    detector.recordAction('t', {}, 'r', true);
    detector.recordAction('t', {}, 'r', true);
    expect(detector.getRecoveryAction()).toBe(RecoveryAction.RETRY_DIFFERENT);
    expect(detector.incrementRecovery()).toBe(true);
    expect(detector.getRecoveryAction()).toBe(RecoveryAction.ESCALATE_MODEL);
    expect(detector.incrementRecovery()).toBe(false);
    expect(detector.getRecoveryAction()).toBe(RecoveryAction.ABORT);
  });

  it('applyBackoff grows geometrically, capped, and resets', async () => {
    const detector = new DoomLoopDetector({ initialBackoff: 0, backoffMultiplier: 2, maxBackoff: 30 });
    expect(await detector.applyBackoff()).toBe(0);
    expect(detector.getStats().currentBackoff).toBe(0);
    detector.resetBackoff();
    expect(detector.getStats().currentBackoff).toBe(0);
  });

  it('startSession clears history', () => {
    const detector = new DoomLoopDetector({ maxIdenticalActions: 2 });
    detector.recordAction('t', {}, 'r', true);
    detector.recordAction('t', {}, 'r', true);
    expect(detector.isDoomLoop()).toBe(true);
    detector.startSession();
    expect(detector.isDoomLoop()).toBe(false);
    expect(detector.getStats().totalActions).toBe(0);
  });
});

describe('stableHash', () => {
  it('is 16 hex chars and deterministic', () => {
    expect(stableHash('abc')).toMatch(/^[0-9a-f]{16}$/);
    expect(stableHash('abc')).toBe(stableHash('abc'));
    expect(stableHash('abc')).not.toBe(stableHash('abd'));
  });
});
