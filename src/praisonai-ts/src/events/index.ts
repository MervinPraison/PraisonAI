/**
 * Event System - PubSub and Event Emitter for agent communication
 * Inspired by mastra's events module
 */

import { EventEmitter } from 'events';

export interface Event {
  id: string;
  topic: string;
  data: any;
  createdAt: Date;
  metadata?: Record<string, any>;
}

export type EventHandler = (event: Event, ack?: () => Promise<void>) => void | Promise<void>;

/**
 * Abstract PubSub base class
 */
export abstract class PubSub {
  abstract publish(topic: string, data: any, metadata?: Record<string, any>): Promise<void>;
  abstract subscribe(topic: string, handler: EventHandler): Promise<void>;
  abstract unsubscribe(topic: string, handler: EventHandler): Promise<void>;
  abstract close(): Promise<void>;
}

/**
 * In-memory EventEmitter-based PubSub implementation
 */
export class EventEmitterPubSub extends PubSub {
  private emitter: EventEmitter;
  private handlers: Map<string, Set<EventHandler>> = new Map();

  constructor(existingEmitter?: EventEmitter) {
    super();
    this.emitter = existingEmitter ?? new EventEmitter();
    this.emitter.setMaxListeners(100); // Allow many listeners
  }

  async publish(topic: string, data: any, metadata?: Record<string, any>): Promise<void> {
    const event: Event = {
      id: crypto.randomUUID(),
      topic,
      data,
      createdAt: new Date(),
      metadata
    };
    this.emitter.emit(topic, event);
  }

  async subscribe(topic: string, handler: EventHandler): Promise<void> {
    if (!this.handlers.has(topic)) {
      this.handlers.set(topic, new Set());
    }
    this.handlers.get(topic)!.add(handler);
    this.emitter.on(topic, handler);
  }

  async unsubscribe(topic: string, handler: EventHandler): Promise<void> {
    this.handlers.get(topic)?.delete(handler);
    this.emitter.off(topic, handler);
  }

  async close(): Promise<void> {
    this.emitter.removeAllListeners();
    this.handlers.clear();
  }

  /**
   * Wait for a specific event with optional timeout
   */
  async waitFor(topic: string, timeout?: number): Promise<Event> {
    return new Promise((resolve, reject) => {
      const timer = timeout ? setTimeout(() => {
        this.emitter.off(topic, handler);
        reject(new Error(`Timeout waiting for event: ${topic}`));
      }, timeout) : null;

      const handler = (event: Event) => {
        if (timer) clearTimeout(timer);
        this.emitter.off(topic, handler);
        resolve(event);
      };

      this.emitter.once(topic, handler);
    });
  }

  /**
   * Get the underlying EventEmitter
   */
  getEmitter(): EventEmitter {
    return this.emitter;
  }
}

/**
 * Agent Event Bus - Specialized event system for agent communication
 */
export class AgentEventBus {
  private pubsub: PubSub;
  private agentId: string;

  constructor(agentId: string, pubsub?: PubSub) {
    this.agentId = agentId;
    this.pubsub = pubsub ?? new EventEmitterPubSub();
  }

  /**
   * Emit an agent event
   */
  async emit(eventType: string, data: any): Promise<void> {
    await this.pubsub.publish(`agent:${this.agentId}:${eventType}`, data, {
      agentId: this.agentId,
      eventType
    });
  }

  /**
   * Listen for agent events
   */
  async on(eventType: string, handler: (data: any) => void | Promise<void>): Promise<void> {
    await this.pubsub.subscribe(`agent:${this.agentId}:${eventType}`, (event) => {
      handler(event.data);
    });
  }

  /**
   * Broadcast to all agents
   */
  async broadcast(eventType: string, data: any): Promise<void> {
    await this.pubsub.publish(`broadcast:${eventType}`, data, {
      sourceAgentId: this.agentId,
      eventType
    });
  }

  /**
   * Listen for broadcast events
   */
  async onBroadcast(eventType: string, handler: (data: any, sourceAgentId: string) => void | Promise<void>): Promise<void> {
    await this.pubsub.subscribe(`broadcast:${eventType}`, (event) => {
      handler(event.data, event.metadata?.sourceAgentId);
    });
  }

  /**
   * Send message to specific agent
   */
  async sendTo(targetAgentId: string, eventType: string, data: any): Promise<void> {
    await this.pubsub.publish(`agent:${targetAgentId}:${eventType}`, data, {
      sourceAgentId: this.agentId,
      targetAgentId,
      eventType
    });
  }

  async close(): Promise<void> {
    await this.pubsub.close();
  }
}

// Standard event types
export const AgentEvents = {
  STARTED: 'started',
  COMPLETED: 'completed',
  ERROR: 'error',
  TOOL_CALLED: 'tool_called',
  TOOL_RESULT: 'tool_result',
  MESSAGE_RECEIVED: 'message_received',
  MESSAGE_SENT: 'message_sent',
  HANDOFF_INITIATED: 'handoff_initiated',
  HANDOFF_COMPLETED: 'handoff_completed'
} as const;

// Factory functions
export function createEventBus(agentId: string): AgentEventBus {
  return new AgentEventBus(agentId);
}

export function createPubSub(): EventEmitterPubSub {
  return new EventEmitterPubSub();
}
