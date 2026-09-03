/**
 * src/agent/retry-utils.ts — Python parity: praisonaiagents/agent/retry_utils.py
 */
import { RetryBackoffConfig, jitteredBackoff, interruptibleSleep } from '../../../src/agent/retry-utils';

/** Python's formula, transcribed, so the TS output is checked against it rather than against itself. */
function pythonJitteredBackoff(attempt: number, baseDelay: number, maxDelay: number, jitterRatio: number, uniform: number): number {
    let delay = Math.min(baseDelay * 2 ** Math.max(0, attempt), maxDelay);
    if (jitterRatio > 0) {
        const jitter = uniform * (delay * jitterRatio);
        delay = Math.max(0.1, Math.min(delay + jitter, maxDelay));
    }
    return delay;
}

describe('RetryBackoffConfig (parity: retry_utils.RetryBackoffConfig)', () => {
    it('has the Python defaults', () => {
        const config = new RetryBackoffConfig();
        expect(config.baseDelay).toBe(5.0);
        expect(config.maxDelay).toBe(120.0);
        expect(config.jitterRatio).toBe(0.5);
        expect(config.maxRetries).toBe(3);
    });

    it('accepts overrides', () => {
        const config = new RetryBackoffConfig({ baseDelay: 1, maxDelay: 10, jitterRatio: 0, maxRetries: 0 });
        expect(config).toMatchObject({ baseDelay: 1, maxDelay: 10, jitterRatio: 0, maxRetries: 0 });
    });

    it('validates like __post_init__', () => {
        expect(() => new RetryBackoffConfig({ baseDelay: 0 })).toThrow('base_delay must be > 0');
        expect(() => new RetryBackoffConfig({ baseDelay: -1 })).toThrow('base_delay must be > 0');
        expect(() => new RetryBackoffConfig({ maxDelay: 4.9 })).toThrow('max_delay must be >= base_delay');
        expect(() => new RetryBackoffConfig({ jitterRatio: 1.01 })).toThrow('jitter_ratio must be between 0 and 1');
        expect(() => new RetryBackoffConfig({ jitterRatio: -0.1 })).toThrow('jitter_ratio must be between 0 and 1');
        expect(() => new RetryBackoffConfig({ maxRetries: -1 })).toThrow('max_retries must be >= 0');
        expect(() => new RetryBackoffConfig({ baseDelay: NaN })).toThrow('base_delay must be > 0');
    });

    it('delayFor uses its own settings', () => {
        const config = new RetryBackoffConfig({ baseDelay: 2, maxDelay: 9, jitterRatio: 0 });
        expect([0, 1, 2, 3].map((a) => config.delayFor(a))).toEqual([2, 4, 8, 9]);
    });
});

describe('jitteredBackoff (parity: retry_utils.jittered_backoff)', () => {
    afterEach(() => {
        jest.restoreAllMocks();
    });

    it('with jitter disabled produces Python\'s exponential sequence capped at maxDelay', () => {
        const seq = [0, 1, 2, 3, 4, 5, 6].map((attempt) =>
            jitteredBackoff(attempt, { baseDelay: 5.0, maxDelay: 120.0, jitterRatio: 0 })
        );
        expect(seq).toEqual([5, 10, 20, 40, 80, 120, 120]);
    });

    it('treats negative attempts as attempt 0 (max(0, attempt))', () => {
        expect(jitteredBackoff(-3, { jitterRatio: 0 })).toBe(5);
    });

    it('uses the Python defaults when options are omitted', () => {
        jest.spyOn(Math, 'random').mockReturnValue(0);
        expect(jitteredBackoff(1)).toBe(10);
        expect(jitteredBackoff(10)).toBe(120);
    });

    it('matches Python\'s formula for a fixed uniform draw', () => {
        jest.spyOn(Math, 'random').mockReturnValue(0.5);
        // attempt 1: delay 10, jitter 0.5 * (10 * 0.5) = 2.5
        expect(jitteredBackoff(1)).toBe(12.5);
        expect(jitteredBackoff(1)).toBe(pythonJitteredBackoff(1, 5, 120, 0.5, 0.5));
        // attempt 5: delay 120 (capped) + jitter 30 -> clamped back to 120
        expect(jitteredBackoff(5)).toBe(120);
    });

    it('with jitter stays within [delay, min(delay * (1 + ratio), maxDelay)] and >= 0.1', () => {
        for (let attempt = 0; attempt < 8; attempt++) {
            const base = jitteredBackoff(attempt, { jitterRatio: 0 });
            for (let i = 0; i < 200; i++) {
                const d = jitteredBackoff(attempt);
                expect(d).toBeGreaterThanOrEqual(Math.max(0.1, base));
                expect(d).toBeLessThanOrEqual(Math.min(base * 1.5, 120));
            }
        }
    });

    it('never returns below the 0.1s floor', () => {
        jest.spyOn(Math, 'random').mockReturnValue(0);
        expect(jitteredBackoff(0, { baseDelay: 0.01, maxDelay: 0.05, jitterRatio: 0.5 })).toBe(0.1);
    });
});

describe('interruptibleSleep (parity: retry_utils.interruptible_sleep)', () => {
    beforeEach(() => {
        jest.useFakeTimers();
    });

    afterEach(() => {
        jest.useRealTimers();
    });

    it('resolves true after the full duration with the default 0.2s check interval', async () => {
        const promise = interruptibleSleep(1.0);
        let settled: boolean | undefined;
        void promise.then((v) => { settled = v; });

        await jest.advanceTimersByTimeAsync(800);
        expect(settled).toBeUndefined();
        await jest.advanceTimersByTimeAsync(200);
        expect(settled).toBe(true);
    });

    it('returns false as soon as interruptFn reports an interruption', async () => {
        let interrupted = false;
        const promise = interruptibleSleep(10, 0.5, () => interrupted);
        let settled: boolean | undefined;
        void promise.then((v) => { settled = v; });

        await jest.advanceTimersByTimeAsync(1000);
        expect(settled).toBeUndefined();
        interrupted = true;
        await jest.advanceTimersByTimeAsync(500);
        expect(settled).toBe(false);
    });

    it('resolves immediately for a non-positive duration', async () => {
        await expect(interruptibleSleep(0)).resolves.toBe(true);
    });
});
