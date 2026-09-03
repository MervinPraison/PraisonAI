/**
 * src/agent/heartbeat.ts — Python parity: praisonaiagents/agent/heartbeat.py
 */
import { Heartbeat, HeartbeatConfig, parseHeartbeatSchedule, HeartbeatAgent } from '../../../src/agent/heartbeat';
import { Logger } from '../../../src/utils/logger';

function makeAgent(impl: (prompt: string) => unknown = () => 'ok'): HeartbeatAgent & { start: jest.Mock } {
    return { name: 'monitor', start: jest.fn(impl) };
}

describe('parseHeartbeatSchedule (parity: Heartbeat._resolve_interval + scheduler/parser.py)', () => {
    it.each([
        ['hourly', 3600],
        ['daily', 86400],
        ['weekly', 604800],
        ['Hourly', 3600],
        ['every 30m', 1800],
        ['*/30m', 1800],
        ['30m', 1800],
        ['every 6h', 21600],
        ['*/6h', 21600],
        ['*/10s', 10],
        ['every 2 hours', 7200],
        ['5 minutes', 300],
        ['Every 45 Sec', 45],
        ['3600', 3600],
        ['  daily  ', 86400],
    ])('parses %j -> %d seconds', (schedule, seconds) => {
        expect(parseHeartbeatSchedule(schedule)).toBe(seconds);
    });

    it.each([
        '',
        '   ',
        'yearly',
        '0m',
        '0',
        '-5m',
        'cron:0 7 * * *',
        'at:2026-03-01T09:00:00',
        'in 20 minutes',
        'every day at 9am',
        '5 fortnights',
    ])('rejects %j', (schedule) => {
        expect(() => parseHeartbeatSchedule(schedule)).toThrow();
    });

    it('rejects non-strings', () => {
        expect(() => parseHeartbeatSchedule(undefined as unknown as string)).toThrow('cannot be empty');
    });
});

describe('HeartbeatConfig (parity: heartbeat.HeartbeatConfig)', () => {
    it('has the Python defaults', () => {
        const config = new HeartbeatConfig();
        expect(config.schedule).toBe('hourly');
        expect(config.prompt).toBeNull();
        expect(config.onResult).toBeNull();
        expect(config.onError).toBe('retry');
        expect(config.maxRetries).toBe(3);
    });

    it('keeps overrides', () => {
        const onResult = jest.fn();
        const config = new HeartbeatConfig({ schedule: 'daily', prompt: 'p', onResult, onError: 'skip', maxRetries: 1 });
        expect(config).toMatchObject({ schedule: 'daily', prompt: 'p', onResult, onError: 'skip', maxRetries: 1 });
    });
});

describe('Heartbeat (parity: heartbeat.Heartbeat)', () => {
    beforeEach(() => {
        jest.useFakeTimers();
        Logger.setVerbose(false); // keep tick logs out of the test output
    });

    afterEach(() => {
        jest.useRealTimers();
        Logger.setVerbose(true);
        jest.restoreAllMocks();
    });

    it('builds its config from the options and resolves the interval', () => {
        const hb = new Heartbeat(makeAgent(), { schedule: 'every 30m', prompt: 'Report status' });
        expect(hb.config).toBeInstanceOf(HeartbeatConfig);
        expect(hb.config.prompt).toBe('Report status');
        expect(hb.intervalSeconds).toBe(1800);
        expect(hb.isRunning).toBe(false);
        expect(new Heartbeat(makeAgent()).intervalSeconds).toBe(3600);
    });

    it('rejects a bad schedule at construction instead of silently running hourly', () => {
        expect(() => new Heartbeat(makeAgent(), { schedule: 'fortnightly' })).toThrow('Unrecognised heartbeat schedule');
    });

    it('ticks immediately, then every interval, and stops', async () => {
        const agent = makeAgent(async () => 'server fine');
        const onResult = jest.fn();
        const hb = new Heartbeat(agent, { schedule: '*/30m', onResult });

        await hb.start(false);
        expect(hb.isRunning).toBe(true);
        await jest.advanceTimersByTimeAsync(0);
        expect(agent.start).toHaveBeenCalledTimes(1);
        expect(agent.start).toHaveBeenCalledWith('Run your scheduled check.');
        expect(onResult).toHaveBeenCalledWith('server fine');

        await jest.advanceTimersByTimeAsync(1800 * 1000 - 1);
        expect(agent.start).toHaveBeenCalledTimes(1);
        await jest.advanceTimersByTimeAsync(1);
        expect(agent.start).toHaveBeenCalledTimes(2);

        hb.stop();
        expect(hb.isRunning).toBe(false);
        await jest.advanceTimersByTimeAsync(1800 * 1000 * 3);
        expect(agent.start).toHaveBeenCalledTimes(2);
        expect(jest.getTimerCount()).toBe(0);
    });

    it('uses the configured prompt and coerces the agent result to a string', async () => {
        const agent = makeAgent(() => ({ toString: () => 'obj' }));
        const onResult = jest.fn();
        const hb = new Heartbeat(agent, { schedule: 'hourly', prompt: 'Report status', onResult });
        await hb.start(false);
        await jest.advanceTimersByTimeAsync(0);
        expect(agent.start).toHaveBeenCalledWith('Report status');
        expect(onResult).toHaveBeenCalledWith('obj');
        hb.stop();
    });

    it('delivers an empty string for a falsy result', async () => {
        const onResult = jest.fn();
        const hb = new Heartbeat(makeAgent(() => undefined), { onResult });
        await hb.start(false);
        await jest.advanceTimersByTimeAsync(0);
        expect(onResult).toHaveBeenCalledWith('');
        hb.stop();
    });

    it('blocking start resolves only once stop() is called', async () => {
        const hb = new Heartbeat(makeAgent(), { schedule: '10s' });
        let resolved = false;
        const done = hb.start().then(() => { resolved = true; });
        await jest.advanceTimersByTimeAsync(25_000);
        expect(resolved).toBe(false);
        hb.stop();
        await done;
        expect(resolved).toBe(true);
        expect(hb.isRunning).toBe(false);
    });

    it('waits for an in-flight tick before settling the blocking promise, and does not reschedule', async () => {
        let finish: (v: string) => void = () => undefined;
        const agent = makeAgent(() => new Promise<string>((resolve) => { finish = resolve; }));
        const onResult = jest.fn();
        const hb = new Heartbeat(agent, { schedule: '10s', onResult });
        let resolved = false;
        const done = hb.start().then(() => { resolved = true; });
        await jest.advanceTimersByTimeAsync(0);
        hb.stop();
        await jest.advanceTimersByTimeAsync(0);
        expect(resolved).toBe(false);
        finish('late');
        await done;
        expect(onResult).toHaveBeenCalledWith('late');
        expect(jest.getTimerCount()).toBe(0);
    });

    it('calling start twice does not start a second loop', async () => {
        const agent = makeAgent();
        const hb = new Heartbeat(agent, { schedule: '10s' });
        await hb.start(false);
        await hb.start(false);
        await jest.advanceTimersByTimeAsync(0);
        expect(agent.start).toHaveBeenCalledTimes(1);
        hb.stop();
    });

    describe('error handling', () => {
        it('passes the error to a callable onError and keeps ticking', async () => {
            jest.spyOn(console, 'error').mockImplementation(() => undefined);
            const boom = new Error('boom');
            const agent = makeAgent(() => { throw boom; });
            const onError = jest.fn();
            const hb = new Heartbeat(agent, { schedule: '10s', onError });
            await hb.start(false);
            await jest.advanceTimersByTimeAsync(0);
            expect(onError).toHaveBeenCalledWith(boom);
            await jest.advanceTimersByTimeAsync(10_000);
            expect(agent.start).toHaveBeenCalledTimes(2);
            expect(onError).toHaveBeenCalledTimes(2);
            hb.stop();
        });

        it('"skip" logs a warning and continues', async () => {
            Logger.setVerbose(true);
            const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => undefined);
            jest.spyOn(console, 'error').mockImplementation(() => undefined);
            const agent = makeAgent(() => { throw new Error('nope'); });
            const hb = new Heartbeat(agent, { schedule: '10s', onError: 'skip' });
            await hb.start(false);
            await jest.advanceTimersByTimeAsync(0);
            expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('[heartbeat] Skipping error: Error: nope'));
            await jest.advanceTimersByTimeAsync(10_000);
            expect(agent.start).toHaveBeenCalledTimes(2);
            hb.stop();
        });

        it('"retry" counts consecutive failures, logs at maxRetries and resets', async () => {
            const errorSpy = jest.spyOn(console, 'error').mockImplementation(() => undefined);
            let calls = 0;
            const agent = makeAgent(() => {
                calls += 1;
                if (calls <= 4) throw new Error(`fail ${calls}`);
                return 'recovered';
            });
            const onResult = jest.fn();
            const hb = new Heartbeat(agent, { schedule: '10s', onError: 'retry', maxRetries: 2, onResult });
            await hb.start(false);
            await jest.advanceTimersByTimeAsync(0);            // tick 1: fail #1
            await jest.advanceTimersByTimeAsync(10_000);       // tick 2: fail #2 -> max reached, reset
            const maxReachedLines = errorSpy.mock.calls.filter(([line]) => String(line).includes('max retries (2) reached'));
            expect(maxReachedLines).toHaveLength(1);
            await jest.advanceTimersByTimeAsync(10_000);       // tick 3: fail #1 again
            await jest.advanceTimersByTimeAsync(10_000);       // tick 4: fail #2 -> max reached again
            expect(errorSpy.mock.calls.filter(([line]) => String(line).includes('max retries (2) reached'))).toHaveLength(2);
            await jest.advanceTimersByTimeAsync(10_000);       // tick 5: success
            expect(onResult).toHaveBeenCalledWith('recovered');
            hb.stop();
        });
    });

    it('unrefs its timer so a running heartbeat cannot hold the process open', async () => {
        jest.useRealTimers();
        const unrefs: jest.SpyInstance[] = [];
        const realSetTimeout = global.setTimeout;
        const setTimeoutSpy = jest.spyOn(global, 'setTimeout').mockImplementation(((fn: () => void, ms?: number) => {
            const timer = realSetTimeout(fn, ms);
            unrefs.push(jest.spyOn(timer, 'unref'));
            return timer;
        }) as typeof setTimeout);
        try {
            const hb = new Heartbeat(makeAgent(), { schedule: 'daily' });
            await hb.start(false);
            await new Promise<void>((resolve) => realSetTimeout(resolve, 0));
            expect(unrefs.length).toBeGreaterThanOrEqual(1);
            expect(unrefs[0]).toHaveBeenCalled();
            hb.stop();
        } finally {
            setTimeoutSpy.mockRestore();
        }
    });
});
