/**
 * A UUID that works everywhere praisonai-ts runs.
 *
 * `import { randomUUID } from 'crypto'` is a STATIC Node builtin import: in a
 * browser or webview the bundle dies at module load, before any code runs,
 * with no error boundary and a blank screen. That was issue #4437, and PR
 * #4438 fixed it for the two files on the Agent import graph -- leaving the
 * same import in 32 others, each of which re-breaks the moment anything
 * reachable from a webview touches it.
 *
 * `globalThis.crypto.randomUUID` is a straight substitution rather than a
 * polyfill: it exists in every supported webview and in Node >= 19. The
 * fallbacks below exist for older runtimes and are ordered by how much
 * entropy they can offer.
 *
 * The version and variant nibbles are set BY HAND in the fallback, which is
 * the part worth reading twice: getting the masks wrong yields a string that
 * looks like a UUID and is not one, and anything validating it rejects the id
 * far away from here.
 */

/** RFC 4122 version 4. */
export function randomUUID(): string {
  const c = globalThis.crypto;
  if (c?.randomUUID) {
    return c.randomUUID();
  }

  const bytes = new Uint8Array(16);
  if (c?.getRandomValues) {
    c.getRandomValues(bytes);
  } else {
    // The last resort, for a runtime with no WebCrypto at all. Math.random is
    // not a CSPRNG and these ids must not be used as secrets -- they are run
    // and message identifiers, where collision resistance is what matters.
    for (let i = 0; i < 16; i++) bytes[i] = Math.floor(Math.random() * 256);
  }

  // Version 4: clear the high nibble THEN set it. `| 0x40` alone leaves an
  // all-ones byte reading as version f.
  bytes[6] = (bytes[6]! & 0x0f) | 0x40;
  // Variant 10xx: same reasoning on the two high bits.
  bytes[8] = (bytes[8]! & 0x3f) | 0x80;

  // padStart is load-bearing: toString(16) on a byte below 0x10 yields one
  // character, and the whole string then comes out short with the dashes in
  // the wrong places.
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0'));
  return (
    hex[0]! + hex[1]! + hex[2]! + hex[3]! + '-' +
    hex[4]! + hex[5]! + '-' +
    hex[6]! + hex[7]! + '-' +
    hex[8]! + hex[9]! + '-' +
    hex[10]! + hex[11]! + hex[12]! + hex[13]! + hex[14]! + hex[15]!
  );
}
