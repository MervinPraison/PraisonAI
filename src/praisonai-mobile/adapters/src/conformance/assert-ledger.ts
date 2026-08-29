/**
 * A counting proxy over `node:assert/strict`, so an assertion cannot vanish
 * from a contract without the run noticing.
 *
 * WHY THIS EXISTS. `contract-fixture.ts` proves a contract still CONTAINS the
 * assertion that catches a given defect: it registers a deliberately broken
 * adapter and asserts the matching case fails by name. That works, and it
 * caught real hollowing. But it protects exactly one assertion per break mode
 * -- the FIRST one in that case to trip. Every other assertion in the same
 * case is still free to be deleted, because the case keeps failing on the one
 * before it.
 *
 * Measured, by deleting each single-line assertion in the four adapter
 * contracts one at a time and running the whole adapters suite: 62 of 73 could
 * be removed with a fully green run. Thirteen break modes were protecting
 * eleven assertions. The contracts are shared code that every adapter is
 * judged against, and the failure mode is silent -- the run reports one test
 * fewer and nothing else -- so the gap is worth closing with a mechanism
 * rather than with sixty more break modes.
 *
 * HOW. Each `describeXContract` call takes its own ledger and uses it in place
 * of the bare `assert`. The contract's last registered case asserts the exact
 * number of assertions the earlier cases made. Delete one and the count is
 * short; the case fails and names the file. Add one and the count is over, and
 * the constant has to be updated deliberately -- which is the point, since
 * that is where you would notice you had also meant to give it a break mode.
 *
 * The count is EXACT rather than a floor. A floor lets an assertion be
 * replaced by a weaker one at the same arity, which is the same hollowing
 * wearing a different hat.
 *
 * This does not claim an assertion still asserts something USEFUL -- only that
 * it is still there and still ran. `contract-fixture.ts` remains the thing
 * that proves the assertion has teeth; the two are complementary and neither
 * subsumes the other.
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
