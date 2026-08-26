/**
 * The randomUUID fallback, which CI can never reach on its own.
 *
 * `globalThis.crypto.randomUUID` exists in every environment these tests run
 * in, so the fallback path is dead code as far as a normal run is concerned --
 * it would stay green no matter how broken it was. It is also the path that
 * actually matters: it exists for older webviews, which is precisely where
 * nobody is watching the console.
 *
 * `randomUUID` is not exported, so these drive it through `Agent`, whose
 * `runId` is produced by it.
 */
import { Agent } from '../../../src/agent/simple';

/** RFC 4122: 8-4-4-4-12 hex, version nibble 4, variant nibble 8|9|a|b. */
const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

const runIdOf = (agent: Agent): string => agent.getRunId();

describe('randomUUID fallback', () => {
  const realCrypto = globalThis.crypto;

  afterEach(() => {
    Object.defineProperty(globalThis, 'crypto', {
      value: realCrypto, configurable: true, writable: true,
    });
  });

  /** Replace the global crypto with a partial one. */
  const withCrypto = (value: unknown) => {
    Object.defineProperty(globalThis, 'crypto', {
      value, configurable: true, writable: true,
    });
  };

  it('uses native randomUUID when it is available', () => {
    // The pair. Without it, a fallback that always ran would pass every other
    // case here while silently discarding the platform's CSPRNG.
    let used = false;
    withCrypto({
      randomUUID: () => { used = true; return '11111111-2222-4333-8444-555555555555'; },
      getRandomValues: realCrypto.getRandomValues.bind(realCrypto),
    });
    const id = runIdOf(new Agent({ instructions: 'x' }));
    expect(used).toBe(true);
    expect(id).toBe('11111111-2222-4333-8444-555555555555');
  });

  it('falls back to getRandomValues and still produces a valid v4 UUID', () => {
    // The version and variant nibbles are SET by hand in the fallback. Getting
    // that bit-twiddling wrong yields a string that looks like a UUID and is
    // not one -- which anything validating it will reject, far from here.
    withCrypto({ getRandomValues: realCrypto.getRandomValues.bind(realCrypto) });
    expect(runIdOf(new Agent({ instructions: 'x' }))).toMatch(UUID_V4);
  });

  it('falls back again when there is no crypto global at all', () => {
    // The oldest webviews. Math.random is a weak source, but a weak id beats
    // a ReferenceError at construction.
    withCrypto(undefined);
    expect(runIdOf(new Agent({ instructions: 'x' }))).toMatch(UUID_V4);
  });

  it('sets the version nibble to 4 even when every random byte is 0xff', () => {
    // Masking, not assignment: `| 0x40` without clearing the high nibble first
    // leaves it as f. An all-ones source is the input that exposes it.
    withCrypto({ getRandomValues: (a: Uint8Array) => a.fill(0xff) });
    const id = runIdOf(new Agent({ instructions: 'x' }));
    expect(id[14]).toBe('4');
    expect(['8', '9', 'a', 'b']).toContain(id[19]);
    expect(id).toMatch(UUID_V4);
  });

  it('sets the variant nibble correctly when every random byte is 0x00', () => {
    // The other extreme, which catches a mask that clears too much.
    withCrypto({ getRandomValues: (a: Uint8Array) => a.fill(0x00) });
    const id = runIdOf(new Agent({ instructions: 'x' }));
    expect(id[14]).toBe('4');
    expect(id[19]).toBe('8');
    expect(id).toMatch(UUID_V4);
  });

  it('produces a different id each time', () => {
    withCrypto({ getRandomValues: realCrypto.getRandomValues.bind(realCrypto) });
    const ids = new Set(
      Array.from({ length: 50 }, () => runIdOf(new Agent({ instructions: 'x' }))),
    );
    expect(ids.size).toBe(50);
  });

  it('pads a byte below 0x10 to two hex digits', () => {
    // `toString(16)` on 0x05 gives "5". Without padStart the whole string is
    // short and the dashes land in the wrong places.
    withCrypto({ getRandomValues: (a: Uint8Array) => a.fill(0x05) });
    expect(runIdOf(new Agent({ instructions: 'x' }))).toMatch(UUID_V4);
  });
});
