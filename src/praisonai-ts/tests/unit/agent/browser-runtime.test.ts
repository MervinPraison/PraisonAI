/**
 * The Agent constructor must not require a Node `process` global.
 *
 * A Tauri/React-Native webview has no `process`. Before this guard, five
 * unguarded `process.env` dereferences in the constructor threw
 * `ReferenceError: process is not defined` on the very first `new Agent(...)`,
 * so the bundle failed at import time on a device while every Node test passed.
 *
 * The test deletes the global rather than mocking `getEnv`, because mocking the
 * accessor would pass even if a new raw `process.env` deref were added.
 */
import { Agent, writeTokenToStdout } from '../../../src/agent/simple';

describe('Agent in a runtime with no process global', () => {
  const saved = (globalThis as any).process;

  beforeEach(() => {
    delete (globalThis as any).process;
  });

  afterEach(() => {
    (globalThis as any).process = saved;
  });

  it('constructs without throwing', () => {
    expect(() => new Agent({ instructions: 'You are helpful' })).not.toThrow();
  });

  it('falls back to the default model when no env is readable', () => {
    const agent = new Agent({ instructions: 'You are helpful' });
    expect((agent as any).llm).toBe('gpt-4o-mini');
  });

  it('still honours an explicitly passed model', () => {
    // Guards the `||` chain: the fallback must not win over a real config value.
    const agent = new Agent({ instructions: 'x', llm: 'gpt-4o' });
    expect((agent as any).llm).toBe('gpt-4o');
  });

  it('applies the documented verbose/pretty defaults', () => {
    // `verbose` defaults ON (`!== 'false'`), `pretty` defaults OFF
    // (`=== 'true'`). An undefined env must reproduce exactly that.
    const agent = new Agent({ instructions: 'x' });
    expect((agent as any).verbose).toBe(true);
    expect((agent as any).pretty).toBe(false);
  });
});

describe('Agent streaming in a runtime with no process global', () => {
  const saved = (globalThis as any).process;

  afterEach(() => {
    (globalThis as any).process = saved;
  });

  it('the default token sink does not throw when stdout is absent', () => {
    // start() with no onToken defaults to writing to stdout. On a webview that
    // deref threw on the FIRST token, so streaming died the moment it began --
    // after the constructor had already succeeded, which is why the constructor
    // test above does not cover it.
    const agent: any = new Agent({ instructions: 'x' });
    delete (globalThis as any).process;
    expect(() => writeTokenToStdout('hello')).not.toThrow();
    expect(agent.name).toBeDefined();
  });

  it('still writes to stdout when one is present', () => {
    // The pair: "never write" would pass the test above and silently break the CLI.
    const written: string[] = [];
    (globalThis as any).process = { ...saved, stdout: { write: (t: string) => written.push(t) } };
    writeTokenToStdout('hello');
    expect(written).toEqual(['hello']);
  });
});
