import { describe, it, expect } from '@jest/globals';
import { Session } from '../../../src/session/session';
import { MemoryDbAdapter } from '../../../src/db/memory-adapter';

const factories: Array<[string, () => Session]> = [
  ['new', () => new Session()],
  ['setState', () => { const s = new Session(); s.setState({}); return s; }],
  ['clearState', () => { const s = new Session(); s.set('old', 1); s.clearState(); return s; }],
  ['fromJSON', () => Session.fromJSON(JSON.parse(JSON.stringify(new Session().toJSON())))],
];

describe.each(factories)('Session state keys after %s', (_name, create) => {
  it.each(['toString', 'constructor', '__proto__'])('does not report an unstored %s key', key => {
    const session = create();
    expect(session.has(key)).toBe(false);
    expect(session.get(key)).toBeUndefined();
    expect(session.delete(key)).toBe(false);
  });

  it.each(['toString', 'constructor', '__proto__'])('stores and deletes %s as ordinary data', key => {
    const session = create();
    const value = { preference: 'window seat' };
    session.set(key, value);
    expect(session.has(key)).toBe(true);
    expect(session.get(key)).toEqual(value);
    expect(session.keys()).toEqual([key]);
    expect(JSON.parse(JSON.stringify(session.toJSON())).data[key]).toEqual(value);
    expect(session.delete(key)).toBe(true);
    expect(session.has(key)).toBe(false);
    expect(session.get(key)).toBeUndefined();
  });

  it('preserves an explicitly stored undefined value until deletion', () => {
    const session = create();
    session.set('optional', undefined);
    expect(session.has('optional')).toBe(true);
    expect(session.delete('optional')).toBe(true);
    expect(session.has('optional')).toBe(false);
  });
});

it('preserves special keys supplied through setState and a JSON round trip', () => {
  const state = JSON.parse('{"__proto__":{"seat":"window"},"constructor":2,"toString":3}');
  const session = new Session();
  session.setState(state);
  const restored = Session.fromJSON(JSON.parse(JSON.stringify(session.toJSON())));
  expect(restored.getState()).toEqual(state);
  expect(restored.delete('__proto__')).toBe(true);
  expect(restored.has('__proto__')).toBe(false);
  restored.set('__proto__', { seat: 'aisle' });
  expect(restored.keys()).toContain('__proto__');
  expect(restored.get('__proto__')).toEqual({ seat: 'aisle' });
});

it('preserves special keys across database save/load without inheriting unstored keys', async () => {
  const db = new MemoryDbAdapter();
  const session = new Session({ id: 'state-keys', db });
  session.set('__proto__', { preference: 'window seat' });
  await session.save();
  const restored = new Session({ id: session.id, db });
  await restored.load();
  expect(restored.get('__proto__')).toEqual({ preference: 'window seat' });
  expect(restored.keys()).toEqual(['__proto__']);
  expect(restored.has('toString')).toBe(false);
  restored.delete('__proto__');
  restored.set('__proto__', { preference: 'aisle' });
  expect(restored.keys()).toEqual(['__proto__']);
  expect(restored.get('__proto__')).toEqual({ preference: 'aisle' });
});
