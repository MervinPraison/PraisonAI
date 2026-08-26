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

/** Write a row's content into its element. Called on insert and on update. */
function paint(el: HTMLElement, row: Row, strings: Strings): void {
  switch (row.kind) {
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
      const name = el.ownerDocument.createElement("span");
      name.className = "tool-name";
      name.textContent = row.name;
      const meta = el.ownerDocument.createElement("span");
      meta.className = "tool-meta";
      // durationKnown is separate from the label: `seconds: null` means the
      // engine never observed the call begin, which is not zero.
      meta.textContent = row.durationKnown ? row.durationLabel : UNKNOWN;
      el.append(name, meta);
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
        host.insertBefore(el, host.children[op.index] ?? null);
        break;
      }
    }
  }
}
