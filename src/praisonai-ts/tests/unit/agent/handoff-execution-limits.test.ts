/**
 * Handoff execution-limit parity tests - Python `Handoff.execute_async`:
 * `timeoutSeconds` bounds the target's turn (`asyncio.wait_for` ->
 * `HandoffTimeoutError`) and `maxConcurrent` bounds how many of one handoff's
 * executions run at once (the per-instance `asyncio.Semaphore`).
 *
 * Every case is paired with a control that turns the limit off, so a test that
 * would pass with the option ignored fails here.
 */

import { describe, it, expect, jest } from '@jest/globals';
import { Handoff, HandoffTimeoutError, type HandoffContext } from '../../../src/agent/handoff';

process.env.PRAISONAI_PARITY_SILENT = '1';

/** A sleep whose timer cannot hold the Jest worker open if a test abandons it. */
const wait = (ms: number) =>
  new Promise<void>(resolve => {
    const timer = setTimeout(resolve, ms);
    (timer as unknown as { unref?: () => void }).unref?.();
  });

const ctx = (extra: Partial<HandoffContext> = {}): HandoffContext => ({
  messages: [],
  lastMessage: 'go',
  ...extra,
});

/** A target that takes `delayMs` to answer and reports peak concurrency. */
function slowAgent(name: string, delayMs: number) {
  const agent: any = {
    name,
    active: 0,
    peak: 0,
    calls: 0,
    chat: jest.fn(async () => {
      agent.calls++;
      agent.active++;
      agent.peak = Math.max(agent.peak, agent.active);
      try {
        await wait(delayMs);
        return { text: `${name} ok` };
      } finally {
        agent.active--;
      }
    }),
  };
  return agent;
}

describe('Handoff execution limits (Python parity)', () => {
  describe('timeoutSeconds', () => {
    it('fails a target that runs past the timeout', async () => {
      const agent = slowAgent('slow', 200);
      const h = new Handoff({ agent, timeoutSeconds: 0.02 });

      await expect(h.execute(ctx())).rejects.toThrow(HandoffTimeoutError);
    });

    it('lets the same target finish when the timeout is generous (control)', async () => {
      const agent = slowAgent('slow', 20);
      const h = new Handoff({ agent, timeoutSeconds: 5 });

      const result = await h.execute(ctx());
      expect(result.response).toBe('slow ok');
    });

    it('lets the same target finish when the timeout is disabled with 0 (control)', async () => {
      const agent = slowAgent('slow', 30);
      const h = new Handoff({ agent, timeoutSeconds: 0 });

      const result = await h.execute(ctx());
      expect(result.response).toBe('slow ok');
    });

    it('reports the timeout the way Python does, and is retryable', async () => {
      const h = new Handoff({ agent: slowAgent('slow', 200), timeoutSeconds: 0.02 });
      let error: any;
      await h.execute(ctx({ sourceAgent: { name: 'main', chat: async () => '' } })).catch(e => { error = e; });

      expect(error).toBeInstanceOf(HandoffTimeoutError);
      expect(error.message).toBe('Handoff to slow timed out after 0.02s');
      expect(error.timeout).toBe(0.02);
      expect(error.isRetryable).toBe(true);
      expect(error.context).toMatchObject({ source_agent: 'main', target_agent: 'slow', timeout_seconds: 0.02 });
    });

    it('runs onError on the way out', async () => {
      const onError = jest.fn<(error: Error) => void>();
      const h = new Handoff({ agent: slowAgent('slow', 200), timeoutSeconds: 0.02, onError });

      await expect(h.execute(ctx())).rejects.toThrow(HandoffTimeoutError);
      expect(onError).toHaveBeenCalledWith(expect.any(HandoffTimeoutError));
    });

    it('does not leave the abandoned call as an unhandled rejection', async () => {
      const agent: any = {
        name: 'explodes-late',
        chat: jest.fn(async () => {
          await wait(30);
          throw new Error('too late to matter');
        }),
      };
      const unhandled: unknown[] = [];
      const onUnhandled = (reason: unknown) => unhandled.push(reason);
      process.on('unhandledRejection', onUnhandled);
      try {
        await expect(new Handoff({ agent, timeoutSeconds: 0.01 }).execute(ctx())).rejects.toThrow(
          HandoffTimeoutError
        );
        await wait(60); // outlive the abandoned call
      } finally {
        process.off('unhandledRejection', onUnhandled);
      }
      expect(unhandled).toEqual([]);
    });
  });

  describe('maxConcurrent', () => {
    it('serialises one handoff instance at maxConcurrent 1', async () => {
      const agent = slowAgent('specialist', 15);
      const h = new Handoff({ agent, maxConcurrent: 1 });

      await Promise.all([h.execute(ctx()), h.execute(ctx()), h.execute(ctx()), h.execute(ctx())]);
      expect(agent.calls).toBe(4);
      expect(agent.peak).toBe(1);
    });

    it('runs the same four at once when the limit is 0 = unlimited (control)', async () => {
      const agent = slowAgent('specialist', 15);
      const h = new Handoff({ agent, maxConcurrent: 0 });

      await Promise.all([h.execute(ctx()), h.execute(ctx()), h.execute(ctx()), h.execute(ctx())]);
      expect(agent.peak).toBe(4);
    });

    it('caps at the Python default of 5', async () => {
      const agent = slowAgent('specialist', 15);
      const h = new Handoff({ agent });

      await Promise.all(Array.from({ length: 8 }, () => h.execute(ctx())));
      expect(agent.calls).toBe(8);
      expect(agent.peak).toBe(5);
    });

    it('is per handoff instance, not process-wide', async () => {
      // Python creates the semaphore per Handoff so one handoff's limit cannot
      // be imposed on another; two instances at 1 each still run in parallel.
      const first = slowAgent('first', 20);
      const second = slowAgent('second', 20);
      const a = new Handoff({ agent: first, maxConcurrent: 1 });
      const b = new Handoff({ agent: second, maxConcurrent: 1 });

      // Prove concurrency by observed overlap rather than a wall-clock ceiling:
      // a shared gate would serialise them and the two would never be active at
      // once. Timing budgets flake on a loaded CI worker; overlap does not.
      let bothActive = false;
      const watch = setInterval(() => {
        if (first.active > 0 && second.active > 0) bothActive = true;
      }, 1);
      (watch as unknown as { unref?: () => void }).unref?.();
      try {
        await Promise.all([a.execute(ctx()), b.execute(ctx())]);
      } finally {
        clearInterval(watch);
      }
      expect(bothActive).toBe(true);
      expect(first.peak).toBe(1);
      expect(second.peak).toBe(1);
    });

    it('does not spend the timeout waiting for a slot', async () => {
      // Python acquires the semaphore *outside* wait_for: a queued handoff must
      // not be failed for the queue's length. Two calls at maxConcurrent 1,
      // each taking 30ms, with a 50ms timeout: the second waits 30ms for its
      // slot and still gets its full budget.
      const agent = slowAgent('specialist', 30);
      const h = new Handoff({ agent, maxConcurrent: 1, timeoutSeconds: 0.05 });

      const results = await Promise.all([h.execute(ctx()), h.execute(ctx())]);
      expect(results.map(r => r.response)).toEqual(['specialist ok', 'specialist ok']);
    });
  });
});
