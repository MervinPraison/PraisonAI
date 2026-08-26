/**
 * Turning a provider `Error` into an `ErrorKind`.
 *
 * `kind` selects the recovery the UI offers, so this is not cosmetic: an auth
 * failure classified as `internal` sends the user to "try again" instead of to
 * the settings screen, and they retry a key that will never work.
 *
 * praisonai-ts surfaces provider failures as a plain `Error` with the provider's
 * message -- there is no structured code to switch on -- so this reads the
 * status code and the text. That is inherently approximate, which is why the
 * default is `internal` rather than a guess: an unrecognised failure that says
 * "something went wrong" is honest, while one mislabelled `rate_limit` tells
 * the user to wait for a condition that will never clear.
 *
 * Order matters. 401/403 is checked before the word "quota", because a
 * provider that returns 403 for an exhausted key mentions both.
 */
import type { ErrorKind } from "../../../protocol/src/events.ts";

/** Read an HTTP status off the shapes providers actually throw. */
export function statusOf(error: unknown): number | null {
  if (error === null || typeof error !== "object") return null;
  const candidate = error as { status?: unknown; statusCode?: unknown; response?: { status?: unknown } };
  for (const value of [candidate.status, candidate.statusCode, candidate.response?.status]) {
    if (typeof value === "number" && Number.isFinite(value)) return value;
  }
  return null;
}

export function classifyError(error: unknown): ErrorKind {
  const status = statusOf(error);
  if (status === 401 || status === 403) return "auth";
  if (status === 429) return "rate_limit";

  const text = (error instanceof Error ? error.message : String(error ?? "")).toLowerCase();

  // Auth first -- see the ordering note above.
  // No trailing \b on the word forms: Anthropic sends `authentication_error`,
  // and `_` is a word character, so `\bauthentication\b` does not match it --
  // which sent a bad key to "try again" instead of to the settings screen.
  if (/\b(401|403)\b/.test(text) || /(unauthor|forbidden|authentication|invalid[ _-]?x?-?api[ _-]?key|incorrect api key|no api key|api key not)/.test(text)) {
    return "auth";
  }
  if (/\b(429|rate.?limit|too many requests|quota|overloaded|capacity)\b/.test(text)) {
    return "rate_limit";
  }
  // A dropped stream. The engine itself may be fine, so the offered recovery
  // is "retry", which is different from both of the above.
  if (/\b(econnreset|etimedout|enotfound|econnrefused|socket hang up|network|fetch failed|aborted|timeout)\b/.test(text)) {
    return "transport";
  }
  if (status !== null && status >= 500) return "transport";

  return "internal";
}
