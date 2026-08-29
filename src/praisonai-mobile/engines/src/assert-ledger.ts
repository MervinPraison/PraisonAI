/**
 * A counting proxy over `node:assert/strict`, so an assertion cannot vanish
 * from a contract without the run noticing.
 *
 * A byte-for-byte twin of `adapters/src/conformance/assert-ledger.ts`. The two
 * are deliberately separate files: `engines` may not import `adapters` and the
 * layer rule is right to say so, and neither belongs in `core`, which ships.
 * The fixture pattern one directory over is duplicated for the same reason.
 *
 * WHY THIS EXISTS. `contract-fixture.ts` proves a contract still CONTAINS the
 * assertion that catches a given defect: it registers a deliberately broken
 * adapter and asserts the matching case fails by name. That works, and it
 * caught real hollowing. But it protects exactly one assertion per break mode
 * -- the FIRST one in that case to trip. Every other assertion in the same
 * case is still free to be deleted, because the case keeps failing on the one
 * before it.
 *
 * Measured, by deleting each single-line assertion in this contract one
 * at a time and running the whole engines suite: 30 of 32 could be removed
 * with a fully green run. Five break modes were protecting two assertions.
 * (The four adapter contracts measured 62 of 73 on the same method.) A
 * contract is shared code that every engine is judged against, and the failure
 * mode is silent -- the run reports one test fewer and nothing else -- so the
 * gap is worth closing with a mechanism rather than with thirty more break
 * modes.
 *
 * HOW. `describeEngineContract` takes its own ledger and uses it in place of the
 * bare `assert`, and EACH case ends by asserting the exact number of
 * assertions it made. Per case rather than one total, because a harness
 * declares which scenarios it cannot support and skips them, so no single
 * total is right for every engine. Delete an assertion and its case's count is
 * short and the case fails by name. Add one and the count is over, and the
 * constant has to be updated deliberately -- which is the point, since that is
 * where you would notice the new assertion also wants a break mode.
 *
 * The count is EXACT rather than a floor. A floor lets an assertion be
 * replaced by a weaker one at the same arity, which is the same hollowing
 * wearing a different hat.
 *
 * This does not claim an assertion still asserts something USEFUL -- only that
 * it is still there and still ran. `contract-fixture.ts` remains the thing
 * that proves the assertion has teeth; the two are complementary and neither
 * subsumes the other. `assert-ledger.test.ts` covers this file itself, which
 * is now load-bearing for every count in the contract.
 */
import assert from "node:assert/strict";

export interface Ledger {
  /** Drop-in for `node:assert/strict`, counting every call. */
  readonly assert: typeof assert;
  /** How many assertions have been made through this ledger so far. */
  made(): number;
}

export function ledger(): Ledger {
  let made = 0;

  // `assert` is both callable and a namespace of callables, so the proxy has
  // to handle both: `assert(x)` goes through `apply`, `assert.equal(a, b)`
  // through `get`. Counting only one of the two would leave a whole style of
  // assertion unprotected.
  const counted = new Proxy(assert, {
    apply(target, thisArg, args: unknown[]): unknown {
      made += 1;
      return Reflect.apply(target as (...a: unknown[]) => unknown, thisArg, args);
    },
    get(target, prop, receiver): unknown {
      const value = Reflect.get(target, prop, receiver) as unknown;
      if (typeof value !== "function") return value;
      return (...args: unknown[]): unknown => {
        made += 1;
        return (value as (...a: unknown[]) => unknown).apply(target, args);
      };
    },
  });

  return { assert: counted as typeof assert, made: () => made };
}
