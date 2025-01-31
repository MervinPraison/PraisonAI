import { PrettyLogger } from './pretty-logger';

export enum LogLevel {
    DEBUG = 0,
    INFO = 1,
    WARN = 2,
    ERROR = 3
}

export class Logger {
    private static level: LogLevel = process.env.LOGLEVEL === 'debug' ? LogLevel.DEBUG : LogLevel.INFO;
    private static verbose: boolean = true;
    private static pretty: boolean = false;

    private static getCircularReplacer() {
        const seen = new WeakSet();
        return (key: string, value: any) => {
            if (typeof value === "object" && value !== null) {
                if (seen.has(value)) {
                    return "[Circular]";
                }
                seen.add(value);
            }
            return value;
        };
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

    static async debug(message: string, context?: any): Promise<void> {
        if (this.level <= LogLevel.DEBUG && this.verbose) {
            if (this.pretty) {
                await PrettyLogger.info(message, context);
            } else {
                console.log(`[DEBUG] ${message}${context ? '\nContext: ' + this.formatContext(context) : ''}`);
            }
        }
    }

    static async info(message: string, context?: any): Promise<void> {
        if (this.level <= LogLevel.INFO && this.verbose) {
            if (this.pretty) {
                await PrettyLogger.info(message, context);
            } else {
                console.log(`[INFO] ${message}${context ? '\nContext: ' + this.formatContext(context) : ''}`);
            }
        }
    }

    static async warn(message: string, context?: any): Promise<void> {
        if (this.level <= LogLevel.WARN && this.verbose) {
            if (this.pretty) {
                await PrettyLogger.warning(message, context);
            } else {
                console.warn(`[WARN] ${message}${context ? '\nContext: ' + this.formatContext(context) : ''}`);
            }
        }
    }

    static async error(message: string, context?: any): Promise<void> {
        if (this.level <= LogLevel.ERROR) {
            if (this.pretty) {
                await PrettyLogger.error(message, context);
            } else {
                console.error(`[ERROR] ${message}${context ? '\nContext: ' + this.formatContext(context) : ''}`);
            }
        }
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
