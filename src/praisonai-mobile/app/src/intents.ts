/**
 * What a tap MEANS, decided without a DOM.
 *
 * `app/src/dom.ts` renders approval buttons carrying `data-approval-id` and
 * `data-choice`, and nothing listened for them -- so an approval prompt was
 * drawn, blocked the run, and could not be answered. That is the worst class
 * of bug this package guards against: the UI looks correct and the run hangs
 * until the engine's timeout with nothing on screen to explain it.
 *
 * The mapping lives here as a pure function over a plain attribute bag rather
 * than inside a listener, for the usual reason: a decision buried in an event
 * handler can only be tested by synthesising events against a real DOM, and
 * the cases that matter -- a tap that lands on the icon INSIDE a button, a tap
 * on a disabled control, a stale id from a row that has since been replaced --
 * are then asserted against the wrong thing.
 */
import type { ApprovalChoice } from "../../protocol/src/events.ts";

export type Intent =
  | { readonly kind: "approve"; readonly approvalId: string; readonly choice: ApprovalChoice }
  | { readonly kind: "send" }
  | { readonly kind: "stop" }
  | { readonly kind: "new-chat" }
  | { readonly kind: "open-chat"; readonly chatId: string }
  | { readonly kind: "delete-chat"; readonly chatId: string }
  | { readonly kind: "navigate"; readonly route: string }
  /**
   * A settings field was committed.
   *
   * `raw` is the text exactly as the field held it -- unparsed and
   * unvalidated, because deciding whether "9000" is a legal port for this key
   * needs the def, and this file deliberately knows about no settings at all.
   * `ui/src/settings/view-model.ts`'s `validateInput` is what turns it into a
   * value, and the handler is where a refusal becomes something the user can
   * see.
   */
  | { readonly kind: "set-setting"; readonly key: string; readonly raw: string }
  | { readonly kind: "retry" }
  | { readonly kind: "copy" };

/** The subset of an element this decision needs. Keeps it DOM-free. */
export interface Actionable {
  /** `data-*` attributes, camelCased exactly as `HTMLElement.dataset` gives them. */
  readonly dataset: Readonly<Record<string, string | undefined>>;
  readonly disabled?: boolean;
  /**
   * What the control currently holds, for the elements that hold anything.
   *
   * Absent on every element that is not a field -- a `<div>` row, a `<span>`
   * label, the section heading. That ABSENCE is load-bearing: it is the only
   * thing separating "the user cleared this field" from "this element has no
   * field in it", and conflating the two turns a stray tap into a wiped engine
   * address on the one screen that exists to repair it.
   */
  readonly value?: string;
}

const CHOICES: readonly string[] = ["allow", "always", "deny"];

/**
 * Read an intent off the nearest actionable ancestor.
 *
 * Takes the ANCESTOR CHAIN rather than a single element, because a tap lands
 * on whatever is under the finger -- a label or an icon inside the button, not
 * the button. Walking outward is what every real UI toolkit does and what a
 * naive `event.target` check gets wrong on exactly the taps users make most.
 */
export function intentFrom(chain: readonly Actionable[]): Intent | null {
  for (const el of chain) {
    // A disabled control is not merely styled: it must not act. Approval
    // buttons go disabled while a decision is in flight, and honouring that
    // here is what stops a double tap sending two decisions.
    if (el.disabled === true) return null;

    const d = el.dataset;

    const approvalId = d["approvalId"];
    const choice = d["choice"];
    if (approvalId !== undefined && choice !== undefined) {
      // An unrecognised choice is refused rather than coerced. Sending a
      // decision the engine does not understand is worse than not sending one:
      // the run stays blocked either way, but a refusal is visible here.
      if (!CHOICES.includes(choice)) return null;
      return { kind: "approve", approvalId, choice: choice as ApprovalChoice };
    }

    const action = d["action"];
    if (action === undefined) continue;

    switch (action) {
      case "send":
        return { kind: "send" };
      case "stop":
        return { kind: "stop" };
      case "new-chat":
        return { kind: "new-chat" };
      case "retry":
        return { kind: "retry" };
      case "copy":
        return { kind: "copy" };
      case "open-chat": {
        const chatId = d["chatId"];
        return chatId === undefined ? null : { kind: "open-chat", chatId };
      }
      case "delete-chat": {
        const chatId = d["chatId"];
        return chatId === undefined ? null : { kind: "delete-chat", chatId };
      }
      case "navigate": {
        const route = d["route"];
        return route === undefined ? null : { kind: "navigate", route };
      }
      case "set-setting": {
        // Both halves are required, and for different reasons. A missing key
        // is the delete-chat rule again: a write aimed at "" is refused by the
        // store anyway, but silently, and the user is told nothing. A missing
        // VALUE means this element is not a field -- see `Actionable.value`.
        const key = d["settingKey"];
        if (key === undefined) return null;
        const raw = el.value;
        return raw === undefined ? null : { kind: "set-setting", key, raw };
      }
      default:
        // An unknown action is not an error -- a newer template can carry one
        // this build has never heard of -- but it must not silently resolve to
        // some other intent, so the walk stops here.
        return null;
    }
  }
  return null;
}
