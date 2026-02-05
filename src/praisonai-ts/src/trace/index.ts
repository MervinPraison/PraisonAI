/**
 * Trace Module for PraisonAI TypeScript SDK
 * 
 * Python parity with praisonaiagents/trace module
 * 
 * Provides:
 * - Context event types and interfaces
 * - Trace sink protocols
 * - Context trace emitter
 */

// ============================================================================
// Event Types
// ============================================================================

/**
 * Context event types.
 * Python parity: praisonaiagents/trace
 */
export enum ContextEventType {
  AGENT_START = 'agent_start',
  AGENT_END = 'agent_end',
  TOOL_START = 'tool_start',
  TOOL_END = 'tool_end',
  LLM_START = 'llm_start',
  LLM_END = 'llm_end',
  ERROR = 'error',
  MESSAGE = 'message',
  HANDOFF = 'handoff',
  MEMORY_READ = 'memory_read',
  MEMORY_WRITE = 'memory_write',
}

/**
 * General event types.
 * Python parity: praisonaiagents/trace
 */
export enum EventType {
  START = 'start',
  END = 'end',
  ERROR = 'error',
  INFO = 'info',
  DEBUG = 'debug',
  TRACE = 'trace',
}

/**
 * Message types.
 * Python parity: praisonaiagents/trace
 */
export enum MessageType {
  USER = 'user',
  ASSISTANT = 'assistant',
  SYSTEM = 'system',
  TOOL = 'tool',
  FUNCTION = 'function',
}

// ============================================================================
// Context Event Interface
// ============================================================================

/**
 * Context event.
 * Python parity: praisonaiagents/trace
 */
export interface ContextEvent {
  type: ContextEventType;
  timestamp: Date;
  agentName?: string;
  toolName?: string;
  data?: Record<string, any>;
  metadata?: Record<string, any>;
  traceId?: string;
  spanId?: string;
  parentSpanId?: string;
}

/**
 * Create a context event.
 */
export function createContextEvent(
  type: ContextEventType,
  data?: Record<string, any>
): ContextEvent {
  return {
    type,
    timestamp: new Date(),
    data,
  };
}

// ============================================================================
// Trace Sink Protocols
// ============================================================================

/**
 * Trace sink protocol.
 * Python parity: praisonaiagents/trace
 */
export interface TraceSinkProtocol {
  emit(event: ContextEvent): void | Promise<void>;
  flush?(): void | Promise<void>;
  close?(): void | Promise<void>;
}

/**
 * Context trace sink protocol.
 * Python parity: praisonaiagents/trace
 */
export interface ContextTraceSinkProtocol extends TraceSinkProtocol {
  onAgentStart?(agentName: string, input: string): void | Promise<void>;
  onAgentEnd?(agentName: string, output: string): void | Promise<void>;
  onToolStart?(toolName: string, args: any): void | Promise<void>;
  onToolEnd?(toolName: string, result: any): void | Promise<void>;
  onError?(error: Error, context?: any): void | Promise<void>;
}

// ============================================================================
// Trace Sink Implementations
// ============================================================================

/**
 * Base trace sink.
 * Python parity: praisonaiagents/trace
 */
export class TraceSink implements TraceSinkProtocol {
  protected events: ContextEvent[] = [];

  emit(event: ContextEvent): void {
    this.events.push(event);
  }

  flush(): void {
    // Override in subclass
  }

  close(): void {
    this.flush();
    this.events = [];
  }

  getEvents(): ContextEvent[] {
    return [...this.events];
  }

  clear(): void {
    this.events = [];
  }
}

/**
 * Context trace sink with lifecycle hooks.
 * Python parity: praisonaiagents/trace
 */
export class ContextTraceSink extends TraceSink implements ContextTraceSinkProtocol {
  onAgentStart(agentName: string, input: string): void {
    this.emit({
      type: ContextEventType.AGENT_START,
      timestamp: new Date(),
      agentName,
      data: { input },
    });
  }

  onAgentEnd(agentName: string, output: string): void {
    this.emit({
      type: ContextEventType.AGENT_END,
      timestamp: new Date(),
      agentName,
      data: { output },
    });
  }

  onToolStart(toolName: string, args: any): void {
    this.emit({
      type: ContextEventType.TOOL_START,
      timestamp: new Date(),
      toolName,
      data: { args },
    });
  }

  onToolEnd(toolName: string, result: any): void {
    this.emit({
      type: ContextEventType.TOOL_END,
      timestamp: new Date(),
      toolName,
      data: { result },
    });
  }

  onError(error: Error, context?: any): void {
    this.emit({
      type: ContextEventType.ERROR,
      timestamp: new Date(),
      data: {
        error: error.message,
        stack: error.stack,
        context,
      },
    });
  }
}

/**
 * List-based context sink for collecting events.
 * Python parity: praisonaiagents/trace
 */
export class ContextListSink extends ContextTraceSink {
  getEventsByType(type: ContextEventType): ContextEvent[] {
    return this.events.filter(e => e.type === type);
  }

  getEventsByAgent(agentName: string): ContextEvent[] {
    return this.events.filter(e => e.agentName === agentName);
  }

  getEventsByTool(toolName: string): ContextEvent[] {
    return this.events.filter(e => e.toolName === toolName);
  }
}

/**
 * No-op context sink (discards all events).
 * Python parity: praisonaiagents/trace
 */
export class ContextNoOpSink implements ContextTraceSinkProtocol {
  emit(_event: ContextEvent): void {
    // No-op
  }

  onAgentStart(_agentName: string, _input: string): void {
    // No-op
  }

  onAgentEnd(_agentName: string, _output: string): void {
    // No-op
  }

  onToolStart(_toolName: string, _args: any): void {
    // No-op
  }

  onToolEnd(_toolName: string, _result: any): void {
    // No-op
  }

  onError(_error: Error, _context?: any): void {
    // No-op
  }
}

// ============================================================================
// Context Trace Emitter
// ============================================================================

/**
 * Context trace emitter for broadcasting events to multiple sinks.
 * Python parity: praisonaiagents/trace
 */
export class ContextTraceEmitter {
  private sinks: TraceSinkProtocol[] = [];

  /**
   * Add a sink.
   */
  addSink(sink: TraceSinkProtocol): void {
    this.sinks.push(sink);
  }

  /**
   * Remove a sink.
   */
  removeSink(sink: TraceSinkProtocol): boolean {
    const index = this.sinks.indexOf(sink);
    if (index >= 0) {
      this.sinks.splice(index, 1);
      return true;
    }
    return false;
  }

  /**
   * Emit an event to all sinks.
   */
  async emit(event: ContextEvent): Promise<void> {
    for (const sink of this.sinks) {
      await sink.emit(event);
    }
  }

  /**
   * Emit agent start event.
   */
  async emitAgentStart(agentName: string, input: string): Promise<void> {
    await this.emit({
      type: ContextEventType.AGENT_START,
      timestamp: new Date(),
      agentName,
      data: { input },
    });
  }

  /**
   * Emit agent end event.
   */
  async emitAgentEnd(agentName: string, output: string): Promise<void> {
    await this.emit({
      type: ContextEventType.AGENT_END,
      timestamp: new Date(),
      agentName,
      data: { output },
    });
  }

  /**
   * Emit tool start event.
   */
  async emitToolStart(toolName: string, args: any): Promise<void> {
    await this.emit({
      type: ContextEventType.TOOL_START,
      timestamp: new Date(),
      toolName,
      data: { args },
    });
  }

  /**
   * Emit tool end event.
   */
  async emitToolEnd(toolName: string, result: any): Promise<void> {
    await this.emit({
      type: ContextEventType.TOOL_END,
      timestamp: new Date(),
      toolName,
      data: { result },
    });
  }

  /**
   * Emit error event.
   */
  async emitError(error: Error, context?: any): Promise<void> {
    await this.emit({
      type: ContextEventType.ERROR,
      timestamp: new Date(),
      data: {
        error: error.message,
        stack: error.stack,
        context,
      },
    });
  }

  /**
   * Flush all sinks.
   */
  async flush(): Promise<void> {
    for (const sink of this.sinks) {
      if (sink.flush) {
        await sink.flush();
      }
    }
  }

  /**
   * Close all sinks.
   */
  async close(): Promise<void> {
    for (const sink of this.sinks) {
      if (sink.close) {
        await sink.close();
      }
    }
    this.sinks = [];
  }

  /**
   * Get sink count.
   */
  get sinkCount(): number {
    return this.sinks.length;
  }
}

// ============================================================================
// Trace Context
// ============================================================================

/**
 * Trace context for managing trace state.
 * Python parity: praisonaiagents/trace
 */
export interface TraceContext {
  traceId: string;
  spanId: string;
  parentSpanId?: string;
  startTime: Date;
  metadata?: Record<string, any>;
}

/**
 * Create a new trace context.
 * Python parity: praisonaiagents/trace
 */
export function traceContext(metadata?: Record<string, any>): TraceContext {
  return {
    traceId: generateTraceId(),
    spanId: generateSpanId(),
    startTime: new Date(),
    metadata,
  };
}

/**
 * Generate a trace ID.
 */
function generateTraceId(): string {
  return `trace_${Date.now()}_${Math.random().toString(36).substring(2, 11)}`;
}

/**
 * Generate a span ID.
 */
function generateSpanId(): string {
  return `span_${Date.now()}_${Math.random().toString(36).substring(2, 11)}`;
}

// ============================================================================
// Track Workflow
// ============================================================================

/**
 * Track workflow execution.
 * Python parity: praisonaiagents/trace
 */
export function trackWorkflow(
  workflowName: string,
  emitter: ContextTraceEmitter
): {
  start: () => Promise<void>;
  end: (result?: any) => Promise<void>;
  error: (error: Error) => Promise<void>;
} {
  const context = traceContext({ workflowName });
  
  return {
    async start(): Promise<void> {
      await emitter.emit({
        type: ContextEventType.AGENT_START,
        timestamp: new Date(),
        traceId: context.traceId,
        spanId: context.spanId,
        data: { workflowName, action: 'start' },
      });
    },
    
    async end(result?: any): Promise<void> {
      await emitter.emit({
        type: ContextEventType.AGENT_END,
        timestamp: new Date(),
        traceId: context.traceId,
        spanId: context.spanId,
        data: { workflowName, action: 'end', result },
      });
    },
    
    async error(error: Error): Promise<void> {
      await emitter.emitError(error, { workflowName, traceId: context.traceId });
    },
  };
}
