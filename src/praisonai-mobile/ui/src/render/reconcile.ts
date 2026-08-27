/**
 * What the renderer must DO to the DOM, computed without touching it.
 *
 * A streaming answer publishes many times a second. Rebuilding the transcript
 * on each publish is what makes a chat app janky on a phone: it throws away
 * every node, loses selection and scroll anchoring, and forces layout on the
 * whole list to repaint one changed character at the end.
 *
 * So the renderer diffs. The diff is HERE and is pure -- it takes the previous
 * row ids and the next rows and returns operations -- because a diff mixed
 * into DOM calls can only be tested by inspecting a DOM, and the interesting
 * cases (a row inserted in the middle, an unchanged row left alone) are then
 * asserted on the wrong thing.
 *
 * The rule that makes this correct: ids are STABLE and UNIQUE per row. The
 * view model guarantees that, and its own test asserts it -- two rows sharing
 * an id is how a keyed renderer paints one row's content into another's node.
 */
import type { Row } from "../transcript/view-model.ts";

export type Op =
  /** Create a node for `row` and place it at `index`. */
  | { readonly kind: "insert"; readonly id: string; readonly index: number; readonly row: Row }
  /** The row at this id changed. Update in place -- never recreate, or a
   *  streaming paragraph loses its node on every token. */
  | { readonly kind: "update"; readonly id: string; readonly row: Row }
  /** Same node, new position. Moving beats destroy-and-recreate. */
  | { readonly kind: "move"; readonly id: string; readonly index: number }
  | { readonly kind: "remove"; readonly id: string };

/**
 * A row's identity for change detection.
 *
 * Deliberately NOT a deep equality check: rows are small but there are many,
 * and a per-publish deep compare of the whole list is the cost the diff exists
 * to avoid. Every field a row actually renders is folded into a string here,
 * so a change to any of them is a change.
 */
export function signatureOf(row: Row): string {
  switch (row.kind) {
    case "text":
      return `text|${row.streaming ? 1 : 0}|${row.text}`;
    case "reasoning":
      return `reasoning|${row.text}`;
    case "tool":
      return `tool|${row.status}|${row.name}|${row.seconds ?? ""}|${row.output}`;
    case "approval":
      return `approval|${row.state.status}|${row.actionable ? 1 : 0}|${row.name}`;
    case "notice":
      return `notice|${row.tone}|${row.text}`;
    case "error":
      // recovery is included: the same message can offer a different action
      // once the engine reports a different kind.
      return `error|${row.errorKind}|${row.recovery}|${row.tone}|${row.message}`;
    case "dropped":
      return `dropped|${row.count}|${row.reasons.join(",")}`;
    default: {
      // Exhaustiveness: a new row kind that forgets a signature would silently
      // never update, which reads as a frozen UI rather than a missing case.
      const never: never = row;
      return JSON.stringify(never);
    }
  }
}

export interface RenderState {
  /** Row ids in document order, as last applied. */
  readonly ids: readonly string[];
  readonly signatures: ReadonlyMap<string, string>;
}

export const emptyRender: RenderState = { ids: [], signatures: new Map() };

export interface Diff {
  readonly ops: readonly Op[];
  readonly next: RenderState;
}

export function reconcile(previous: RenderState, rows: readonly Row[]): Diff {
  const ops: Op[] = [];
  const nextIds = rows.map((r) => r.id);
  const nextSignatures = new Map<string, string>();
  const previousIds = new Set(previous.ids);
  const nextIdSet = new Set(nextIds);

  // Removals first, so later index arithmetic is against a list that no longer
  // contains the departed rows.
  for (const id of previous.ids) {
    if (!nextIdSet.has(id)) ops.push({ kind: "remove", id });
  }

  // The surviving rows, in their previous relative order. Anything whose
  // position within THIS sequence changes genuinely moved; comparing against
  // raw previous indices instead would report a move for every row after a
  // single insertion.
  const surviving = previous.ids.filter((id) => nextIdSet.has(id));
  let survivorCursor = 0;

  rows.forEach((row, index) => {
    const signature = signatureOf(row);
    nextSignatures.set(row.id, signature);

    if (!previousIds.has(row.id)) {
      ops.push({ kind: "insert", id: row.id, index, row });
      return;
    }

    if (previous.signatures.get(row.id) !== signature) {
      ops.push({ kind: "update", id: row.id, row });
    }

    if (surviving[survivorCursor] !== row.id) {
      ops.push({ kind: "move", id: row.id, index });
      const at = surviving.indexOf(row.id, survivorCursor);
      if (at !== -1) surviving.splice(at, 1);
      surviving.splice(index, 0, row.id);
    }
    survivorCursor++;
  });

  return { ops, next: { ids: nextIds, signatures: nextSignatures } };
}
