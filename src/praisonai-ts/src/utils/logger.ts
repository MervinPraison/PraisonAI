import { PrettyLogger } from './pretty-logger';

export enum LogLevel {
    DEBUG = 0,
    INFO = 1,
    WARN = 2,
    ERROR = 3
}

// ============================================================================
// Structured logging support
// Python parity: praisonaiagents/_logging.py (StructuredFormatter,
// configure_structured_logging, get_logger). Python's `logging` module has
// named loggers, formatters and records; here the same three concepts are
// layered onto the existing static `Logger` instead of a second log system.
// ============================================================================

/**
 * Python `logging` level names as they appear in `record.levelname`, so a
 * structured record filtered by `level` matches Python output ("WARNING",
 * not "WARN").
 */
export type LogLevelName = 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR';

const LEVEL_NAMES: Record<LogLevel, LogLevelName> = {
    [LogLevel.DEBUG]: 'DEBUG',
    [LogLevel.INFO]: 'INFO',
    [LogLevel.WARN]: 'WARNING',
    [LogLevel.ERROR]: 'ERROR',
};

/** Prefix used by the plain (non-structured, non-pretty) console output. */
const LEVEL_TAGS: Record<LogLevel, string> = {
    [LogLevel.DEBUG]: 'DEBUG',
    [LogLevel.INFO]: 'INFO',
    [LogLevel.WARN]: 'WARN',
    [LogLevel.ERROR]: 'ERROR',
};

/** Root logger name; every {@link getLogger} name is prefixed with it, as in Python. */
export const ROOT_LOGGER_NAME = 'praisonaiagents';

/**
 * One log event, the counterpart of Python's `logging.LogRecord`. Field
 * comments give the Python attribute each one mirrors.
 */
export interface LogRecord {
    /** Logger name (`record.name`). */
    name: string;
    /** Level name (`record.levelname`). */
    level: LogLevelName;
    /** Rendered message (`record.getMessage()`). */
    message: string;
    /** Event time (`record.created`); defaults to now. */
    timestamp?: Date;
    /** Source module name without extension (`record.module`). */
    module?: string;
    /** Calling function name (`record.funcName`). */
    function?: string;
    /** Source line number (`record.lineno`). */
    line?: number;
    /** Attached exception (`record.exc_info`). */
    error?: unknown;
    /** Attached stack text (`record.stack_info`). */
    stackInfo?: string;
    /** Free-form context passed to the `Logger` methods (no Python counterpart). */
    context?: unknown;
    /** Per-logger structured fields (`record.extra_data`, from `get_logger(extra_data=...)`). */
    extraData?: Record<string, unknown> | null;
}

/** Anything that can turn a {@link LogRecord} into a line of output (Python `logging.Formatter`). */
export interface LogFormatter {
    format(record: LogRecord): string;
}

function circularReplacer() {
    const seen = new WeakSet();
    return (key: string, value: any) => {
        if (typeof value === 'object' && value !== null) {
            if (seen.has(value)) {
                return '[Circular]';
            }
            seen.add(value);
        }
        return value;
    };
}

function safeStringify(value: unknown, indent?: number): string {
    try {
        return JSON.stringify(value, circularReplacer(), indent);
    } catch {
        return String(value);
    }
}

/**
 * Minimal `strftime` covering the directives Python's default log formats use
 * (`%Y %m %d %H %M %S %f %X %x %%`). Unknown directives are left as written.
 */
function strftime(date: Date, format: string): string {
    const pad = (n: number, width = 2) => String(n).padStart(width, '0');
    return format.replace(/%([a-zA-Z%])/g, (whole, directive: string) => {
        switch (directive) {
            case 'Y': return String(date.getFullYear());
            case 'm': return pad(date.getMonth() + 1);
            case 'd': return pad(date.getDate());
            case 'H': return pad(date.getHours());
            case 'M': return pad(date.getMinutes());
            case 'S': return pad(date.getSeconds());
            case 'f': return pad(date.getMilliseconds() * 1000, 6);
            case 'X': return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
            case 'x': return `${pad(date.getMonth() + 1)}/${pad(date.getDate())}/${pad(date.getFullYear() % 100)}`;
            case '%': return '%';
            default: return whole;
        }
    });
}

const LOGGER_FILE_RE = /[\\/]utils[\\/]logger\.(?:ts|js|mjs|cjs)$/;
const STACK_FRAME_RE = /^at (?:(.+?) \()?(.+?):(\d+):(\d+)\)?$/;

/**
 * Locate the first stack frame outside this file, the way Python fills
 * `record.module` / `funcName` / `lineno` from the caller's frame. Only used
 * when a formatter is installed, so plain logging pays nothing for it.
 */
function captureCallSite(): Pick<LogRecord, 'module' | 'function' | 'line'> | undefined {
    const stack = new Error().stack;
    if (!stack) {
        return undefined;
    }
    for (const raw of stack.split('\n').slice(1)) {
        const frame = raw.trim();
        const match = STACK_FRAME_RE.exec(frame);
        if (!match) {
            continue;
        }
        const [, fn, file, lineNo] = match;
        if (LOGGER_FILE_RE.test(file) || file.startsWith('node:') || file === '<anonymous>') {
            continue;
        }
        const base = file.split(/[\\/]/).pop() ?? file;
        const functionName = !fn || fn === 'Object.<anonymous>' ? '<module>' : fn;
        return { module: base.replace(/\.[^.]+$/, ''), function: functionName, line: Number(lineNo) };
    }
    return undefined;
}

/** Constructor options for {@link StructuredFormatter}. */
export interface StructuredFormatterOptions {
    /**
     * `strftime`-style format for the `timestamp` field (Python
     * `logging.Formatter(datefmt=...)`). `null` emits ISO 8601 (`toISOString`).
     */
    datefmt?: string | null;
}

/**
 * JSON formatter for structured logging in production environments.
 *
 * Python parity: `StructuredFormatter` in praisonaiagents/_logging.py. Emits
 * one JSON object per record with the same field names: `timestamp`, `level`,
 * `logger`, `message`, `module`, `function`, `line`, plus `exc_info` and
 * `stack_info` when present, then any `extraData` keys that do not collide
 * with those standard fields.
 */
export class StructuredFormatter implements LogFormatter {
    /** Field names that `extraData` may never overwrite (Python `_STANDARD_FIELDS`). */
    static readonly STANDARD_FIELDS: ReadonlySet<string> = new Set([
        'timestamp', 'level', 'logger', 'message',
        'module', 'function', 'line', 'exc_info', 'stack_info',
    ]);

    readonly datefmt: string | null;

    constructor(options: StructuredFormatterOptions = {}) {
        this.datefmt = options.datefmt ?? null;
    }

    /** Python `Formatter.formatTime`. */
    formatTime(record: LogRecord, datefmt: string | null = this.datefmt): string {
        const date = record.timestamp ?? new Date();
        return datefmt ? strftime(date, datefmt) : date.toISOString();
    }

    /** Python `Formatter.formatException`: the stack trace text of an error. */
    formatException(error: unknown): string {
        if (error instanceof Error) {
            return error.stack ?? `${error.name}: ${error.message}`;
        }
        return String(error);
    }

    /** Python `Formatter.formatStack`. */
    formatStack(stackInfo: string): string {
        return stackInfo;
    }

    /** Format a record as one line of JSON. Python `StructuredFormatter.format`. */
    format(record: LogRecord): string {
        const logData: Record<string, unknown> = {
            timestamp: this.formatTime(record, this.datefmt),
            level: record.level,
            logger: record.name,
            message: record.message,
            module: record.module ?? null,
            function: record.function ?? null,
            line: record.line ?? null,
        };

        // Include exception info if present
        if (record.error !== undefined && record.error !== null) {
            logData.exc_info = this.formatException(record.error);
        }
        if (record.stackInfo) {
            logData.stack_info = this.formatStack(record.stackInfo);
        }

        // Free-form Logger context travels under its own key so it can never
        // shadow a standard field or an extraData field.
        if (record.context !== undefined && record.context !== null) {
            logData.context = record.context;
        }

        // Merge extra fields without overwriting standard log fields
        if (record.extraData) {
            for (const [key, value] of Object.entries(record.extraData)) {
                if (!StructuredFormatter.STANDARD_FIELDS.has(key)) {
                    logData[key] = value;
                }
            }
        }

        return safeStringify(logData);
    }
}

export class Logger {
    private static _level?: LogLevel;
    private static verbose: boolean = true;
    private static pretty: boolean = false;
    private static formatter: LogFormatter | null = null;

    private static get level(): LogLevel {
        if (this._level === undefined) {
            const logLevel = typeof process !== 'undefined' && process.env
                ? process.env.LOGLEVEL
                : undefined;
            this._level = logLevel === 'debug' ? LogLevel.DEBUG : LogLevel.INFO;
        }
        return this._level;
    }

    private static getCircularReplacer() {
        return circularReplacer();
    }

    private static formatContext(context: any): string {
        try {
            return JSON.stringify(context, this.getCircularReplacer(), 2);
        } catch (error) {
            return String(context);
        }
    }

    static setVerbose(verbose: boolean): void {
        this.verbose = verbose;
    }

    static setPretty(pretty: boolean): void {
        this.pretty = pretty;
    }

    /**
     * Install (or with `null`, remove) a formatter. While one is installed,
     * every record from `Logger` and every {@link PraisonLogger} is rendered by
     * it instead of the plain/pretty output — the counterpart of Python's
     * `handler.setFormatter(...)` on the root handler.
     */
    static setFormatter(formatter: LogFormatter | null): void {
        this.formatter = formatter;
    }

    static getFormatter(): LogFormatter | null {
        return this.formatter;
    }

    /**
     * Route one event through the level/verbose gates and then to the
     * formatter, the pretty logger or the plain console. `name` and
     * `extraData` come from a named {@link PraisonLogger}.
     */
    static async log(
        level: LogLevel,
        message: string,
        context?: any,
        name?: string,
        extraData?: Record<string, unknown> | null
    ): Promise<void> {
        if (level < this.level) {
            return;
        }
        // Errors always print; everything else honours setVerbose(false).
        if (level < LogLevel.ERROR && !this.verbose) {
            return;
        }

        if (this.formatter) {
            const callSite = captureCallSite();
            const errorFromContext =
                context && typeof context === 'object' && (context as any).error instanceof Error
                    ? (context as any).error
                    : undefined;
            const record: LogRecord = {
                name: name ?? ROOT_LOGGER_NAME,
                level: LEVEL_NAMES[level],
                message,
                timestamp: new Date(),
                ...callSite,
                error: errorFromContext,
                context: context === undefined ? undefined : context,
                extraData: extraData ?? undefined,
            };
            this.write(level, this.formatter.format(record));
            return;
        }

        const labelled = name ? `[${name}] ${message}` : message;
        if (this.pretty) {
            if (level === LogLevel.WARN) {
                await PrettyLogger.warning(labelled, context);
            } else if (level === LogLevel.ERROR) {
                await PrettyLogger.error(labelled, context);
            } else {
                await PrettyLogger.info(labelled, context);
            }
            return;
        }

        this.write(
            level,
            `[${LEVEL_TAGS[level]}] ${labelled}${context ? '\nContext: ' + this.formatContext(context) : ''}`
        );
    }

    private static write(level: LogLevel, line: string): void {
        if (level === LogLevel.ERROR) {
            console.error(line);
        } else if (level === LogLevel.WARN) {
            console.warn(line);
        } else {
            console.log(line);
        }
    }

    static async debug(message: string, context?: any): Promise<void> {
        await this.log(LogLevel.DEBUG, message, context);
    }

    static async info(message: string, context?: any): Promise<void> {
        await this.log(LogLevel.INFO, message, context);
    }

    static async warn(message: string, context?: any): Promise<void> {
        await this.log(LogLevel.WARN, message, context);
    }

    static async error(message: string, context?: any): Promise<void> {
        await this.log(LogLevel.ERROR, message, context);
    }

    static async success(message: string, data?: unknown): Promise<void> {
        if (!this.verbose) return;

        if (this.pretty) {
            await PrettyLogger.success(message, data);
        } else {
            console.log(`✓ ${message}`);
            if (data) {
                console.log(data);
            }
        }
    }

    static async startSpinner(text: string): Promise<void> {
        if (!this.verbose) return;

        if (this.pretty) {
            await PrettyLogger.startSpinner(text);
        } else {
            console.log(`⟳ ${text}`);
        }
    }

    static async updateSpinner(text: string): Promise<void> {
        if (!this.verbose) return;

        if (this.pretty) {
            await PrettyLogger.updateSpinner(text);
        } else {
            console.log(`⟳ ${text}`);
        }
    }

    static async stopSpinner(success: boolean = true): Promise<void> {
        if (!this.verbose) return;

        if (this.pretty) {
            await PrettyLogger.stopSpinner(success);
        } else {
            // Already logged in startSpinner
        }
    }

    static async table(headers: string[], data: (string | number)[][]): Promise<void> {
        if (!this.verbose) return;

        if (this.pretty) {
            await PrettyLogger.table(headers, data);
        } else {
            console.log(headers.join('\t'));
            data.forEach(row => console.log(row.join('\t')));
        }
    }

    static async section(title: string, content: string): Promise<void> {
        if (!this.verbose) return;

        if (this.pretty) {
            await PrettyLogger.section(title, content);
        } else {
            console.log(`\n=== ${title} ===`);
            console.log(content);
            console.log('='.repeat(title.length + 8));
        }
    }
}

// ============================================================================
// Named loggers
// ============================================================================

/**
 * A named logger sharing the static `Logger`'s level, verbosity and
 * formatter — Python's `logging.Logger` (or `_ExtraDataAdapter` when
 * `extraData` is set). Obtain one through {@link getLogger}.
 */
export class PraisonLogger {
    readonly name: string;
    readonly extraData: Record<string, unknown> | null;

    constructor(name: string, extraData: Record<string, unknown> | null = null) {
        this.name = name;
        this.extraData = extraData;
    }

    /** A logger with the same name and additional structured fields (Python `LoggerAdapter`). */
    withExtraData(extraData: Record<string, unknown>): PraisonLogger {
        return new PraisonLogger(this.name, { ...(this.extraData ?? {}), ...extraData });
    }

    debug(message: string, context?: any): Promise<void> {
        return Logger.log(LogLevel.DEBUG, message, context, this.name, this.extraData);
    }

    info(message: string, context?: any): Promise<void> {
        return Logger.log(LogLevel.INFO, message, context, this.name, this.extraData);
    }

    warn(message: string, context?: any): Promise<void> {
        return Logger.log(LogLevel.WARN, message, context, this.name, this.extraData);
    }

    /** Python spelling of {@link warn}. */
    warning(message: string, context?: any): Promise<void> {
        return this.warn(message, context);
    }

    error(message: string, context?: any): Promise<void> {
        return Logger.log(LogLevel.ERROR, message, context, this.name, this.extraData);
    }
}

const loggerRegistry = new Map<string, PraisonLogger>();

/**
 * Apply Python `get_logger`'s naming convention: every name lives under
 * `praisonaiagents.`; `__main__` becomes `praisonaiagents.main`; a
 * `praisonai`/`praisonai.x` name is re-rooted to `praisonaiagents.x`.
 */
export function normalizeLoggerName(name: string): string {
    if (name.startsWith(`${ROOT_LOGGER_NAME}.`)) {
        return name;
    }
    if (name === '__main__') {
        return `${ROOT_LOGGER_NAME}.main`;
    }
    if (name === 'praisonai' || name.startsWith('praisonai.')) {
        return ROOT_LOGGER_NAME + name.slice('praisonai'.length);
    }
    return `${ROOT_LOGGER_NAME}.${name}`;
}

/** Keyword options of {@link getLogger}; Python's keyword-only parameters. */
export interface GetLoggerOptions {
    /** Extra fields merged into every record from this logger (Python `extra_data`). */
    extraData?: Record<string, unknown> | null;
}

/**
 * Get a logger with consistent naming for PraisonAI modules.
 *
 * Python parity: `get_logger(name=None, *, extra_data=None)` in
 * praisonaiagents/_logging.py. The same name always returns the same instance
 * (Python's `logging.getLogger` registry); when `extraData` is given a fresh
 * adapter-style logger bound to that name is returned, as Python wraps the
 * base logger in `_ExtraDataAdapter`. With no name, the calling file's
 * basename stands in for Python's `__name__`.
 *
 * @example
 * const logger = getLogger('agent.heartbeat');           // praisonaiagents.agent.heartbeat
 * const scoped = getLogger('agent', { extraData: { agentId: 'assistant' } });
 */
export function getLogger(name: string | null = null, options: GetLoggerOptions = {}): PraisonLogger {
    const { extraData = null } = options;

    // Auto-detect the caller's module when no name is given.
    const resolvedName = normalizeLoggerName(name ?? captureCallSite()?.module ?? 'unknown');

    let base = loggerRegistry.get(resolvedName);
    if (!base) {
        base = new PraisonLogger(resolvedName);
        loggerRegistry.set(resolvedName, base);
    }

    // Wrap with an adapter-style logger when extra structured data is requested.
    if (extraData && Object.keys(extraData).length > 0) {
        return new PraisonLogger(resolvedName, extraData);
    }

    return base;
}

/**
 * Configure structured JSON logging for production environments.
 *
 * Python parity: `configure_structured_logging()` in praisonaiagents/_logging.py.
 * Exactly like Python it only acts when `PRAISONAI_STRUCTURED_LOGS=true`;
 * it then installs a {@link StructuredFormatter} on the `Logger`, which every
 * named logger shares. Useful for log aggregation (ELK, Splunk, CloudWatch).
 *
 * @example
 * process.env.PRAISONAI_STRUCTURED_LOGS = 'true';
 * configureStructuredLogging();
 */
export function configureStructuredLogging(): void {
    const flag = typeof process !== 'undefined' && process.env
        ? process.env.PRAISONAI_STRUCTURED_LOGS
        : undefined;
    if ((flag ?? '').toLowerCase() === 'true') {
        Logger.setFormatter(new StructuredFormatter());
    }
}
