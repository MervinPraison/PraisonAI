/**
 * The shared UUID util.
 *
 * `Agent`'s own tests cover the fallback through `getRunId()`, which is the
 * important end-to-end path. This covers the util directly, because 32 other
 * modules now depend on it and none of them go through an Agent -- so a break
 * here would surface as a failure somewhere with no obvious connection to ids.
 *
 * The fallback is unreachable in a normal run: `globalThis.crypto.randomUUID`
 * exists in every environment these tests execute in, so it would stay green
 * however broken it was. Each case forces it.
 */
import { randomUUID } from '../../../src/utils/uuid';

/** RFC 4122: 8-4-4-4-12 hex, version nibble 4, variant nibble 8|9|a|b. */
const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

describe('randomUUID', () => {
  const real = globalThis.crypto;
  const withCrypto = (value: unknown) => {
    Object.defineProperty(globalThis, 'crypto', { value, configurable: true, writable: true });
  };
  afterEach(() => withCrypto(real));

  it('uses the platform generator when there is one', () => {
    // The pair for every fallback case below: a util that always fell back
    // would pass them all while discarding the platform's CSPRNG.
    let used = false;
    withCrypto({ randomUUID: () => { used = true; return '11111111-2222-4333-8444-555555555555'; } });
    expect(randomUUID()).toBe('11111111-2222-4333-8444-555555555555');
    expect(used).toBe(true);
  });

  it('falls back to getRandomValues and still produces a valid v4', () => {
    withCrypto({ getRandomValues: real.getRandomValues.bind(real) });
    expect(randomUUID()).toMatch(UUID_V4);
  });

  it('works with no crypto global at all', () => {
    // The oldest webviews. A weak id beats a ReferenceError at module load.
    withCrypto(undefined);
    expect(randomUUID()).toMatch(UUID_V4);
  });

  it('sets the version nibble when every random byte is 0xff', () => {
    // Masking, not assignment: `| 0x40` without clearing the high nibble first
    // leaves an all-ones byte reading as version f. This input exposes it.
    withCrypto({ getRandomValues: (a: Uint8Array) => a.fill(0xff) });
    const id = randomUUID();
    expect(id[14]).toBe('4');
    expect(['8', '9', 'a', 'b']).toContain(id[19]);
    expect(id).toMatch(UUID_V4);
  });

  it('sets the variant nibble when every random byte is 0x00', () => {
    // The other extreme, which catches a mask that clears too much.
    withCrypto({ getRandomValues: (a: Uint8Array) => a.fill(0x00) });
    const id = randomUUID();
    expect(id[14]).toBe('4');
    expect(id[19]).toBe('8');
    expect(id).toMatch(UUID_V4);
  });

  it('pads a byte below 0x10 to two hex digits', () => {
    // toString(16) on 0x05 gives "5"; without padStart the string comes out
    // short and every dash lands in the wrong place.
    withCrypto({ getRandomValues: (a: Uint8Array) => a.fill(0x05) });
    expect(randomUUID()).toMatch(UUID_V4);
  });

  it('does not repeat', () => {
    withCrypto({ getRandomValues: real.getRandomValues.bind(real) });
    const ids = new Set(Array.from({ length: 200 }, () => randomUUID()));
    expect(ids.size).toBe(200);
  });
});
