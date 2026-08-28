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

  // The list as the DOM will actually look, updated as each op is emitted.
  //
  // This used to be `surviving` -- the previous ids minus removals -- with
  // moves spliced into it at the TARGET index. Those are two different
  // coordinate systems: the target index counts rows that were inserted this
  // pass, and `surviving` contains none of them. Inserted rows were never
  // added to it either, so the model drifted from the DOM as soon as one
  // insert preceded a reorder, and the ops then described a list nobody had.
  //
  // Measured by applying the real ops through the real `applyOps` to a DOM:
  // 120 of 960 exhaustive cases over 5 ids rendered the wrong order, and a
  // fuzz over 8 ids put it at 0.8%. `reconcile.test.ts` asserted op SHAPES and
  // never applied them, so nothing in the suite could see it.
  const current = previous.ids.filter((id) => nextIdSet.has(id));

  rows.forEach((row, index) => {
    const signature = signatureOf(row);
    nextSignatures.set(row.id, signature);

    if (!previousIds.has(row.id)) {
      ops.push({ kind: "insert", id: row.id, index, row });
      current.splice(index, 0, row.id);
      return;
    }

    if (previous.signatures.get(row.id) !== signature) {
      ops.push({ kind: "update", id: row.id, row });
    }

    // Already where it belongs: emit nothing. This is what keeps an append
    // from reporting a move for every row after it.
    if (current[index] === row.id) return;

    ops.push({ kind: "move", id: row.id, index });
    const at = current.indexOf(row.id);
    if (at !== -1) current.splice(at, 1);
    current.splice(index, 0, row.id);
  });

  return { ops, next: { ids: nextIds, signatures: nextSignatures } };
}
