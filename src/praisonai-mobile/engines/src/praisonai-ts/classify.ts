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
  // A key that was never SET, which is a different sentence from a key that was
  // rejected and was reaching none of the patterns above.
  //
  // This is the single most likely failure the app has -- it is what a fresh
  // install does on its very first message -- and it was classified `internal`,
  // whose recovery is `none`. So the one error whose entire answer is "open
  // Settings and paste a key" offered no route to settings at all, while the
  // docstring at the top of this file describes exactly that outcome as the
  // thing the function exists to prevent.
  //
  // The message it misses is not hypothetical: `The OPENAI_API_KEY environment
  // variable is missing or empty` is quoted verbatim in
  // ui/src/transcript/empty-state.ts as the prose a user was left to read, and
  // none of `unauthor`, `forbidden`, `authentication`, `no api key` or
  // `api key not` appears anywhere in it.
  //
  // Bounded by `[^.;]` rather than `.`: the same sentence goes on, after a
  // semicolon, to suggest `instantiate the OpenAI client with an apiKey
  // option`, and a greedy gap would let any later "missing" in an unrelated
  // clause pull an unrelated failure into `auth`.
  if (
    /(?:[a-z0-9]+_)?api[_ -]?key\b[^.;]{0,80}\b(?:missing|not set|unset|empty|required|not provided)\b/.test(text) ||
    /\b(?:missing|no|empty)\b[^.;]{0,40}\bapi[_ -]?key\b/.test(text) ||
    /\bmissing credentials?\b/.test(text)
  ) {
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
