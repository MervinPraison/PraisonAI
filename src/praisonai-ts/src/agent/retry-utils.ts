/**
 * Retry utilities with jittered exponential backoff.
 *
 * Python parity: praisonaiagents/agent/retry_utils.py
 * (`RetryBackoffConfig`, `jittered_backoff`, `interruptible_sleep`).
 *
 * All durations are in SECONDS, as in Python, so that the same numbers mean
 * the same thing in both SDKs. Multiply by 1000 before handing a value to
 * `setTimeout`; {@link interruptibleSleep} already does.
 */

/** Constructor options for {@link RetryBackoffConfig}; the Python dataclass fields. */
export interface RetryBackoffConfigOptions {
    /** Base delay in seconds. Python: `base_delay: float = 5.0`. Must be > 0. */
    baseDelay?: number;
    /** Maximum delay in seconds. Python: `max_delay: float = 120.0`. Must be >= baseDelay. */
    maxDelay?: number;
    /** Jitter as a fraction of the delay added on top (0.0-1.0). Python: `jitter_ratio: float = 0.5`. */
    jitterRatio?: number;
    /** Maximum retry attempts. Python: `max_retries: int = 3`. Must be >= 0. */
    maxRetries?: number;
}

/**
 * Configuration for jittered exponential backoff retry behaviour.
 *
 * Python parity: `RetryBackoffConfig` dataclass in agent/retry_utils.py,
 * including its `__post_init__` validation (same messages).
 */
export class RetryBackoffConfig {
    readonly baseDelay: number;
    readonly maxDelay: number;
    readonly jitterRatio: number;
    readonly maxRetries: number;

    constructor(config: RetryBackoffConfigOptions = {}) {
        this.baseDelay = config.baseDelay ?? 5.0;
        this.maxDelay = config.maxDelay ?? 120.0;
        this.jitterRatio = config.jitterRatio ?? 0.5;
        this.maxRetries = config.maxRetries ?? 3;

        if (!(this.baseDelay > 0)) {
            throw new RangeError('base_delay must be > 0');
        }
        if (!(this.maxDelay >= this.baseDelay)) {
            throw new RangeError('max_delay must be >= base_delay');
        }
        if (!(this.jitterRatio >= 0 && this.jitterRatio <= 1)) {
            throw new RangeError('jitter_ratio must be between 0 and 1');
        }
        if (!(this.maxRetries >= 0)) {
            throw new RangeError('max_retries must be >= 0');
        }
    }

    /** Delay in seconds for `attempt` (0-based) under this configuration. */
    delayFor(attempt: number): number {
        return jitteredBackoff(attempt, {
            baseDelay: this.baseDelay,
            maxDelay: this.maxDelay,
            jitterRatio: this.jitterRatio,
        });
    }
}

/** Keyword options of {@link jitteredBackoff}; Python's keyword-only parameters. */
export interface JitteredBackoffOptions {
    /** Base delay in seconds. Python: `base_delay: float = 5.0`. */
    baseDelay?: number;
    /** Maximum delay cap in seconds. Python: `max_delay: float = 120.0`. */
    maxDelay?: number;
    /** Fraction of the delay added as positive jitter (0.0-1.0). Python: `jitter_ratio: float = 0.5`. */
    jitterRatio?: number;
}

/**
 * Calculate the delay (seconds) for jittered exponential backoff.
 *
 * Python parity: `jittered_backoff(attempt, *, base_delay, max_delay, jitter_ratio)`.
 * Formula, identical to Python:
 *   delay = min(base * 2 ** max(0, attempt), max)
 *   if jitterRatio > 0: delay = max(0.1, min(delay + uniform(0, delay * jitterRatio), max))
 *
 * @param attempt Current attempt number (0-based).
 * @returns Delay in seconds with jitter applied.
 *
 * @example
 * // Attempt 0: ~5s, attempt 1: ~10s, attempt 2: ~20s
 * const delay = jitteredBackoff(1, { baseDelay: 5.0, maxDelay: 120.0, jitterRatio: 0.5 });
 */
export function jitteredBackoff(attempt: number, options: JitteredBackoffOptions = {}): number {
    const { baseDelay = 5.0, maxDelay = 120.0, jitterRatio = 0.5 } = options;

    // Exponential backoff: base * 2^attempt
    let delay = Math.min(baseDelay * Math.pow(2, Math.max(0, attempt)), maxDelay);

    // Additive positive jitter: delay + uniform(0, jitterRatio * delay), clamped again.
    if (jitterRatio > 0) {
        const jitterRange = delay * jitterRatio;
        const jitter = Math.random() * jitterRange;
        delay = Math.max(0.1, Math.min(delay + jitter, maxDelay));
    }

    return delay;
}

/**
 * Sleep with periodic interruption checks.
 *
 * Python parity: `interruptible_sleep(seconds, check_interval=0.2, interrupt_fn=None)`.
 *
 * @param seconds Total sleep duration in seconds.
 * @param checkInterval How often to check for interruption, in seconds.
 * @param interruptFn Returns true when the sleep should be cut short.
 * @returns true if the full duration elapsed, false if interrupted.
 *
 * @example
 * const completed = await interruptibleSleep(30.0, 0.2, () => agent.isStopped());
 */
export async function interruptibleSleep(
    seconds: number,
    checkInterval: number = 0.2,
    interruptFn?: () => boolean
): Promise<boolean> {
    const shouldInterrupt = interruptFn ?? (() => false);

    let elapsed = 0.0;
    while (elapsed < seconds) {
        if (shouldInterrupt()) {
            return false; // Interrupted
        }
        const sleepTime = Math.min(checkInterval, seconds - elapsed);
        await new Promise<void>((resolve) => setTimeout(resolve, Math.max(0, sleepTime * 1000)));
        elapsed += sleepTime;
    }

    return true; // Completed full sleep
}
