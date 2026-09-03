/**
 * Structured logging — Python parity: praisonaiagents/_logging.py
 * (StructuredFormatter, configure_structured_logging, get_logger).
 */
import {
    Logger,
    StructuredFormatter,
    PraisonLogger,
    getLogger,
    normalizeLoggerName,
    configureStructuredLogging,
    LogRecord,
} from '../../../src/utils/logger';

describe('StructuredFormatter (parity: _logging.StructuredFormatter)', () => {
    const baseRecord: LogRecord = {
        name: 'praisonaiagents.agent',
        level: 'INFO',
        message: 'hello',
        timestamp: new Date('2026-01-02T03:04:05.678Z'),
        module: 'agent',
        function: 'run',
        line: 42,
    };

    it('emits the same field names as Python', () => {
        const out = JSON.parse(new StructuredFormatter().format(baseRecord));
        expect(Object.keys(out)).toEqual(['timestamp', 'level', 'logger', 'message', 'module', 'function', 'line']);
        expect(out).toMatchObject({
            timestamp: '2026-01-02T03:04:05.678Z',
            level: 'INFO',
            logger: 'praisonaiagents.agent',
            message: 'hello',
            module: 'agent',
            function: 'run',
            line: 42,
        });
    });

    it('adds exc_info and stack_info only when present', () => {
        const formatter = new StructuredFormatter();
        const plain = JSON.parse(formatter.format(baseRecord));
        expect(plain).not.toHaveProperty('exc_info');
        expect(plain).not.toHaveProperty('stack_info');

        const error = new Error('boom');
        const withError = JSON.parse(formatter.format({ ...baseRecord, error, stackInfo: 'frame-1\nframe-2' }));
        expect(withError.exc_info).toContain('Error: boom');
        expect(withError.stack_info).toBe('frame-1\nframe-2');
    });

    it('merges extraData without overwriting standard fields', () => {
        const out = JSON.parse(new StructuredFormatter().format({
            ...baseRecord,
            extraData: { agent_id: 'assistant', session: '123', level: 'HACKED', message: 'HACKED' },
        }));
        expect(out.agent_id).toBe('assistant');
        expect(out.session).toBe('123');
        expect(out.level).toBe('INFO');
        expect(out.message).toBe('hello');
    });

    it('STANDARD_FIELDS matches Python _STANDARD_FIELDS', () => {
        expect([...StructuredFormatter.STANDARD_FIELDS].sort()).toEqual([
            'exc_info', 'function', 'level', 'line', 'logger', 'message', 'module', 'stack_info', 'timestamp',
        ]);
    });

    it('honours datefmt like logging.Formatter(datefmt=...)', () => {
        const formatter = new StructuredFormatter({ datefmt: '%Y-%m-%d %H:%M:%S' });
        const ts = new Date(2026, 0, 2, 3, 4, 5); // local time, as strftime is
        const out = JSON.parse(formatter.format({ ...baseRecord, timestamp: ts }));
        expect(out.timestamp).toBe('2026-01-02 03:04:05');
        expect(new StructuredFormatter().datefmt).toBeNull();
    });

    it('survives circular context', () => {
        const context: any = { a: 1 };
        context.self = context;
        const out = JSON.parse(new StructuredFormatter().format({ ...baseRecord, context }));
        expect(out.context.self).toBe('[Circular]');
    });
});

describe('Logger with a formatter installed', () => {
    let logSpy: jest.SpyInstance;
    let errorSpy: jest.SpyInstance;

    beforeEach(() => {
        logSpy = jest.spyOn(console, 'log').mockImplementation(() => undefined);
        errorSpy = jest.spyOn(console, 'error').mockImplementation(() => undefined);
        Logger.setVerbose(true);
        Logger.setFormatter(new StructuredFormatter());
    });

    afterEach(() => {
        Logger.setFormatter(null);
        logSpy.mockRestore();
        errorSpy.mockRestore();
    });

    it('routes Logger.info through the formatter with the root logger name and call site', async () => {
        await Logger.info('structured hello', { requestId: 'r1' });
        expect(logSpy).toHaveBeenCalledTimes(1);
        const out = JSON.parse(logSpy.mock.calls[0][0]);
        expect(out.logger).toBe('praisonaiagents');
        expect(out.level).toBe('INFO');
        expect(out.message).toBe('structured hello');
        expect(out.context).toEqual({ requestId: 'r1' });
        expect(out.module).toBe('structured-logging.test');
        expect(typeof out.line).toBe('number');
        expect(out).not.toHaveProperty('exc_info');
    });

    it('uses Python level names and lifts an Error out of the context into exc_info', async () => {
        await Logger.error('failed', { error: new Error('kaboom') });
        const out = JSON.parse(errorSpy.mock.calls[0][0]);
        expect(out.level).toBe('ERROR');
        expect(out.exc_info).toContain('kaboom');
    });

    it('getFormatter/setFormatter round-trip and null restores plain output', async () => {
        expect(Logger.getFormatter()).toBeInstanceOf(StructuredFormatter);
        Logger.setFormatter(null);
        expect(Logger.getFormatter()).toBeNull();
        await Logger.info('plain again');
        expect(logSpy).toHaveBeenCalledWith('[INFO] plain again');
    });
});

describe('getLogger (parity: _logging.get_logger)', () => {
    it('returns the same instance for the same name', () => {
        const a = getLogger('agent.heartbeat');
        const b = getLogger('agent.heartbeat');
        const c = getLogger('praisonaiagents.agent.heartbeat');
        expect(a).toBe(b);
        expect(a).toBe(c);
        expect(a).toBeInstanceOf(PraisonLogger);
        expect(a.name).toBe('praisonaiagents.agent.heartbeat');
        expect(getLogger('other')).not.toBe(a);
    });

    it('applies the Python naming convention', () => {
        expect(normalizeLoggerName('foo')).toBe('praisonaiagents.foo');
        expect(normalizeLoggerName('praisonaiagents.foo')).toBe('praisonaiagents.foo');
        expect(normalizeLoggerName('__main__')).toBe('praisonaiagents.main');
        expect(normalizeLoggerName('praisonai.tools')).toBe('praisonaiagents.tools');
        expect(normalizeLoggerName('praisonai')).toBe('praisonaiagents');
    });

    it('detects the calling module when no name is given', () => {
        const auto = getLogger();
        expect(auto.name).toBe('praisonaiagents.structured-logging.test');
        expect(getLogger(null)).toBe(auto);
    });

    it('extraData returns an adapter-style logger bound to the same name whose records carry the data', async () => {
        const base = getLogger('scoped');
        const scoped = getLogger('scoped', { extraData: { agent_id: 'assistant' } });
        expect(scoped).not.toBe(base);
        expect(scoped.name).toBe(base.name);
        expect(getLogger('scoped', { extraData: {} })).toBe(base); // empty dict is falsy in Python too

        const logSpy = jest.spyOn(console, 'log').mockImplementation(() => undefined);
        Logger.setFormatter(new StructuredFormatter());
        try {
            await scoped.info('tick');
            const out = JSON.parse(logSpy.mock.calls[0][0]);
            expect(out.logger).toBe('praisonaiagents.scoped');
            expect(out.agent_id).toBe('assistant');
        } finally {
            Logger.setFormatter(null);
            logSpy.mockRestore();
        }
    });

    it('named logger prints its name in plain mode and shares Logger verbosity', async () => {
        const logSpy = jest.spyOn(console, 'log').mockImplementation(() => undefined);
        try {
            await getLogger('plain').info('msg');
            expect(logSpy).toHaveBeenCalledWith('[INFO] [praisonaiagents.plain] msg');
            Logger.setVerbose(false);
            await getLogger('plain').info('silenced');
            expect(logSpy).toHaveBeenCalledTimes(1);
        } finally {
            Logger.setVerbose(true);
            logSpy.mockRestore();
        }
    });
});

describe('configureStructuredLogging (parity: _logging.configure_structured_logging)', () => {
    const previous = process.env.PRAISONAI_STRUCTURED_LOGS;

    afterEach(() => {
        Logger.setFormatter(null);
        if (previous === undefined) {
            delete process.env.PRAISONAI_STRUCTURED_LOGS;
        } else {
            process.env.PRAISONAI_STRUCTURED_LOGS = previous;
        }
    });

    it('does nothing unless PRAISONAI_STRUCTURED_LOGS=true', () => {
        delete process.env.PRAISONAI_STRUCTURED_LOGS;
        configureStructuredLogging();
        expect(Logger.getFormatter()).toBeNull();
        process.env.PRAISONAI_STRUCTURED_LOGS = 'false';
        configureStructuredLogging();
        expect(Logger.getFormatter()).toBeNull();
    });

    it('installs a StructuredFormatter when the flag is set (case-insensitive)', () => {
        process.env.PRAISONAI_STRUCTURED_LOGS = 'TRUE';
        configureStructuredLogging();
        expect(Logger.getFormatter()).toBeInstanceOf(StructuredFormatter);
    });
});
