/**
 * Performance Monitor - Track agent performance metrics
 * 
 * Provides latency, throughput, and error tracking for agents.
 */

import { randomUUID } from 'crypto';

/**
 * Metric types
 */
export type MetricType = 'counter' | 'gauge' | 'histogram' | 'timer';

/**
 * Metric entry
 */
export interface MetricEntry {
    name: string;
    type: MetricType;
    value: number;
    timestamp: number;
    labels?: Record<string, string>;
}

/**
 * Timer result
 */
export interface TimerResult {
    duration: number;
    startTime: number;
    endTime: number;
}

/**
 * Performance stats
 */
export interface PerformanceStats {
    count: number;
    sum: number;
    min: number;
    max: number;
    avg: number;
    p50: number;
    p95: number;
    p99: number;
}

/**
 * Performance Monitor configuration
 */
export interface PerformanceMonitorConfig {
    /** Enable automatic collection */
    autoCollect?: boolean;
    /** Collection interval in ms */
    collectInterval?: number;
    /** Max entries to keep */
    maxEntries?: number;
    /** Enable logging */
    logging?: boolean;
}

/**
 * PerformanceMonitor - Track and analyze performance metrics
 */
export class PerformanceMonitor {
    readonly id: string;
    private metrics: Map<string, MetricEntry[]>;
    private timers: Map<string, number>;
    private config: Required<PerformanceMonitorConfig>;
    private intervalHandle?: NodeJS.Timeout;

    constructor(config: PerformanceMonitorConfig = {}) {
        this.id = randomUUID();
        this.metrics = new Map();
        this.timers = new Map();
        this.config = {
            autoCollect: config.autoCollect ?? false,
            collectInterval: config.collectInterval ?? 60000,
            maxEntries: config.maxEntries ?? 10000,
            logging: config.logging ?? false,
        };

        if (this.config.autoCollect) {
            this.startAutoCollect();
        }
    }

    /**
     * Increment a counter
     */
    increment(name: string, value: number = 1, labels?: Record<string, string>): void {
        this.record(name, 'counter', value, labels);
    }

    /**
     * Set a gauge value
     */
    gauge(name: string, value: number, labels?: Record<string, string>): void {
        this.record(name, 'gauge', value, labels);
    }

    /**
     * Record a histogram value
     */
    histogram(name: string, value: number, labels?: Record<string, string>): void {
        this.record(name, 'histogram', value, labels);
    }

    /**
     * Start a timer
     */
    startTimer(name: string): string {
        const timerId = `${name}-${randomUUID().slice(0, 8)}`;
        this.timers.set(timerId, Date.now());
        return timerId;
    }

    /**
     * Stop a timer and record duration
     */
    stopTimer(timerId: string, labels?: Record<string, string>): TimerResult {
        const startTime = this.timers.get(timerId);
        if (!startTime) {
            throw new Error(`Timer not found: ${timerId}`);
        }

        const endTime = Date.now();
        const duration = endTime - startTime;

        // Extract name from timer ID
        const name = timerId.split('-').slice(0, -1).join('-');
        this.record(`${name}_duration_ms`, 'timer', duration, labels);

        this.timers.delete(timerId);
        return { duration, startTime, endTime };
    }

    /**
     * Time an async function
     */
    async time<T>(name: string, fn: () => Promise<T>, labels?: Record<string, string>): Promise<T> {
        const timerId = this.startTimer(name);
        try {
            const result = await fn();
            this.stopTimer(timerId, { ...labels, status: 'success' });
            return result;
        } catch (error) {
            this.stopTimer(timerId, { ...labels, status: 'error' });
            throw error;
        }
    }

    /**
     * Record a metric
     */
    private record(name: string, type: MetricType, value: number, labels?: Record<string, string>): void {
        const entry: MetricEntry = {
            name,
            type,
            value,
            timestamp: Date.now(),
            labels,
        };

        if (!this.metrics.has(name)) {
            this.metrics.set(name, []);
        }

        const entries = this.metrics.get(name)!;
        entries.push(entry);

        // Enforce max entries
        while (entries.length > this.config.maxEntries) {
            entries.shift();
        }

        if (this.config.logging) {
            console.log(`[Perf] ${name}: ${value}`);
        }
    }

    /**
     * Get stats for a metric
     */
    getStats(name: string, since?: number): PerformanceStats | null {
        const entries = this.metrics.get(name);
        if (!entries || entries.length === 0) return null;

        let values = entries.map(e => e.value);
        if (since) {
            values = entries.filter(e => e.timestamp >= since).map(e => e.value);
        }

        if (values.length === 0) return null;

        values.sort((a, b) => a - b);
        const sum = values.reduce((a, b) => a + b, 0);

        return {
            count: values.length,
            sum,
            min: values[0],
            max: values[values.length - 1],
            avg: sum / values.length,
            p50: this.percentile(values, 50),
            p95: this.percentile(values, 95),
            p99: this.percentile(values, 99),
        };
    }

    /**
     * Get all metric names
     */
    getMetricNames(): string[] {
        return Array.from(this.metrics.keys());
    }

    /**
     * Get recent entries
     */
    getRecent(name: string, count: number = 10): MetricEntry[] {
        const entries = this.metrics.get(name);
        if (!entries) return [];
        return entries.slice(-count);
    }

    /**
     * Clear metrics
     */
    clear(name?: string): void {
        if (name) {
            this.metrics.delete(name);
        } else {
            this.metrics.clear();
        }
    }

    /**
     * Export metrics
     */
    export(): { metrics: Record<string, MetricEntry[]>; stats: Record<string, PerformanceStats | null> } {
        const metrics: Record<string, MetricEntry[]> = {};
        const stats: Record<string, PerformanceStats | null> = {};

        for (const [name, entries] of this.metrics) {
            metrics[name] = entries;
            stats[name] = this.getStats(name);
        }

        return { metrics, stats };
    }

    /**
     * Calculate percentile
     */
    private percentile(sorted: number[], p: number): number {
        const index = Math.ceil((p / 100) * sorted.length) - 1;
        return sorted[Math.max(0, Math.min(index, sorted.length - 1))];
    }

    /**
     * Start auto-collection
     */
    private startAutoCollect(): void {
        this.intervalHandle = setInterval(() => {
            this.gauge('memory_heap_used', process.memoryUsage?.().heapUsed ?? 0);
            this.gauge('memory_heap_total', process.memoryUsage?.().heapTotal ?? 0);
        }, this.config.collectInterval);
    }

    /**
     * Stop auto-collection
     */
    stop(): void {
        if (this.intervalHandle) {
            clearInterval(this.intervalHandle);
            this.intervalHandle = undefined;
        }
    }
}

/**
 * Create performance monitor
 */
export function createPerformanceMonitor(config?: PerformanceMonitorConfig): PerformanceMonitor {
    return new PerformanceMonitor(config);
}

// Default export
export default PerformanceMonitor;
