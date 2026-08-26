/**
 * The protocol version, and the gate that decides whether an engine may be
 * spoken to at all.
 *
 * Modelled on src-tauri/src/health.rs:11, which records why this is a distinct
 * failure from a transport failure: "a transport error may be the engine still
 * binding its socket, whereas a version mismatch will never fix itself." One is
 * worth retrying and the other is not, so they must not share a code path -- a
 * retry loop against a permanent refusal just burns a phone battery.
 *
 * The gate never throws. It returns a verdict and the caller decides. Throwing
 * here would put the decision inside whichever `try` block happened to enclose
 * the call, which is not where it belongs.
 */

/**
 * What this client speaks. 2 matches engine/server.py's PROTOCOL_VERSION, so
 * the remote-http engine can talk to a desktop install unmodified.
 */
export const PROTOCOL_VERSION = 2;

/** The oldest engine we will talk to at all. */
export const MIN_ENGINE_PROTOCOL = 2;

/**
 * Capabilities that arrived after MIN_ENGINE_PROTOCOL.
 *
 * An older engine then degrades *visibly* -- the client reads this list and
 * turns the feature off -- rather than appearing to support something and
 * failing at the moment a user relies on it.
 */
export const FEATURES: readonly { readonly name: string; readonly since: number }[] = [
  // Empty today, and that is the correct state rather than an oversight.
  //
  // INVARIANT: no entry may have `since` greater than PROTOCOL_VERSION. A
  // client cannot sensibly report a capability as "degraded on this engine"
  // when the client does not implement it either -- that reads to the UI as an
  // engine problem when it is our own gap. Add the entry in the same change
  // that raises PROTOCOL_VERSION, never before. version.test.ts holds this.
  //
  // The first entry will be resume_after_background, at v3, once the wire
  // carries a per-event sequence number.
];

export type Compatibility =
  | { readonly ok: true; readonly engine: number; readonly degraded: readonly string[] }
  | {
      readonly ok: false;
      readonly reason: "too_old" | "unreadable";
      readonly engine: number | null;
      readonly expected: number;
    };

/**
 * `engine` is whatever the engine reported about itself, deliberately typed
 * `unknown`: the entire point is that it has not been trusted yet.
 *
 * An engine NEWER than this client is accepted. Forward compatibility is
 * structural rather than promised -- decode.ts ignores unknown event names and
 * unknown fields, so a newer engine can only add things this client skips.
 * Refusing it would strand every shipped client on the day the engine ships
 * first, which is the normal order of events.
 */
export function checkProtocol(engine: unknown): Compatibility {
  if (typeof engine !== "number" || !Number.isInteger(engine) || engine < 1) {
    // Not "assume v2". health.rs:66 -- a missing field must never be mistaken
    // for a present one, and an engine that cannot state what it speaks is not
    // one that can be held to a contract.
    return { ok: false, reason: "unreadable", engine: null, expected: PROTOCOL_VERSION };
  }
  if (engine < MIN_ENGINE_PROTOCOL) {
    return { ok: false, reason: "too_old", engine, expected: PROTOCOL_VERSION };
  }
  const degraded = FEATURES.filter((f) => engine < f.since).map((f) => f.name);
  return { ok: true, engine, degraded };
}
