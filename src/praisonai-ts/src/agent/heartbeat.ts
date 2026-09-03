/**
 * Heartbeat — runs an agent on a schedule, delivers results via callback.
 *
 * Python parity: praisonaiagents/agent/heartbeat.py (`HeartbeatConfig`,
 * `Heartbeat`). Standalone wrapper; does NOT modify the Agent class.
 *
 * Python runs a thread that ticks, sleeps `interval` seconds, and repeats.
 * Here the loop is a chain of `setTimeout` calls that are `unref()`'d, so a
 * running heartbeat never keeps the Node process alive on its own, and
 * `stop()` clears the pending timer immediately.
 *
 * @example
 * const hb = new Heartbeat(agent, { schedule: 'every 30m', prompt: 'Report status' });
 * await hb.start();        // resolves when stop() is called
 * hb.start(false);         // background: returns after scheduling the first tick
 */

import { getLogger } from '../utils/logger';

const logger = getLogger('praisonaiagents.agent.heartbeat');

/** The slice of an agent the heartbeat needs: a name and `start(prompt)`. */
export interface HeartbeatAgent {
    name?: string;
    start(prompt: string): unknown;
}

/** Python `on_error`: "retry" | "skip" | callable(error). */
export type HeartbeatOnError = 'retry' | 'skip' | ((error: unknown) => void);

/** Options accepted by {@link HeartbeatConfig} and {@link Heartbeat}; the Python dataclass fields. */
export interface HeartbeatOptions {
    /**
     * Human-friendly schedule. Python: `schedule: str = "hourly"`. Supported:
     * keywords `hourly` | `daily` | `weekly`; intervals `every 30m`, `*\/30m`,
     * `30m`, `every 6h`, `*\/10s`, `2 hours`; raw seconds `"3600"`.
     * See {@link parseHeartbeatSchedule}.
     */
    schedule?: string;
    /** Prompt sent each tick. Python: `prompt: Optional[str] = None` (null = "Run your scheduled check."). */
    prompt?: string | null;
    /** Receives each tick's result text. Python: `on_result: Optional[Callable] = None` (null = log it). */
    onResult?: ((result: string) => void) | null;
    /** Error policy. Python: `on_error: Union[str, Callable] = "retry"`. */
    onError?: HeartbeatOnError;
    /** Consecutive failures before the retry counter resets. Python: `max_retries: int = 3`. */
    maxRetries?: number;
}

/**
 * Configuration for the Heartbeat scheduler.
 *
 * Python parity: `HeartbeatConfig` dataclass in agent/heartbeat.py, same
 * fields and defaults.
 */
export class HeartbeatConfig {
    readonly schedule: string;
    readonly prompt: string | null;
    readonly onResult: ((result: string) => void) | null;
    readonly onError: HeartbeatOnError;
    readonly maxRetries: number;

    constructor(config: HeartbeatOptions = {}) {
        this.schedule = config.schedule ?? 'hourly';
        this.prompt = config.prompt ?? null;
        this.onResult = config.onResult ?? null;
        this.onError = config.onError ?? 'retry';
        this.maxRetries = config.maxRetries ?? 3;
    }
}

const SCHEDULE_KEYWORDS: Record<string, number> = {
    hourly: 3600,
    daily: 86400,
    weekly: 604800,
};

// Same grammar as praisonaiagents/scheduler/parser.py `_INTERVAL_RE`, with the
// optional "every " prefix that heartbeat.py's fallback also accepts.
const INTERVAL_RE = /^(?:every\s+)?\*?\/?\*?(\d+)\s*(s|sec|second|seconds|m|min|minute|minutes|h|hr|hour|hours)$/i;

const UNIT_MULTIPLIER: Record<string, number> = {
    s: 1, sec: 1, second: 1, seconds: 1,
    m: 60, min: 60, minute: 60, minutes: 60,
    h: 3600, hr: 3600, hour: 3600, hours: 3600,
};

/** `setTimeout` cannot wait longer than this (2^31 - 1 ms, ~24.8 days). */
const MAX_TIMEOUT_MS = 2147483647;

/**
 * Convert a heartbeat schedule string to an interval in seconds.
 *
 * Python parity: `Heartbeat._resolve_interval` in agent/heartbeat.py, using
 * the interval grammar of scheduler/parser.py. Accepted forms:
 *   - keywords: `hourly`, `daily`, `weekly`
 *   - intervals: `every 30m`, `*\/30m`, `30m`, `every 6h`, `*\/10s`, `2 hours`
 *   - raw positive seconds: `3600`
 *
 * Deviation from Python, on purpose: Python silently falls back to hourly
 * for anything it cannot parse (including `cron:` and `at:` forms, which the
 * heartbeat cannot run). Here an unrecognised or non-positive schedule throws
 * so a misspelled schedule is caught at construction instead of running at
 * the wrong cadence.
 *
 * @throws {Error} when the schedule is empty, unrecognised, or resolves to zero seconds.
 */
export function parseHeartbeatSchedule(schedule: string): number {
    if (typeof schedule !== 'string' || !schedule.trim()) {
        throw new Error('Schedule expression cannot be empty');
    }
    const expr = schedule.trim();
    const lower = expr.toLowerCase();

    if (lower in SCHEDULE_KEYWORDS) {
        return SCHEDULE_KEYWORDS[lower];
    }

    let seconds: number | undefined;
    const match = INTERVAL_RE.exec(expr);
    if (match) {
        seconds = parseInt(match[1], 10) * UNIT_MULTIPLIER[match[2].toLowerCase()];
    } else if (/^\d+$/.test(expr)) {
        seconds = parseInt(expr, 10);
    }

    if (seconds === undefined) {
        throw new Error(
            `Unrecognised heartbeat schedule: ${JSON.stringify(schedule)}. ` +
            "Use 'hourly', 'daily', 'weekly', 'every 30m', '*/6h', '*/10s' or raw seconds. " +
            "Cron and one-shot ('cron:', 'at:') schedules are not intervals and cannot drive a heartbeat."
        );
    }
    if (!(seconds > 0)) {
        throw new Error(`Heartbeat schedule must be a positive interval, got ${JSON.stringify(schedule)}`);
    }
    return seconds;
}

/**
 * Standalone heartbeat coordinator: runs an agent on a schedule and delivers
 * results via callback. Does NOT add any params to the Agent class.
 *
 * Python parity: `Heartbeat(agent, schedule="hourly", prompt=None,
 * on_result=None, on_error="retry", max_retries=3)` in agent/heartbeat.py.
 * The keyword parameters travel in `options` (see {@link HeartbeatOptions}).
 */
export class Heartbeat {
    readonly agent: HeartbeatAgent;
    readonly config: HeartbeatConfig;

    private _running = false;
    private _timer: ReturnType<typeof setTimeout> | null = null;
    private _tickInFlight = false;
    private _retries = 0;
    private readonly _intervalSeconds: number;
    private _stopped: Promise<void> | null = null;
    private _resolveStopped: (() => void) | null = null;

    constructor(agent: HeartbeatAgent, options: HeartbeatOptions = {}) {
        this.agent = agent;
        this.config = new HeartbeatConfig(options);
        this._intervalSeconds = parseHeartbeatSchedule(this.config.schedule);
    }

    /** Interval between ticks in seconds, as resolved from `config.schedule`. */
    get intervalSeconds(): number {
        return this._intervalSeconds;
    }

    /** Python `is_running`. */
    get isRunning(): boolean {
        return this._running;
    }

    /**
     * Start the heartbeat loop. The first tick runs immediately, then every
     * interval, as in Python.
     *
     * @param blocking Python `start(blocking=True)`. When true the returned
     *   promise resolves only after {@link stop} is called and any in-flight
     *   tick has finished (the async counterpart of a blocking loop). When
     *   false the promise resolves as soon as the loop is scheduled, and the
     *   heartbeat keeps running in the background.
     */
    start(blocking: boolean = true): Promise<void> {
        if (!this._running) {
            this._running = true;
            this._retries = 0;
            this._stopped = new Promise<void>((resolve) => {
                this._resolveStopped = resolve;
            });
            void this._loop();
        }
        return blocking ? (this._stopped as Promise<void>) : Promise.resolve();
    }

    /** Stop the heartbeat loop; clears the pending timer so nothing fires again. */
    stop(): void {
        if (!this._running) {
            return;
        }
        this._running = false;
        if (this._timer !== null) {
            clearTimeout(this._timer);
            this._timer = null;
        }
        if (!this._tickInFlight) {
            this._settleStopped();
        }
    }

    // ── internals ────────────────────────────────────────────────────

    private _settleStopped(): void {
        const resolve = this._resolveStopped;
        this._resolveStopped = null;
        this._stopped = null;
        if (resolve) {
            resolve();
        }
    }

    /** One iteration of Python's `_loop`: tick, handle the outcome, sleep. */
    private async _loop(): Promise<void> {
        if (!this._running) {
            return;
        }
        this._tickInFlight = true;
        try {
            const result = await this._tick();
            this._retries = 0; // Reset on success
            this._deliver(result);
        } catch (error) {
            this._handleError(error);
        } finally {
            this._tickInFlight = false;
        }

        if (!this._running) {
            this._settleStopped();
            return;
        }
        const delayMs = Math.min(this._intervalSeconds * 1000, MAX_TIMEOUT_MS);
        const timer = setTimeout(() => {
            this._timer = null;
            void this._loop();
        }, delayMs);
        // Never keep the process alive just for the next tick.
        if (typeof (timer as any).unref === 'function') {
            (timer as any).unref();
        }
        this._timer = timer;
    }

    private _handleError(error: unknown): void {
        this._retries += 1;
        const name = this.agent.name ?? 'agent';
        void logger.error(`[heartbeat] ${name}: error on tick #${this._retries}: ${String(error)}`);
        const onError = this.config.onError;
        if (typeof onError === 'function') {
            onError(error);
        } else if (onError === 'skip') {
            void logger.warn(`[heartbeat] Skipping error: ${String(error)}`);
        } else if (this._retries >= this.config.maxRetries) { // "retry"
            void logger.error(
                `[heartbeat] ${name}: max retries (${this.config.maxRetries}) reached, skipping.`
            );
            this._retries = 0;
        }
    }

    /** Execute one heartbeat tick — run the agent and return its result text. */
    private async _tick(): Promise<string> {
        const prompt = this.config.prompt || 'Run your scheduled check.';
        const result = await this.agent.start(prompt);
        return result ? String(result) : '';
    }

    /** Deliver the result via callback or log. */
    private _deliver(result: string): void {
        if (this.config.onResult) {
            this.config.onResult(result);
        } else {
            void logger.info(`[heartbeat] ${this.agent.name ?? 'agent'}: ${result.slice(0, 200)}`);
        }
    }
}
