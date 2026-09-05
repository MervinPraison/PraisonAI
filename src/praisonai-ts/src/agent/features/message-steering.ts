/**
 * Real-time message steering (Python parity: `Agent(message_steering=...)`,
 * `agent/message_steering.py` `MessageSteering` / `SteeringMixin`,
 * `agent/protocols.py` `SteeringPriority` / `MessageSteeringProtocol`).
 *
 * Someone watching an agent work can send it guidance without cancelling the
 * run: `agent.steer("check the staging config first")`. The note is queued by
 * priority and folded into the next turn's prompt, with wording that tells the
 * model how urgently to act on it.
 *
 * Priority matters and is preserved end to end. An INTERRUPT that arrives as
 * ordinary "consider this feedback" guidance is worse than no steering at
 * all: the operator believes they stopped the agent, and it carried on.
 */

/** Python `SteeringPriority`. */
export enum SteeringPriority {
  LOW = 1,
  NORMAL = 5,
  HIGH = 10,
  URGENT = 20,
  INTERRUPT = 30,
}

/** Python `SteeringMessage`. */
export interface SteeringMessage {
  content: string;
  priority: SteeringPriority;
  metadata?: Record<string, unknown>;
}

/** The interface an Agent needs from a steering implementation. */
export interface MessageSteeringProtocol {
  readonly enabled: boolean;
  queueMessage(message: string, priority?: number): string;
  /** Every pending message, highest priority first, removing them from the queue. */
  drain(): SteeringMessage[];
  hasPendingMessages(): boolean;
  clearMessages(): number;
  enable(): void;
  disable(): void;
}

/** Python's priority-aware wording, shared by every injection path. */
export function formatSteeringNote(content: string, priority: SteeringPriority): string {
  if (priority >= SteeringPriority.INTERRUPT) {
    return `[INTERRUPT USER GUIDANCE]: ${content}\nPlease stop current work and follow this guidance immediately.`;
  }
  if (priority >= SteeringPriority.HIGH) {
    return `[URGENT USER GUIDANCE]: ${content}\nPlease acknowledge and adjust your approach accordingly.`;
  }
  return `[USER GUIDANCE]: ${content}\nPlease consider this feedback as you continue.`;
}

function toPriority(value: number): SteeringPriority {
  const known = [
    SteeringPriority.LOW, SteeringPriority.NORMAL, SteeringPriority.HIGH,
    SteeringPriority.URGENT, SteeringPriority.INTERRUPT,
  ];
  return known.includes(value as SteeringPriority) ? (value as SteeringPriority) : SteeringPriority.NORMAL;
}

/**
 * The built-in implementation: a bounded priority queue (Python
 * `AgentMessageQueue`, default 50 messages).
 */
export class MessageSteering implements MessageSteeringProtocol {
  private queue: SteeringMessage[] = [];
  private _enabled = true;
  private counter = 0;

  constructor(readonly maxMessages: number = 50) {}

  get enabled(): boolean {
    return this._enabled;
  }

  queueMessage(message: string, priority: number = SteeringPriority.NORMAL): string {
    if (!this._enabled) return '';
    if (this.queue.length >= this.maxMessages) return '';
    this.queue.push({
      content: message,
      priority: toPriority(priority),
      metadata: { timestamp: Date.now() },
    });
    this.counter += 1;
    return `steer_${Date.now()}_${this.counter}`;
  }

  /**
   * Take every pending message, highest priority first. Python drains one per
   * check pre-turn and all of them mid-run; taking them all at the one
   * injection point this SDK has means a queued note is never left behind
   * while the agent answers without it.
   */
  drain(): SteeringMessage[] {
    if (!this._enabled || this.queue.length === 0) return [];
    // Stable within a priority so two notes of equal urgency stay in the
    // order the operator wrote them.
    const ordered = this.queue
      .map((message, index) => ({ message, index }))
      .sort((a, b) => b.message.priority - a.message.priority || a.index - b.index)
      .map((entry) => entry.message);
    this.queue = [];
    return ordered;
  }

  hasPendingMessages(): boolean {
    return this.queue.length > 0;
  }

  clearMessages(): number {
    const count = this.queue.length;
    this.queue = [];
    return count;
  }

  enable(): void {
    this._enabled = true;
  }

  disable(): void {
    this._enabled = false;
  }
}

function isSteeringProtocol(value: unknown): value is MessageSteeringProtocol {
  if (value === null || typeof value !== 'object') return false;
  const v = value as Record<string, unknown>;
  return typeof v.queueMessage === 'function' && typeof v.drain === 'function';
}

/**
 * Resolve the constructor option: `true` for the built-in implementation, a
 * custom object implementing the protocol, or `undefined` when off
 * (Python `SteeringMixin._init_message_steering`).
 */
export function resolveMessageSteering(
  input: boolean | Record<string, unknown> | undefined | null
): MessageSteeringProtocol | undefined {
  if (input === undefined || input === null || input === false) return undefined;
  if (input === true) return new MessageSteering();
  if (isSteeringProtocol(input)) return input;
  throw new Error(
    'messageSteering must be true, false, or an object with queueMessage() and drain().'
  );
}

/** The block appended to a prompt for the drained messages, or '' when there are none. */
export function steeringNotesFor(messages: readonly SteeringMessage[]): string {
  if (messages.length === 0) return '';
  return messages.map((m) => formatSteeringNote(m.content, m.priority)).join('\n\n');
}
