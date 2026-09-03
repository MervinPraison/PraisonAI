/**
 * Applying a diff to real nodes. The thin half, deliberately.
 *
 * Every decision -- what changed, what moved, what a row should say -- happens
 * above this file, in `ui/`, where it is testable without a DOM. What is left
 * here is node creation and placement, and it is kept dull on purpose: this is
 * the only code in the package that a unit test cannot easily reach, so the
 * less judgement it carries the better.
 *
 * Text is set through `textContent`, never `innerHTML`. Model output, tool
 * results and error messages all flow through here, and every one of them is
 * attacker-influenced in the ordinary case -- a web page the model summarised
 * can contain markup. `textContent` makes that structurally impossible rather
 * than depending on an escaping function nobody re-reads.
 */
import type { Op } from "../../ui/src/render/reconcile.ts";
import type { Row } from "../../ui/src/transcript/view-model.ts";
import { en, type Strings } from "../../ui/src/i18n/strings.ts";
import { accessibleName, userRowNames } from "../../ui/src/a11y/names.ts";
import { UNKNOWN } from "../../ui/src/format.ts";

export interface RowNodes {
  /** id -> the element currently representing that row. */
  readonly nodes: Map<string, HTMLElement>;
}

export const emptyNodes = (): RowNodes => ({ nodes: new Map() });

function build(doc: Document, row: Row, strings: Strings): HTMLElement {
  const el = doc.createElement("div");
  el.className = `row row-${row.kind}`;
  el.dataset["rowId"] = row.id;
  paint(el, row, strings);
  return el;
}

/**
 * Write a row's content into its element. Called on insert and on update.
 *
 * The `aria-label` comes FIRST, and it is repainted on every update rather
 * than only on insert: a tool row's name carries its status, and a row that
 * goes from `running` to `failed` in place would otherwise keep announcing
 * itself as running for the rest of the conversation.
 *
 * `ui/src/a11y/names.ts` existed, was tested eleven ways, and had no caller
 * anywhere in the application -- so every transcript row was announced by its
 * text content alone. A tool row read as "search, 1.2s" with no word for
 * whether it SUCCEEDED (the status reached the DOM only as `data-status`,
 * which app.css turns into a border colour and a screen reader cannot see at
 * all); an approval row mid-decision read as its question plus three buttons
 * that are disabled while the answer is in flight, and a disabled button is
 * announced as "dimmed" or skipped entirely, so the row went silent at the
 * exact moment the user was waiting to hear what happened; an error row read
 * as bare provider prose with no `errorTitle` in front of it.
 *
 * `null` is a real answer and not a gap -- a text row's own words ARE its
 * name, and labelling it would replace the answer with a summary of it -- so
 * null REMOVES the attribute rather than writing "null" or an empty string. A
 * row that changes kind in place must not keep a stale label.
 */
function paint(el: HTMLElement, row: Row, strings: Strings): void {
  const name = accessibleName(strings, row);
  if (name === null) el.removeAttribute("aria-label");
  else el.setAttribute("aria-label", name);

  switch (row.kind) {
    case "user": {
      // Three independent signals, only one of which is a colour: the row hugs
      // the opposite edge (app.css), it carries `data-speaker="user"`, and it
      // opens with a visually-hidden "You said:". A conversation whose two
      // sides are told apart by background colour alone is one a screen-reader
      // user hears as a single voice -- the defect a11y/names.ts exists for,
      // with alignment standing in for hue.
      el.dataset["speaker"] = "user";
      el.dataset["state"] = row.state;
      el.textContent = "";
      const names = userRowNames(strings, row);
      const speaker = el.ownerDocument.createElement("span");
      // Content, NOT an aria-label. See a11y/names.ts: labelling the row would
      // replace the message in the accessibility tree and cost the reader the
      // ability to navigate their own words.
      speaker.className = "sr-only";
      speaker.textContent = names.speaker;
      const said = el.ownerDocument.createElement("span");
      said.className = "user-text";
      said.textContent = row.text;
      el.append(speaker, said);
      if (names.note !== null) {
        // Sent, and not on disk. Said in words and shown as an element, so it
        // survives both a screen reader and a colour-blind glance.
        const note = el.ownerDocument.createElement("span");
        note.className = "user-note";
        note.textContent = names.note;
        el.append(note);
      }
      return;
    }
    case "text":
      el.textContent = row.text;
      el.classList.toggle("streaming", row.streaming);
      return;
    case "reasoning":
      el.textContent = row.text;
      return;
    case "notice":
      el.textContent = row.text;
      el.dataset["tone"] = row.tone;
      return;
    case "error":
      el.textContent = row.message;
      el.dataset["tone"] = row.tone;
      el.dataset["recovery"] = row.recovery;
      return;
    case "dropped":
      // Was a hand-rolled `event`/`events`, which is wrong in most languages --
      // Polish has three plural categories, Welsh six, Arabic a `zero`. The
      // table routes it through Intl.PluralRules.
      el.textContent = strings.droppedEvents(row.count, row.reasons);
      return;
    case "tool": {
      el.dataset["status"] = row.status;
      el.textContent = "";
      // The status IN WORDS, not only as `data-status`.
      //
      // app.css styles `[data-status="failed"]` and `[data-status="ok"]` with a
      // border colour and nothing else, so the status was carried by colour
      // alone -- and it had no rule at all for `unresolved`, which therefore
      // rendered pixel-for-pixel identically to a tool still running. "A tool
      // that never came back must not read like one that worked" is the defect
      // the whole transcript layer is written against (view-model.ts:173), and
      // `strings.toolStatus` was written for exactly this and had no caller.
      const status = el.ownerDocument.createElement("span");
      status.className = "tool-status";
      status.textContent = strings.toolStatus(row.status);
      const name = el.ownerDocument.createElement("span");
      name.className = "tool-name";
      name.textContent = row.name;
      const meta = el.ownerDocument.createElement("span");
      meta.className = "tool-meta";
      // durationKnown is separate from the label: `seconds: null` means the
      // engine never observed the call begin, which is not zero.
      meta.textContent = row.durationKnown ? row.durationLabel : UNKNOWN;
      el.append(status, name, meta);
      if (row.preview !== "") {
        const out = el.ownerDocument.createElement("pre");
        out.className = "tool-output";
        out.textContent = row.preview;
        el.append(out);
      }
      return;
    }
    case "approval": {
      el.dataset["state"] = row.state.status;
      el.textContent = "";
      const q = el.ownerDocument.createElement("p");
      q.textContent = strings.approvalQuestion(row.name);
      el.append(q);
      for (const choice of ["allow", "always", "deny"] as const) {
        const b = el.ownerDocument.createElement("button");
        b.type = "button";
        b.textContent = strings.approvalChoice(choice);
        // The id that goes back on the wire is the approvalId, never the
        // callId -- binding by row position silently authorises the wrong
        // command as soon as two approvals are outstanding.
        b.dataset["approvalId"] = row.approvalId;
        b.dataset["choice"] = choice;
        // `actionable` is false while a decision is in flight, so a double
        // tap cannot send two -- which is how the same command gets approved
        // twice.
        b.disabled = !row.actionable;
        el.append(b);
      }
      return;
    }
  }
}

export function applyOps(
  host: HTMLElement,
  state: RowNodes,
  ops: readonly Op[],
  strings: Strings = en,
): void {
  const doc = host.ownerDocument;
  for (const op of ops) {
    switch (op.kind) {
      case "remove": {
        state.nodes.get(op.id)?.remove();
        state.nodes.delete(op.id);
        break;
      }
      case "insert": {
        const el = build(doc, op.row, strings);
        state.nodes.set(op.id, el);
        // `children[index]` is the node currently at that position; inserting
        // before it puts the new row exactly there. Undefined means append.
        host.insertBefore(el, host.children[op.index] ?? null);
        break;
      }
      case "update": {
        const el = state.nodes.get(op.id);
        if (el !== undefined) paint(el, op.row, strings);
        break;
      }
      case "move": {
        const el = state.nodes.get(op.id);
        if (el === undefined) break;
        // `children[op.index]` is read BEFORE insertBefore detaches the node,
        // so it names a real sibling and the placement is relative to that
        // node, not to an index that shifts underneath it.
        host.insertBefore(el, host.children[op.index] ?? null);
        break;
      }
    }
  }
}
