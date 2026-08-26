/**
 * Is the engine on the other end actually ready to be talked to?
 *
 * A TypeScript port of praisonai-desktop/src-tauri/src/health.rs, which exists
 * because of one non-obvious rule stated in its own header:
 *
 *   the engine answers failures with HTTP 200 and a body of {"ok": false},
 *   so a status code alone is NOT readiness.
 *
 * A client that treats 200 as ready routes a user's chat into a broken engine
 * and then reports the resulting nonsense as a model failure. That is why this
 * is a named function with a verdict type rather than an `if (res.ok)`.
 *
 * The second rule is that the failures are NOT interchangeable. health.rs:11:
 * "a transport error may be the engine still binding its socket, whereas a
 * version mismatch will never fix itself." One is worth retrying and the other
 * is not, so they cannot share a branch.
 */
import { checkProtocol, type Compatibility } from "../../../protocol/src/version.ts";

/** What a probe observed. Deliberately a value, not an exception -- a caller
 *  should not have to distinguish "engine said no" from "fetch threw". */
export type Probe =
  | { readonly kind: "transport"; readonly detail: string }
  | { readonly kind: "http"; readonly status: number; readonly body: string };

export type Readiness =
  | { readonly ready: true; readonly protocol: number; readonly degraded: readonly string[] }
  | {
      readonly ready: false;
      readonly reason:
        | "transport" // could not reach it at all -- retry is meaningful
        | "http_status" // reached it, wrong status
        | "malformed" // reached it, body was not the shape we expect
        | "unhealthy" // reached it, it said ok:false
        | "version_mismatch"; // reached it, we cannot speak to it -- never retry
      readonly detail: string;
      readonly retryable: boolean;
    };

const notReady = (
  reason: Extract<Readiness, { ready: false }>["reason"],
  detail: string,
  retryable: boolean,
): Readiness => ({ ready: false, reason, detail, retryable });

/**
 * Classify a probe. Pure -- no I/O, so the whole table below is testable
 * without a server.
 */
export function classify(probe: Probe): Readiness {
  if (probe.kind === "transport") {
    // The engine may simply still be binding its socket. Worth retrying.
    return notReady("transport", probe.detail, true);
  }

  if (probe.status !== 200) {
    return notReady("http_status", String(probe.status), true);
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(probe.body);
  } catch {
    // Reached something that is not our engine -- a captive portal, a proxy
    // error page, a different service on the port. Retrying is reasonable.
    return notReady("malformed", probe.body.slice(0, 120), true);
  }

  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    return notReady("malformed", typeof parsed, true);
  }

  const body = parsed as Record<string, unknown>;

  // THE RULE. A 200 with ok:false is the engine telling us it is not ready.
  // Reading the status code alone routes a chat into a broken engine.
  if (body["ok"] !== true) {
    return notReady("unhealthy", JSON.stringify(body["ok"] ?? null), true);
  }

  const compat: Compatibility = checkProtocol(body["version"]);
  if (!compat.ok) {
    // Never retryable. A version mismatch does not resolve itself, and a retry
    // loop against a permanent refusal just drains a phone battery.
    return notReady(
      "version_mismatch",
      `${compat.reason}: engine=${compat.engine ?? "unreadable"} expected=${compat.expected}`,
      false,
    );
  }

  return { ready: true, protocol: compat.engine, degraded: compat.degraded };
}
