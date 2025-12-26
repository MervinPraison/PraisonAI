/**
 * Events System Unit Tests
 */

import { EventEmitterPubSub, AgentEventBus, AgentEvents, createEventBus, createPubSub } from '../../../src/events';

describe('EventEmitterPubSub', () => {
  let pubsub: EventEmitterPubSub;

  beforeEach(() => {
    pubsub = new EventEmitterPubSub();
  });

  afterEach(async () => {
    await pubsub.close();
  });

  it('should publish and subscribe to events', async () => {
    const received: any[] = [];
    
    await pubsub.subscribe('test-topic', (event) => {
      received.push(event);
    });

    await pubsub.publish('test-topic', { message: 'hello' });
    
    expect(received.length).toBe(1);
    expect(received[0].data.message).toBe('hello');
    expect(received[0].topic).toBe('test-topic');
    expect(received[0].id).toBeDefined();
    expect(received[0].createdAt).toBeInstanceOf(Date);
  });

  it('should support multiple subscribers', async () => {
    let count = 0;
    
    await pubsub.subscribe('topic', () => { count++; });
    await pubsub.subscribe('topic', () => { count++; });
    
    await pubsub.publish('topic', {});
    
    expect(count).toBe(2);
  });

  it('should unsubscribe handlers', async () => {
    let count = 0;
    const handler = () => { count++; };
    
    await pubsub.subscribe('topic', handler);
    await pubsub.publish('topic', {});
    expect(count).toBe(1);
    
    await pubsub.unsubscribe('topic', handler);
    await pubsub.publish('topic', {});
    expect(count).toBe(1); // Should not increment
  });

  it('should include metadata in events', async () => {
    let receivedEvent: any;
    
    await pubsub.subscribe('topic', (event) => {
      receivedEvent = event;
    });

    await pubsub.publish('topic', { data: 'test' }, { source: 'unit-test' });
    
    expect(receivedEvent.metadata?.source).toBe('unit-test');
  });

  it('should wait for specific event with timeout', async () => {
    const promise = pubsub.waitFor('delayed-topic', 1000);
    
    setTimeout(() => {
      pubsub.publish('delayed-topic', { value: 42 });
    }, 50);

    const event = await promise;
    expect(event.data.value).toBe(42);
  });

  it('should timeout when waiting for event', async () => {
    await expect(pubsub.waitFor('never-topic', 50)).rejects.toThrow('Timeout');
  });

  it('should close and remove all listeners', async () => {
    let count = 0;
    await pubsub.subscribe('topic', () => { count++; });
    
    await pubsub.close();
    
    // After close, publishing should not trigger handlers
    const emitter = pubsub.getEmitter();
    expect(emitter.listenerCount('topic')).toBe(0);
  });
});

describe('AgentEventBus', () => {
  let bus: AgentEventBus;

  beforeEach(() => {
    bus = new AgentEventBus('agent-1');
  });

  afterEach(async () => {
    await bus.close();
  });

  it('should emit and receive agent events', async () => {
    let received: any;
    
    await bus.on('message', (data) => {
      received = data;
    });

    await bus.emit('message', { text: 'Hello' });
    
    expect(received.text).toBe('Hello');
  });

  it('should broadcast to all agents', async () => {
    const bus2 = new AgentEventBus('agent-2');
    let received: any;
    let sourceAgent: string | undefined;

    // Both buses share the same underlying pubsub for this test
    const sharedPubSub = createPubSub();
    const busA = new AgentEventBus('agent-A', sharedPubSub);
    const busB = new AgentEventBus('agent-B', sharedPubSub);

    await busB.onBroadcast('announcement', (data, source) => {
      received = data;
      sourceAgent = source;
    });

    await busA.broadcast('announcement', { info: 'Important!' });

    expect(received.info).toBe('Important!');
    expect(sourceAgent).toBe('agent-A');

    await busA.close();
    await busB.close();
    await bus2.close();
  });

  it('should send message to specific agent', async () => {
    const sharedPubSub = createPubSub();
    const busA = new AgentEventBus('agent-A', sharedPubSub);
    const busB = new AgentEventBus('agent-B', sharedPubSub);

    let receivedByB: any;

    await busB.on('direct', (data) => {
      receivedByB = data;
    });

    await busA.sendTo('agent-B', 'direct', { secret: 'message' });

    expect(receivedByB.secret).toBe('message');

    await busA.close();
    await busB.close();
  });
});

describe('AgentEvents constants', () => {
  it('should have standard event types', () => {
    expect(AgentEvents.STARTED).toBe('started');
    expect(AgentEvents.COMPLETED).toBe('completed');
    expect(AgentEvents.ERROR).toBe('error');
    expect(AgentEvents.TOOL_CALLED).toBe('tool_called');
    expect(AgentEvents.TOOL_RESULT).toBe('tool_result');
    expect(AgentEvents.MESSAGE_RECEIVED).toBe('message_received');
    expect(AgentEvents.MESSAGE_SENT).toBe('message_sent');
    expect(AgentEvents.HANDOFF_INITIATED).toBe('handoff_initiated');
    expect(AgentEvents.HANDOFF_COMPLETED).toBe('handoff_completed');
  });
});

describe('Factory functions', () => {
  it('should create EventBus', () => {
    const bus = createEventBus('test-agent');
    expect(bus).toBeInstanceOf(AgentEventBus);
  });

  it('should create PubSub', () => {
    const pubsub = createPubSub();
    expect(pubsub).toBeInstanceOf(EventEmitterPubSub);
  });
});
