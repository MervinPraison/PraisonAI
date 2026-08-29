/**
 * What a screen reader is told while a turn streams, as a pure function.
 *
 * This is the single hardest decision in making a chat app usable without
 * sight, and both obvious answers are wrong:
 *
 *  - ANNOUNCE NOTHING. The app is silent for forty seconds while the model
 *    writes and three tools run. There is no way to tell "thinking" from
 *    "crashed" from "waiting for you to approve something", so the only
 *    available action is to wait, and then wait more. This is where the app is
 *    today: there is no live region anywhere in the package.
 *
 *  - ANNOUNCE EVERY UPDATE. Put `aria-live="polite"` on the transcript and the
 *    region mutates several times a second. VoiceOver and NVDA restart the
 *    utterance on each mutation, so the user hears "The", "The file", "The
 *    file con", "The file contains" -- forever, never reaching the end of a
 *    sentence. This is worse than silence, because it also blocks the reader
 *    from being used for anything else. It is the state most "we added ARIA"
 *    patches ship in, and it passes every automated accessibility checker.
 *
 * The policy here is COALESCE TO SENTENCE BOUNDARIES, RATE-LIMITED:
 *
 *   1. Only completed sentences are ever spoken. A half-typed clause is held
 *      back until it is finished (ui/src/i18n/segment.ts decides where that is,
 *      per locale -- "1.2" and "Dr." are not sentence ends, and Japanese ends
 *      with 。). This alone removes the stutter.
 *   2. At most one stream announcement per ANNOUNCE_INTERVAL_MS. A model
 *      emitting short sentences would otherwise still produce a new utterance
 *      every 300ms; the interval batches them into a paragraph, which is the
 *      unit a screen reader user actually wants to hear.
 *   3. A cursor into the text means nothing is ever spoken twice. Re-reading
 *      the whole answer on every update is the second-most-common bug here.
 *   4. ON END, THE TAIL IS FLUSHED. A model that finishes without terminal
 *      punctuation -- a bare list item, a code fence, a truncated answer --
 *      would otherwise have its last clause held back forever, and the user
 *      would never hear the end of the response. The rate limit is bypassed
 *      for the flush, because there is no later tick to catch it.
 *   5. REASONING IS NEVER ANNOUNCED. It is ancillary by construction and is
 *      often longer than the answer; speaking it means the answer arrives
 *      minutes late, if at all. It stays visible and navigable on screen.
 *   6. TOOL ARGUMENTS ARE NEVER ANNOUNCED. `args` is an arbitrary bag from the
 *      wire and can be a 4KB file body. Status and name are announced; the
 *      arguments stay readable in the row.
 *   7. An approval bypasses the rate limit entirely and is assertive -- the run
 *      is BLOCKED on it. See politeness.ts.
 *
 * Pure and total: state in, state out, no timers, no DOM, no scheduling. The
 * caller ticks it (on publish, and once more on turn end) and writes the
 * returned text into a live region. That is what makes every rule above
 * assertable by calling a function, which is the same bargain the rest of ui/
 * makes.
 */
import type { TurnState } from "../../../core/src/run/transcript.ts";
import { completedLength } from "../i18n/segment.ts";
import { formatElapsedLocalised } from "../i18n/format-intl.ts";
import type { Strings } from "../i18n/strings.ts";
import { politenessFor, priorityOf, type AnnounceReason, type Politeness } from "./politeness.ts";

/**
 * The floor between two stream announcements.
 *
 * A screen reader reads at roughly 180-300 words per minute, so a sentence
 * takes on the order of a second to speak. Announcing faster than it can talk
 * just grows a queue the user cannot interrupt.
 */
export const ANNOUNCE_INTERVAL_MS = 1200;

export interface Announcement {
  readonly reason: AnnounceReason;
  readonly politeness: Politeness;
  readonly text: string;
}

/**
 * What has already been said.
 *
 * `turnKey` is what makes a new turn start over. Without it, the character
 * cursor from the previous answer points into the middle of the new one and
 * the first half of every reply after the first is silently skipped.
 */
export interface AnnouncerState {
  readonly turnKey: string | null;
  /** How many code units of `turn.text` have been spoken. */
  readonly spokenChars: number;
  readonly lastStreamAtMs: number;
  /** `${callId}:${status}` for each transition already spoken. */
  readonly spokenTools: readonly string[];
  readonly spokenApprovals: readonly string[];
  readonly spokenOutcome: boolean;
  readonly spokenDropped: number;
}

export const initialAnnouncer: AnnouncerState = {
  turnKey: null,
  spokenChars: 0,
  lastStreamAtMs: Number.NEGATIVE_INFINITY,
  spokenTools: [],
  spokenApprovals: [],
  spokenOutcome: false,
  spokenDropped: 0,
};

export interface AnnounceInput {
  readonly turn: TurnState;
  readonly strings: Strings;
  /** Decides where sentences end and how durations read. */
  readonly locale: string;
  readonly nowMs: number;
}

export interface AnnounceResult {
  readonly state: AnnouncerState;
  /** Assertive first. See politeness.ts: an assertive utterance clears the
   *  polite queue, so anything polite has to be written after it. */
  readonly announcements: readonly Announcement[];
}

const NOTHING: readonly Announcement[] = [];

function say(reason: AnnounceReason, text: string): Announcement {
  return { reason, politeness: politenessFor(reason), text };
}

/** Identity of the turn being announced. A new run or a new message id is a
 *  new turn and resets everything. */
function turnKeyOf(turn: TurnState): string | null {
  if (turn.msgId === null) return null;
  return `${turn.runId ?? ""}:${turn.msgId}`;
}

export function announce(state: AnnouncerState, input: AnnounceInput): AnnounceResult {
  const { turn, strings, locale, nowMs } = input;
  const key = turnKeyOf(turn);
  // A different turn: forget the cursor rather than indexing into the new text
  // with the old one.
  const base: AnnouncerState =
    state.turnKey === key ? state : { ...initialAnnouncer, turnKey: key };

  const out: Announcement[] = [];
  let spokenChars = base.spokenChars;
  let lastStreamAtMs = base.lastStreamAtMs;
  let spokenTools = base.spokenTools;
  let spokenApprovals = base.spokenApprovals;
  let spokenOutcome = base.spokenOutcome;
  let spokenDropped = base.spokenDropped;

  // ---- approvals. First, unconditional, assertive. The run is stopped. -----
  const alreadyAsked = new Set(spokenApprovals);
  const newApprovals = turn.approvals.filter((pending) => !alreadyAsked.has(pending.approvalId));
  if (newApprovals.length > 0) {
    for (const pending of newApprovals) {
      // The tool NAME, never the args: see rule 6. "Allow bash?" is actionable;
      // four kilobytes of shell script read aloud is not.
      out.push(say("approval", strings.announceApproval(pending.name)));
    }
    spokenApprovals = [...spokenApprovals, ...newApprovals.map((p) => p.approvalId)];
  }

  // ---- the answer itself --------------------------------------------------
  const text = turn.text;
  const ended = turn.outcome !== null || turn.phase === "ended";
  if (spokenChars > text.length) spokenChars = 0; // defensive; turnKey normally covers it

  if (ended) {
    // Rule 4: flush. No rate limit and no sentence requirement -- there is no
    // later tick, so anything held back now is lost for good.
    const tail = text.slice(spokenChars);
    if (tail.trim() !== "") out.push(say("stream", tail.trim()));
    spokenChars = text.length;
  } else if (nowMs - lastStreamAtMs >= ANNOUNCE_INTERVAL_MS) {
    // Rules 1 and 2. `completedLength` is the end of the last FINISHED
    // sentence; everything after it is a fragment and waits.
    //
    // The clock advances because the CHECK ran, not because it produced
    // speech. `completedLength` segments the whole accumulated answer, and it
    // used to advance only inside `if (chunk !== "")` -- so any stretch in
    // which no sentence completes left the rate limit permanently open and
    // re-segmented everything on every publish. A markdown table, a code
    // block, a JSON dump or a bulleted list is enough. Measured at the real
    // publish cadence: 4.1 / 11.8 / 43.5 / 175.2 ms for 20 / 40 / 80 / 160 kB
    // of unterminated text -- 4.03x per doubling, quadratic, and roughly
    // 700 ms of blocked main thread on a phone for one long answer.
    //
    // The cost of moving it: a sentence that completes just after a check
    // waits up to ANNOUNCE_INTERVAL_MS to be spoken. That is what the rate
    // limit is for, and a screen-reader user is not served by re-segmenting
    // 160 kB six hundred times to discover nothing new. When speech IS
    // flowing, behaviour is identical -- the clock advanced on every chunk
    // anyway.
    lastStreamAtMs = nowMs;
    const complete = completedLength(locale, text);
    if (complete > spokenChars) {
      const chunk = text.slice(spokenChars, complete).trim();
      if (chunk !== "") out.push(say("stream", chunk));
      spokenChars = complete;
    }
  }
  // turn.reasoning is read by nothing above, on purpose. Rule 5.

  // ---- tools --------------------------------------------------------------
  const spokenToolSet = new Set(spokenTools);
  const newTools: string[] = [];
  for (const tool of turn.tools) {
    const marker = `${tool.callId}:${tool.status}`;
    if (spokenToolSet.has(marker)) continue;
    newTools.push(marker);
    if (tool.status === "running") {
      out.push(say("tool", strings.announceToolStarted(tool.name)));
      continue;
    }
    // `seconds: null` means the engine never saw the call begin. Passed through
    // as null so the string table can speak it as words -- "—" is read as
    // silence, which sounds identical to a duration that is simply missing.
    const duration =
      tool.seconds === null ? null : formatElapsedLocalised(locale, strings, tool.seconds);
    out.push(say("tool", strings.announceToolFinished(tool.status, tool.name, duration)));
  }
  if (newTools.length > 0) spokenTools = [...spokenTools, ...newTools];

  // ---- how the turn came out ----------------------------------------------
  const outcome = turn.outcome;
  if (outcome !== null && !spokenOutcome) {
    spokenOutcome = true;
    if (outcome.type === "error") {
      out.push(say("error", strings.announceError(outcome.kind, outcome.message)));
    } else if (outcome.type === "cancelled") {
      out.push(say("outcome", strings.announceStopped));
    } else {
      out.push(say("outcome", strings.announceTurnComplete));
    }
  }

  // ---- refused events -----------------------------------------------------
  // Only at the end. transcript.ts keeps these because "an ignore with no
  // record is indistinguishable from a quiet success", and that is just as true
  // for a user who cannot see the row -- but interrupting the answer to report
  // a decoder gap is not worth it, so it waits for the turn to finish.
  if (ended && turn.dropped.length > spokenDropped) {
    out.push(say("dropped", strings.announceDropped(turn.dropped.length)));
    spokenDropped = turn.dropped.length;
  }

  // Return the SAME object only when nothing at all moved. `out.length === 0`
  // is not that test: this function advances two cursors without necessarily
  // producing speech -- `lastStreamAtMs` when the sentence check runs, and
  // `spokenChars` when the completed prefix trims to nothing -- and returning
  // `state` threw both away. The caller then re-ran the check on the very next
  // publish, and `completedLength` re-segmented the whole accumulated answer
  // every time: 533 full segmentations over 607 publishes of a 160 kB answer,
  // measured, and quadratic in the length of it.
  const unchanged =
    out.length === 0 &&
    base === state &&
    spokenChars === state.spokenChars &&
    lastStreamAtMs === state.lastStreamAtMs &&
    spokenTools === state.spokenTools &&
    spokenApprovals === state.spokenApprovals &&
    spokenOutcome === state.spokenOutcome &&
    spokenDropped === state.spokenDropped;
  if (unchanged) return { state, announcements: NOTHING };

  // Stable sort by priority: assertive first, original order preserved within
  // each band so the answer's own sentences stay in the order they were written.
  const announcements = out
    .map((announcement, index) => ({ announcement, index }))
    .sort((a, b) =>
      priorityOf(a.announcement.reason) - priorityOf(b.announcement.reason) || a.index - b.index)
    .map((entry) => entry.announcement);

  return {
    state: {
      turnKey: key,
      spokenChars,
      lastStreamAtMs,
      spokenTools,
      spokenApprovals,
      spokenOutcome,
      spokenDropped,
    },
    announcements,
  };
}

/** Explicit reset, for a caller that would rather say so than rely on the
 *  turn-key comparison -- e.g. when the user opens a different chat. */
export function resetAnnouncer(): AnnouncerState {
  return initialAnnouncer;
}
