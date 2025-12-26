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
