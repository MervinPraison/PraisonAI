/**
 * Telemetry - Usage tracking and analytics
 */

export interface TelemetryEvent {
  name: string;
  timestamp: number;
  properties?: Record<string, any>;
  userId?: string;
  sessionId?: string;
}

export interface TelemetryConfig {
  enabled?: boolean;
  endpoint?: string;
  batchSize?: number;
  flushInterval?: number;
}

/**
 * Telemetry collector for tracking usage
 */
export class TelemetryCollector {
  private events: TelemetryEvent[] = [];
  private enabled: boolean;
  private endpoint?: string;
  private batchSize: number;
  private flushInterval: number;
  private flushTimer?: NodeJS.Timeout;
  private userId?: string;
  private sessionId: string;

  constructor(config: TelemetryConfig = {}) {
    this.enabled = config.enabled ?? this.checkEnabled();
    this.endpoint = config.endpoint;
    this.batchSize = config.batchSize ?? 100;
    this.flushInterval = config.flushInterval ?? 60000;
    this.sessionId = this.generateSessionId();

    if (this.enabled && this.flushInterval > 0) {
      this.startFlushTimer();
    }
  }

  private checkEnabled(): boolean {
    const disabled = process.env.PRAISONAI_TELEMETRY_DISABLED === 'true' ||
      process.env.PRAISONAI_DISABLE_TELEMETRY === 'true' ||
      process.env.DO_NOT_TRACK === 'true';
    return !disabled;
  }

  /**
   * Track an event
   */
  track(name: string, properties?: Record<string, any>): void {
    if (!this.enabled) return;

    const event: TelemetryEvent = {
      name,
      timestamp: Date.now(),
      properties,
      userId: this.userId,
      sessionId: this.sessionId
    };

    this.events.push(event);

    if (this.events.length >= this.batchSize) {
      this.flush();
    }
  }

  /**
   * Track feature usage
   */
  trackFeatureUsage(feature: string, metadata?: Record<string, any>): void {
    this.track('feature_usage', { feature, ...metadata });
  }

  /**
   * Track agent execution
   */
  trackAgentExecution(agentName: string, duration: number, success: boolean): void {
    this.track('agent_execution', { agentName, duration, success });
  }

  /**
   * Track tool call
   */
  trackToolCall(toolName: string, duration: number, success: boolean): void {
    this.track('tool_call', { toolName, duration, success });
  }

  /**
   * Track LLM call
   */
  trackLLMCall(provider: string, model: string, tokens: number, duration: number): void {
    this.track('llm_call', { provider, model, tokens, duration });
  }

  /**
   * Track error
   */
  trackError(error: string, context?: Record<string, any>): void {
    this.track('error', { error, ...context });
  }

  /**
   * Set user ID
   */
  setUserId(userId: string): void {
    this.userId = userId;
  }

  /**
   * Flush events
   */
  async flush(): Promise<void> {
    if (this.events.length === 0) return;

    const eventsToSend = [...this.events];
    this.events = [];

    if (this.endpoint) {
      try {
        await fetch(this.endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ events: eventsToSend })
        });
      } catch (error) {
        // Silently fail - never break user applications
      }
    }
  }

  /**
   * Enable telemetry
   */
  enable(): void {
    this.enabled = true;
    this.startFlushTimer();
  }

  /**
   * Disable telemetry
   */
  disable(): void {
    this.enabled = false;
    this.stopFlushTimer();
    this.events = [];
  }

  /**
   * Check if telemetry is enabled
   */
  isEnabled(): boolean {
    return this.enabled;
  }

  /**
   * Get pending events count
   */
  getPendingCount(): number {
    return this.events.length;
  }

  /**
   * Cleanup resources
   */
  cleanup(): void {
    this.stopFlushTimer();
    this.flush();
  }

  private startFlushTimer(): void {
    if (this.flushTimer) return;
    this.flushTimer = setInterval(() => this.flush(), this.flushInterval);
  }

  private stopFlushTimer(): void {
    if (this.flushTimer) {
      clearInterval(this.flushTimer);
      this.flushTimer = undefined;
    }
  }

  private generateSessionId(): string {
    return `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }
}

// Global telemetry instance
let globalTelemetry: TelemetryCollector | null = null;

/**
 * Get global telemetry instance
 */
export function getTelemetry(): TelemetryCollector {
  if (!globalTelemetry) {
    globalTelemetry = new TelemetryCollector();
  }
  return globalTelemetry;
}

/**
 * Enable telemetry
 */
export function enableTelemetry(): void {
  getTelemetry().enable();
}

/**
 * Disable telemetry
 */
export function disableTelemetry(): void {
  getTelemetry().disable();
}

/**
 * Cleanup telemetry resources
 */
export function cleanupTelemetry(): void {
  if (globalTelemetry) {
    globalTelemetry.cleanup();
  }
}

/**
 * AgentTelemetry - Agent-focused telemetry wrapper
 * 
 * @example Simple usage (3 lines)
 * ```typescript
 * import { Agent } from 'praisonai';
 * 
 * // Enable telemetry on agent
 * const agent = new Agent({ 
 *   instructions: 'You are helpful',
 *   telemetry: true  // Opt-in telemetry
 * });
 * await agent.chat('Hello!');  // Automatically tracked
 * ```
 * 
 * @example Manual tracking
 * ```typescript
 * import { AgentTelemetry } from 'praisonai';
 * 
 * const telemetry = new AgentTelemetry('MyAgent');
 * const result = await telemetry.trackChat(async () => {
 *   return await agent.chat('Hello!');
 * });
 * console.log(telemetry.getStats());
 * ```
 */
export interface AgentStats {
  totalChats: number;
  successfulChats: number;
  failedChats: number;
  totalDuration: number;
  avgDuration: number;
  totalTokens: number;
  toolCalls: number;
}

export class AgentTelemetry {
  private agentName: string;
  private collector: TelemetryCollector;
  private stats: AgentStats = {
    totalChats: 0,
    successfulChats: 0,
    failedChats: 0,
    totalDuration: 0,
    avgDuration: 0,
    totalTokens: 0,
    toolCalls: 0
  };

  constructor(agentName: string, config?: TelemetryConfig) {
    this.agentName = agentName;
    this.collector = config ? new TelemetryCollector(config) : getTelemetry();
  }

  /**
   * Track a chat execution
   */
  async trackChat<T>(fn: () => Promise<T>): Promise<T> {
    const startTime = Date.now();
    this.stats.totalChats++;

    try {
      const result = await fn();
      const duration = Date.now() - startTime;

      this.stats.successfulChats++;
      this.stats.totalDuration += duration;
      this.stats.avgDuration = this.stats.totalDuration / this.stats.totalChats;

      this.collector.trackAgentExecution(this.agentName, duration, true);

      return result;
    } catch (error) {
      const duration = Date.now() - startTime;

      this.stats.failedChats++;
      this.stats.totalDuration += duration;
      this.stats.avgDuration = this.stats.totalDuration / this.stats.totalChats;

      this.collector.trackAgentExecution(this.agentName, duration, false);
      this.collector.trackError(String(error), { agent: this.agentName });

      throw error;
    }
  }

  /**
   * Track a tool call
   */
  trackToolCall(toolName: string, duration: number, success: boolean): void {
    this.stats.toolCalls++;
    this.collector.trackToolCall(toolName, duration, success);
  }

  /**
   * Track token usage
   */
  trackTokens(tokens: number): void {
    this.stats.totalTokens += tokens;
  }

  /**
   * Get agent statistics
   */
  getStats(): AgentStats {
    return { ...this.stats };
  }

  /**
   * Reset statistics
   */
  resetStats(): void {
    this.stats = {
      totalChats: 0,
      successfulChats: 0,
      failedChats: 0,
      totalDuration: 0,
      avgDuration: 0,
      totalTokens: 0,
      toolCalls: 0
    };
  }

  /**
   * Get success rate
   */
  getSuccessRate(): number {
    if (this.stats.totalChats === 0) return 0;
    return (this.stats.successfulChats / this.stats.totalChats) * 100;
  }

  /**
   * Print summary
   */
  printSummary(): void {
    console.log(`\n📊 Agent Telemetry: ${this.agentName}`);
    console.log(`   Total chats: ${this.stats.totalChats}`);
    console.log(`   Success rate: ${this.getSuccessRate().toFixed(1)}%`);
    console.log(`   Avg duration: ${this.stats.avgDuration.toFixed(0)}ms`);
    console.log(`   Tool calls: ${this.stats.toolCalls}`);
    console.log(`   Total tokens: ${this.stats.totalTokens}`);
  }
}

/**
 * Create agent telemetry
 */
export function createAgentTelemetry(agentName: string, config?: TelemetryConfig): AgentTelemetry {
  return new AgentTelemetry(agentName, config);
}

// ============================================================================
// Python Parity: MinimalTelemetry and Performance Mode
// ============================================================================

/**
 * MinimalTelemetry - Lightweight telemetry with minimal overhead.
 * Python parity with praisonaiagents/telemetry/telemetry.py MinimalTelemetry.
 */
export class MinimalTelemetry {
  private _enabled: boolean;
  private _performanceMode: boolean = false;

  constructor(enabled: boolean = true) {
    this._enabled = enabled && this.checkEnabled();
  }

  private checkEnabled(): boolean {
    const disabled = process.env.PRAISONAI_TELEMETRY_DISABLED === 'true' ||
      process.env.PRAISONAI_DISABLE_TELEMETRY === 'true' ||
      process.env.DO_NOT_TRACK === 'true';
    return !disabled;
  }

  get enabled(): boolean {
    return this._enabled;
  }

  /**
   * Track feature usage.
   */
  trackFeatureUsage(feature: string, metadata?: Record<string, any>): void {
    if (!this._enabled || this._performanceMode) return;
    getTelemetry().trackFeatureUsage(feature, metadata);
  }

  /**
   * Track agent execution.
   */
  trackAgentExecution(agentName: string, duration: number, success: boolean): void {
    if (!this._enabled) return;
    getTelemetry().trackAgentExecution(agentName, duration, success);
  }

  /**
   * Track tool call.
   */
  trackToolCall(toolName: string, duration: number, success: boolean): void {
    if (!this._enabled) return;
    getTelemetry().trackToolCall(toolName, duration, success);
  }

  /**
   * Track LLM call.
   */
  trackLLMCall(provider: string, model: string, tokens: number, duration: number): void {
    if (!this._enabled) return;
    getTelemetry().trackLLMCall(provider, model, tokens, duration);
  }

  /**
   * Track error.
   */
  trackError(error: string, context?: Record<string, any>): void {
    if (!this._enabled) return;
    getTelemetry().trackError(error, context);
  }

  /**
   * Enable telemetry.
   */
  enable(): void {
    this._enabled = true;
  }

  /**
   * Disable telemetry.
   */
  disable(): void {
    this._enabled = false;
  }

  /**
   * Enable performance mode (minimal tracking).
   */
  enablePerformanceMode(): void {
    this._performanceMode = true;
  }

  /**
   * Disable performance mode.
   */
  disablePerformanceMode(): void {
    this._performanceMode = false;
  }

  /**
   * Shutdown telemetry.
   */
  shutdown(): void {
    this._enabled = false;
    cleanupTelemetry();
  }
}

// Global minimal telemetry instance
let globalMinimalTelemetry: MinimalTelemetry | null = null;

/**
 * Get global minimal telemetry instance.
 */
export function getMinimalTelemetry(): MinimalTelemetry {
  if (!globalMinimalTelemetry) {
    globalMinimalTelemetry = new MinimalTelemetry();
  }
  return globalMinimalTelemetry;
}

/**
 * Enable performance mode for minimal telemetry overhead.
 * Python parity with praisonaiagents/telemetry enable_performance_mode.
 */
export function enablePerformanceMode(): void {
  getMinimalTelemetry().enablePerformanceMode();
}

/**
 * Disable performance mode to resume full telemetry tracking.
 * Python parity with praisonaiagents/telemetry disable_performance_mode.
 */
export function disablePerformanceMode(): void {
  getMinimalTelemetry().disablePerformanceMode();
}

/**
 * Clean up telemetry resources including thread pools and queues.
 * Python parity with praisonaiagents/telemetry cleanup_telemetry_resources.
 */
export function cleanupTelemetryResources(): void {
  cleanupTelemetry();
}

// Re-export PerformanceMonitor
export {
  PerformanceMonitor,
  createPerformanceMonitor,
  type MetricType,
  type MetricEntry,
  type TimerResult,
  type PerformanceStats,
  type PerformanceMonitorConfig,
} from './performance';

// Re-export TelemetryIntegration
export {
  TelemetryIntegration,
  createTelemetryIntegration,
  ConsoleSink,
  HTTPSink,
  createConsoleSink,
  createHTTPSink,
  type TelemetryRecord,
  type TelemetrySink,
  type TelemetrySinkType,
  type TelemetryIntegrationConfig,
} from './integration';
