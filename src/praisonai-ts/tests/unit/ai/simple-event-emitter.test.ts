/**
 * SimpleEventEmitter, exercised through ApprovalManager.
 *
 * It replaces Node's `EventEmitter` so the Agent import graph stops pulling in
 * the `events` builtin, which made the bundle unloadable in a webview. That is
 * the right fix, but it swaps a battle-tested implementation for a hand-rolled
 * one, and the differences that matter are not the obvious methods -- they are
 * `once` unwrapping, and mutation during `emit`.
 *
 * The class is not exported, so these drive it through the public subclass,
 * which is also how it is actually used.
 */
import { ApprovalManager } from '../../../src/ai/tool-approval';

/** ApprovalManager is the only public SimpleEventEmitter. */
const emitter = () => new ApprovalManager() as unknown as {
  on(e: string, l: (...a: any[]) => void): unknown;
  once(e: string, l: (...a: any[]) => void): unknown;
  off(e: string, l: (...a: any[]) => void): unknown;
  removeAllListeners(e?: string): unknown;
  emit(e: string, ...a: any[]): boolean;
};

describe('SimpleEventEmitter', () => {
  it('delivers an event to a listener with its arguments', () => {
    const seen: unknown[][] = [];
    const e = emitter();
    e.on('x', (...args) => seen.push(args));
    e.emit('x', 1, 'two');
    expect(seen).toEqual([[1, 'two']]);
  });

  it('calls multiple listeners in registration order', () => {
    // Node guarantees this, and approval flows rely on it: a manager that
    // records a decision before notifying is a different sequence than one
    // that notifies first.
    const order: string[] = [];
    const e = emitter();
    e.on('x', () => order.push('first'));
    e.on('x', () => order.push('second'));
    e.emit('x');
    expect(order).toEqual(['first', 'second']);
  });

  it('emit reports whether anything was listening', () => {
    const e = emitter();
    expect(e.emit('nobody')).toBe(false);
    e.on('somebody', () => {});
    expect(e.emit('somebody')).toBe(true);
  });

  it('once fires exactly once', () => {
    let calls = 0;
    const e = emitter();
    e.once('x', () => { calls++; });
    e.emit('x');
    e.emit('x');
    e.emit('x');
    expect(calls).toBe(1);
  });

  it('once and on can coexist on the same event', () => {
    const order: string[] = [];
    const e = emitter();
    e.once('x', () => order.push('once'));
    e.on('x', () => order.push('always'));
    e.emit('x');
    e.emit('x');
    expect(order).toEqual(['once', 'always', 'always']);
  });

  it('off removes a once-listener by its ORIGINAL reference', () => {
    // The subtle one. `once` registers a wrapper, so an `off` that compared
    // only by identity would never find the caller's function and the listener
    // would leak -- firing after the caller believed it had unsubscribed.
    let calls = 0;
    const listener = () => { calls++; };
    const e = emitter();
    e.once('x', listener);
    e.off('x', listener);
    e.emit('x');
    expect(calls).toBe(0);
  });

  it('off removes an on-listener', () => {
    let calls = 0;
    const listener = () => { calls++; };
    const e = emitter();
    e.on('x', listener);
    e.off('x', listener);
    e.emit('x');
    expect(calls).toBe(0);
  });

  it('off leaves the other listeners in place', () => {
    // The pair: "remove everything" would satisfy both tests above.
    const order: string[] = [];
    const doomed = () => order.push('doomed');
    const e = emitter();
    e.on('x', doomed);
    e.on('x', () => order.push('kept'));
    e.off('x', doomed);
    e.emit('x');
    expect(order).toEqual(['kept']);
  });

  it('off on an unknown event does not throw', () => {
    const e = emitter();
    expect(() => e.off('never-registered', () => {})).not.toThrow();
  });

  it('a listener removing itself during emit does not skip the next one', () => {
    // The classic array-mutation bug: splicing during a forward loop shifts
    // every later index down by one, so the following listener is skipped.
    // `emit` iterating a copy is what prevents it -- and nothing else would
    // catch this, because the emit still reports success.
    const order: string[] = [];
    const e = emitter();
    const first = () => { order.push('first'); e.off('x', first); };
    e.on('x', first);
    e.on('x', () => order.push('second'));
    e.emit('x');
    expect(order).toEqual(['first', 'second']);
  });

  it('a listener added during emit does not fire in that same emit', () => {
    // Node's behaviour: the copy is taken before dispatch, so a listener
    // registered mid-dispatch waits for the next event rather than being
    // invoked with arguments it was never designed for.
    const order: string[] = [];
    const e = emitter();
    e.on('x', () => {
      order.push('first');
      e.on('x', () => order.push('added'));
    });
    e.emit('x');
    expect(order).toEqual(['first']);
    e.emit('x');
    expect(order).toEqual(['first', 'first', 'added']);
  });

  it('removeAllListeners clears one event and leaves the others', () => {
    const order: string[] = [];
    const e = emitter();
    e.on('a', () => order.push('a'));
    e.on('b', () => order.push('b'));
    e.removeAllListeners('a');
    e.emit('a');
    e.emit('b');
    expect(order).toEqual(['b']);
  });

  it('removeAllListeners with no event clears everything', () => {
    const order: string[] = [];
    const e = emitter();
    e.on('a', () => order.push('a'));
    e.on('b', () => order.push('b'));
    e.removeAllListeners();
    e.emit('a');
    e.emit('b');
    expect(order).toEqual([]);
  });

  it('events are isolated from each other', () => {
    const order: string[] = [];
    const e = emitter();
    e.on('a', () => order.push('a'));
    e.emit('b');
    expect(order).toEqual([]);
  });
});
