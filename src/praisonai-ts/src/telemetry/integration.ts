/**
 * Telemetry Integration - External telemetry system integrations
 * 
 * Provides hooks for connecting to external observability systems.
 */

import { randomUUID } from 'crypto';

/**
 * Telemetry sink types
 */
export type TelemetrySinkType = 'console' | 'http' | 'custom';

/**
 * Telemetry record
 */
export interface TelemetryRecord {
    id: string;
    type: 'event' | 'metric' | 'trace' | 'log';
    name: string;
    value?: number;
    tags?: Record<string, string>;
    timestamp: number;
    data?: any;
}

/**
 * Telemetry sink interface
 */
export interface TelemetrySink {
    name: string;
    type: TelemetrySinkType;
    send(records: TelemetryRecord[]): Promise<void>;
    flush?(): Promise<void>;
    close?(): Promise<void>;
}

/**
 * Console sink
 */
export class ConsoleSink implements TelemetrySink {
    name = 'console';
    type: TelemetrySinkType = 'console';
    private format: 'json' | 'pretty';

    constructor(format: 'json' | 'pretty' = 'pretty') {
        this.format = format;
    }

    async send(records: TelemetryRecord[]): Promise<void> {
        for (const record of records) {
            if (this.format === 'json') {
                console.log(JSON.stringify(record));
            } else {
                console.log(`[${record.type}] ${record.name}: ${record.value ?? record.data ?? ''}`);
            }
        }
    }
}

/**
 * HTTP sink
 */
export class HTTPSink implements TelemetrySink {
    name: string;
    type: TelemetrySinkType = 'http';
    private endpoint: string;
    private headers: Record<string, string>;
    private batchSize: number;
    private buffer: TelemetryRecord[];

    constructor(config: {
        name?: string;
        endpoint: string;
        headers?: Record<string, string>;
        batchSize?: number;
    }) {
        this.name = config.name ?? 'http';
        this.endpoint = config.endpoint;
        this.headers = config.headers ?? {};
        this.batchSize = config.batchSize ?? 100;
        this.buffer = [];
    }

    async send(records: TelemetryRecord[]): Promise<void> {
        this.buffer.push(...records);

        while (this.buffer.length >= this.batchSize) {
            const batch = this.buffer.splice(0, this.batchSize);
            await this.sendBatch(batch);
        }
    }

    async flush(): Promise<void> {
        if (this.buffer.length > 0) {
            const batch = this.buffer.splice(0);
            await this.sendBatch(batch);
        }
    }

    private async sendBatch(records: TelemetryRecord[]): Promise<void> {
        try {
            await fetch(this.endpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...this.headers,
                },
                body: JSON.stringify({ records }),
            });
        } catch {
            // Silently fail - never break user applications
        }
    }
}

/**
 * Integration hub configuration
 */
export interface TelemetryIntegrationConfig {
    /** Sinks to send records to */
    sinks?: TelemetrySink[];
    /** Buffer size before auto-flush */
    bufferSize?: number;
    /** Flush interval in ms */
    flushInterval?: number;
    /** Enable/disable */
    enabled?: boolean;
}

/**
 * TelemetryIntegration - Hub for external telemetry systems
 */
export class TelemetryIntegration {
    readonly id: string;
    private sinks: TelemetrySink[];
    private buffer: TelemetryRecord[];
    private bufferSize: number;
    private flushInterval: number;
    private enabled: boolean;
    private flushTimer?: NodeJS.Timeout;

    constructor(config?: TelemetryIntegrationConfig) {
        this.id = randomUUID();
        this.sinks = config?.sinks ?? [];
        this.buffer = [];
        this.bufferSize = config?.bufferSize ?? 100;
        this.flushInterval = config?.flushInterval ?? 60000;
        this.enabled = config?.enabled ?? true;

        if (this.enabled && this.flushInterval > 0) {
            this.startFlushTimer();
        }
    }

    /**
     * Add sink
     */
    addSink(sink: TelemetrySink): void {
        this.sinks.push(sink);
    }

    /**
     * Remove sink by name
     */
    removeSink(name: string): boolean {
        const index = this.sinks.findIndex(s => s.name === name);
        if (index >= 0) {
            this.sinks.splice(index, 1);
            return true;
        }
        return false;
    }

    /**
     * Record event
     */
    event(name: string, data?: any, tags?: Record<string, string>): void {
        this.record({ type: 'event', name, data, tags });
    }

    /**
     * Record metric
     */
    metric(name: string, value: number, tags?: Record<string, string>): void {
        this.record({ type: 'metric', name, value, tags });
    }

    /**
     * Record trace
     */
    trace(name: string, data: any, tags?: Record<string, string>): void {
        this.record({ type: 'trace', name, data, tags });
    }

    /**
     * Record log
     */
    log(name: string, data: any, tags?: Record<string, string>): void {
        this.record({ type: 'log', name, data, tags });
    }

    /**
     * Record telemetry
     */
    private record(partial: Omit<TelemetryRecord, 'id' | 'timestamp'>): void {
        if (!this.enabled) return;

        const record: TelemetryRecord = {
            id: randomUUID(),
            timestamp: Date.now(),
            ...partial,
        };

        this.buffer.push(record);

        if (this.buffer.length >= this.bufferSize) {
            this.flush();
        }
    }

    /**
     * Flush all buffered records
     */
    async flush(): Promise<void> {
        if (this.buffer.length === 0) return;

        const records = this.buffer.splice(0);

        await Promise.all(
            this.sinks.map(sink => sink.send(records).catch(() => { }))
        );
    }

    /**
     * Close integration
     */
    async close(): Promise<void> {
        this.stopFlushTimer();
        await this.flush();

        for (const sink of this.sinks) {
            await sink.flush?.();
            await sink.close?.();
        }
    }

    /**
     * Enable/disable
     */
    setEnabled(enabled: boolean): void {
        this.enabled = enabled;
        if (enabled) {
            this.startFlushTimer();
        } else {
            this.stopFlushTimer();
        }
    }

    /**
     * Start flush timer
     */
    private startFlushTimer(): void {
        if (this.flushTimer) return;
        this.flushTimer = setInterval(() => this.flush(), this.flushInterval);
    }

    /**
     * Stop flush timer
     */
    private stopFlushTimer(): void {
        if (this.flushTimer) {
            clearInterval(this.flushTimer);
            this.flushTimer = undefined;
        }
    }

    /**
     * Get stats
     */
    getStats(): { sinkCount: number; bufferSize: number; enabled: boolean } {
        return {
            sinkCount: this.sinks.length,
            bufferSize: this.buffer.length,
            enabled: this.enabled,
        };
    }
}

/**
 * Create telemetry integration
 */
export function createTelemetryIntegration(config?: TelemetryIntegrationConfig): TelemetryIntegration {
    return new TelemetryIntegration(config);
}

/**
 * Create console sink
 */
export function createConsoleSink(format?: 'json' | 'pretty'): ConsoleSink {
    return new ConsoleSink(format);
}

/**
 * Create HTTP sink
 */
export function createHTTPSink(endpoint: string, options?: { headers?: Record<string, string>; batchSize?: number }): HTTPSink {
    return new HTTPSink({ endpoint, ...options });
}

// Default export
export default TelemetryIntegration;
