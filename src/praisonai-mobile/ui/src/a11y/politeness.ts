/**
 * How urgently a screen reader should be told something.
 *
 * ARIA gives exactly two useful settings and the difference between them is not
 * a matter of taste:
 *
 *   polite    -- queued. Spoken after whatever is being read finishes.
 *   assertive -- interrupts. Clears the queue and speaks now.
 *
 * The failure this file prevents is picking `polite` for an approval prompt.
 * An agent that wants to run `rm -rf build` BLOCKS: the run is stopped, waiting
 * for an answer, and core/src/run/approvals.ts notes the engine gives up after
 * 300 seconds. Meanwhile the model has streamed four paragraphs into a polite
 * live region, and a polite announcement queues BEHIND all of it. A blind user
 * is told about the prompt after it has already timed out -- or, in a screen
 * reader that coalesces polite updates, is never told at all, because a newer
 * polite update replaced it. The run just silently stalls. Sighted users see
 * the buttons appear and nobody ever reproduces the bug.
 *
 * The inverse failure is real too, which is why this is a mapping and not
 * "assertive for everything": marking streamed text assertive makes every token
 * batch interrupt the previous one, so the reader restarts mid-word forever and
 * the user cannot hear a single complete sentence. That is the state most
 * "we added aria-live" patches ship in.
 *
 * The rule, then: assertive is reserved for the two things that BLOCK or BREAK
 * -- an approval request and an error. Everything else waits its turn.
 */

export type Politeness = "polite" | "assertive";

/**
 * Why something is being announced.
 *
 * Politeness is chosen from this and never from the text, for the same reason
 * ui/src/transcript/view-model.ts chooses a recovery from `kind` and never from
 * a message: the text is prose from a model or a provider, and matching on it
 * makes the behaviour depend on wording that changes without notice.
 */
export type AnnounceReason =
  /** A chunk of the model's answer. */
  | "stream"
  /** A tool started or finished. */
  | "tool"
  /** The turn ended, was stopped, or completed. */
  | "outcome"
  /** Events the decoder refused. */
  | "dropped"
  /** The screen changed. */
  | "screen"
  /** The turn failed. */
  | "error"
  /** The run is BLOCKED until the user answers. */
  | "approval";

const ASSERTIVE: ReadonlySet<AnnounceReason> = new Set<AnnounceReason>(["approval", "error"]);

export function politenessFor(reason: AnnounceReason): Politeness {
  return ASSERTIVE.has(reason) ? "assertive" : "polite";
}

/**
 * The ARIA role that goes with a live region of this politeness.
 *
 * `role="status"` implies aria-live="polite" and `role="alert"` implies
 * assertive. Both are given explicitly by a renderer, because a handful of
 * older screen readers honour one attribute and not the other, and a region
 * that is announced by nobody is indistinguishable from one that works.
 */
export type LiveRole = "status" | "alert";

export function roleFor(politeness: Politeness): LiveRole {
  return politeness === "assertive" ? "alert" : "status";
}

/**
 * Which of two announcements should be spoken first.
 *
 * Assertive first, always. A screen reader that honours `assertive` discards
 * the pending polite queue when it fires, so emitting the polite items AFTER
 * the interrupting one is the only order under which they survive to be heard.
 * Emitting them first means writing text into a region that is about to be
 * cleared.
 */
export function priorityOf(reason: AnnounceReason): number {
  return politenessFor(reason) === "assertive" ? 0 : 1;
}
