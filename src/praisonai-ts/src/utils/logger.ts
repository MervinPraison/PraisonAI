export enum LogLevel {
    DEBUG = 0,
    INFO = 1,
    WARN = 2,
    ERROR = 3
}

export class Logger {
    private static level: LogLevel = process.env.LOGLEVEL === 'debug' ? LogLevel.DEBUG : LogLevel.INFO;

    private static getCircularReplacer() {
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

    private static formatContext(context: any): string {
        try {
            return JSON.stringify(context, this.getCircularReplacer(), 2);
        } catch (error) {
            return '[Unable to stringify context]';
        }
    }

    static debug(message: string, context?: any): void {
        if (this.level <= LogLevel.DEBUG) {
            console.log(`[DEBUG] ${message}${context ? '\nContext: ' + this.formatContext(context) : ''}`);
        }
    }

    static info(message: string, context?: any): void {
        if (this.level <= LogLevel.INFO) {
            console.log(`[INFO] ${message}${context ? '\nContext: ' + this.formatContext(context) : ''}`);
        }
    }

    static warn(message: string, context?: any): void {
        if (this.level <= LogLevel.WARN) {
            console.warn(`[WARN] ${message}${context ? '\nContext: ' + this.formatContext(context) : ''}`);
        }
    }

    static error(message: string, context?: any): void {
        if (this.level <= LogLevel.ERROR) {
            console.error(`[ERROR] ${message}${context ? '\nContext: ' + this.formatContext(context) : ''}`);
        }
    }
}
