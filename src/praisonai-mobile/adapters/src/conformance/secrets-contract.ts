/**
 * The SecretsPort contract, as a runnable suite.
 *
 * There was no test of any kind for `adapters/src/web/secrets.ts`, and a
 * mutation sweep found the consequence: collapsing the storage key from
 * `${slot}:${account}` to `${slot}` survived the entire suite. Two accounts in
 * one slot then share a single credential -- adding a second profile's API key
 * silently overwrites the first, reading either returns the last one written,
 * `has()` returns true for an account that was never set, and deleting one
 * deletes both.
 *
 * That is the worst failure this port can have, and it was reachable in a
 * module nothing executed.
 *
 * Written as a contract rather than a test of one adapter because the fake and
 * the web adapter must agree: a test that passes against a fake with different
 * key semantics is how a device-only defect gets shipped. The two ports that
 * already had contracts scored best in that sweep; the two without scored
 * worst.
 */
import test from "node:test";
import rawAssert from "node:assert/strict";
import { ledger, type Ledger } from "./assert-ledger.ts";

/** How many assertions the cases below make in one run. Deleting one makes
 *  the count short and the last case fail by name. The durability branch adds
 *  six and the presence branch four, so the expected total depends on what the
 *  adapter claims. */
const EXPECTED_ASSERTIONS = 16;
const DURABLE_ASSERTIONS = 6;
const PRESENCE_ASSERTIONS = 4;

import type { SecretsPort } from "../../../core/src/ports/secrets.ts";

/**
 * Build a SECOND port over the same platform store, as the next launch does.
 *
 * Supplied only by an adapter that claims durability -- which for THIS port is
 * the whole of it. `core/src/ports/secrets.ts` calls the port "the keychain
 * (iOS) and keystore (Android)", and a keychain that forgets when the process
 * ends is not one: the user re-types their API key on every launch, the app
 * looks like it works, and nothing in a suite of fourteen hundred tests
 * notices. The web adapter is a module-scoped Map by design and does not claim
 * it, so it is not asked to.
 */
export type ReopenSecrets = (secrets: SecretsPort) => Promise<SecretsPort> | SecretsPort;

/**
 * How many times this port has actually READ a value out.
 *
 * Supplied by an adapter that can observe it. Rule 2 of the port -- `has()`
 * "must not fault the value into memory" -- is otherwise untestable from out
 * here: `has` implemented as `get(ref) !== null` returns exactly the right
 * booleans in every case below, and quietly copies the user's API key out of
 * the keychain and into the webview's heap on every repaint of the settings
 * screen.
 */
export type SecretReads = (secrets: SecretsPort) => number;

export function describeSecretsContract(
  name: string,
  make: () => SecretsPort | Promise<SecretsPort>,
  /** Present for a store that must survive the process ending. */
  reopen?: ReopenSecrets,
  /** Present for a port that can say how often a value was read out. */
  readsOf?: SecretReads,
): void {
  // Every assertion below is counted, and the last case in this contract
  // asserts the total. See ./assert-ledger.ts: the break-mode fixture can
  // only protect the first assertion in each case, and 62 of 73 were
  // measured deletable with a green run.
  // Declared with an explicit type rather than destructured: `assert` carries
  // `asserts` signatures, and TS2775 refuses those through a binding pattern.
  const counting = ledger();
  const assert: Ledger["assert"] = counting.assert;
  const made = counting.made;

  const openai = { slot: "openai" as const, account: "default" };

  test(`${name}: a secret that was never set reads as null`, async () => {
    const secrets = await make();
    assert.equal(await secrets.get(openai), null);
    assert.equal(await secrets.has(openai), false);
  });

  test(`${name}: a stored secret reads back exactly`, async () => {
    const secrets = await make();
    await secrets.set(openai, "sk-live-abc123");
    assert.equal(await secrets.get(openai), "sk-live-abc123");
    assert.equal(await secrets.has(openai), true);
  });

  test(`${name}: two ACCOUNTS in one slot are two different secrets`, async () => {
    // THE CASE. Keying by slot alone makes a second profile silently overwrite
    // the first, and every read return whichever was written last.
    const secrets = await make();
    const a = { slot: "openai" as const, account: "work" };
    const b = { slot: "openai" as const, account: "personal" };

    await secrets.set(a, "sk-work");
    await secrets.set(b, "sk-personal");

    assert.equal(await secrets.get(a), "sk-work", "the second account overwrote the first");
    assert.equal(await secrets.get(b), "sk-personal");
  });

  test(`${name}: an account that was never set is absent, even in a used slot`, async () => {
    // The other half: `has` must not answer for a sibling account.
    const secrets = await make();
    await secrets.set({ slot: "openai", account: "work" }, "sk-work");
    assert.equal(await secrets.has({ slot: "openai", account: "never-set" }), false);
    assert.equal(await secrets.get({ slot: "openai", account: "never-set" }), null);
  });

  test(`${name}: deleting one account leaves its siblings alone`, async () => {
    const secrets = await make();
    const a = { slot: "openai" as const, account: "work" };
    const b = { slot: "openai" as const, account: "personal" };
    await secrets.set(a, "sk-work");
    await secrets.set(b, "sk-personal");

    await secrets.delete(a);
    assert.equal(await secrets.has(a), false);
    assert.equal(await secrets.get(b), "sk-personal", "deleting one account deleted both");
  });

  test(`${name}: two SLOTS are two different secrets`, async () => {
    const secrets = await make();
    await secrets.set({ slot: "openai", account: "default" }, "sk-openai");
    await secrets.set({ slot: "anthropic", account: "default" }, "sk-engine");
    assert.equal(await secrets.get({ slot: "openai", account: "default" }), "sk-openai");
    assert.equal(await secrets.get({ slot: "anthropic", account: "default" }), "sk-engine");
  });

  test(`${name}: overwriting a secret replaces it rather than appending`, async () => {
    const secrets = await make();
    await secrets.set(openai, "first");
    await secrets.set(openai, "second");
    assert.equal(await secrets.get(openai), "second");
  });

  test(`${name}: deleting an absent secret succeeds`, async () => {
    // The caller wanted it gone and it is gone. Throwing forces every clear
    // path to wrap itself in a try.
    const secrets = await make();
    await assert.doesNotReject(() => secrets.delete({ slot: "openai", account: "ghost" }));
  });

  test(`${name}: an empty string is a stored value, not an absence`, async () => {
    // `""` is falsy, so an adapter using `||` turns a deliberately-blank
    // credential back into "not configured" on every read.
    const secrets = await make();
    await secrets.set(openai, "");
    assert.equal(await secrets.get(openai), "");
    assert.equal(await secrets.has(openai), true);
  });

  if (reopen !== undefined) {
    test(`${name}: a stored secret survives a relaunch`, async () => {
      // THE claim. The port's own first sentence is that it is the keychain and
      // the keystore; a store that forgets when the process ends makes that a
      // lie, and the user re-enters their API key on every launch forever.
      const secrets = await make();
      await secrets.set(openai, "sk-kept-across-launches");
      const relaunched = await reopen(secrets);
      assert.equal(
        await relaunched.get(openai),
        "sk-kept-across-launches",
        "the key did not come back after a relaunch",
      );
    });

    test(`${name}: presence survives a relaunch, not just the value`, async () => {
      // Reading a slot you already know is not enough: the settings row renders
      // "Configured" from `has`, so a store that kept the value and answered
      // `has` from a per-process index would show "Not set" next to a key that
      // is stored -- and the obvious response is to paste it in again.
      const secrets = await make();
      await secrets.set(openai, "sk-x");
      const relaunched = await reopen(secrets);
      assert.equal(await relaunched.has(openai), true, "the row would read Not set");
    });

    test(`${name}: a deletion survives a relaunch too`, async () => {
      // The pair. A store that persisted writes and forgot deletes would bring
      // back a credential the user deliberately removed, on every launch, which
      // is worse than losing one.
      const secrets = await make();
      await secrets.set(openai, "sk-x");
      await secrets.delete(openai);
      const relaunched = await reopen(secrets);
      assert.equal(await relaunched.has(openai), false);
      assert.equal(await relaunched.get(openai), null);
    });

    test(`${name}: a FRESH store has none of another store's secrets`, async () => {
      // THE CONTROL, and it is not decoration. Every case above is satisfied by
      // an adapter whose `make()` hands back one process-wide store: the
      // "relaunch" then returns the same object it was given, the value is
      // still there, and "survives a relaunch" passes while proving nothing at
      // all. This is the case that fails when the relaunch is not real -- a
      // brand new store must be empty.
      const used = await make();
      await used.set(openai, "sk-from-a-different-install");
      const fresh = await make();
      assert.equal(await fresh.get(openai), null, "a fresh store answered with another's secret");
      assert.equal(await fresh.has(openai), false);
    });
  }

  if (readsOf !== undefined) {
    test(`${name}: has() answers without reading the value`, async () => {
      // Rule 2 of core/src/ports/secrets.ts, as a behaviour rather than a
      // comment. `has: (ref) => (await get(ref)) !== null` passes every other
      // case in this file.
      const secrets = await make();
      await secrets.set(openai, "sk-secret");
      const before = readsOf(secrets);
      assert.equal(await secrets.has(openai), true);
      assert.equal(readsOf(secrets), before, "has() faulted the value into memory");

      // The miss too: an adapter that short-circuits a hit but reads on a miss
      // still pulls every OTHER slot's value out on every repaint.
      assert.equal(await secrets.has({ slot: "anthropic", account: "default" }), false);
      assert.equal(readsOf(secrets), before, "a has() MISS read a value out");
    });
  }

  // Registered last, so every case above has already run by the time it does.
  // Not a style check: the fixture in ./contract-fixture.ts can only protect
  // the FIRST assertion in each case, so without this an assertion can be
  // deleted and the run just reports one test fewer. See ./assert-ledger.ts.
  test(`${name}: this contract made every assertion it is supposed to make`, () => {
    const actual = made();
    const expected =
      EXPECTED_ASSERTIONS +
      (reopen === undefined ? 0 : DURABLE_ASSERTIONS) +
      (readsOf === undefined ? 0 : PRESENCE_ASSERTIONS);
    rawAssert.equal(
      actual,
      expected,
      `${name}: this contract ran ${actual} assertions, not ${expected}. ` +
        `If you deliberately added or removed one, update the constant in ` +
        `${'secrets-contract.ts'} -- and consider whether the new assertion also needs a break ` +
        `mode in contract-fixture.ts, which is what proves it has teeth.`,
    );
  });
}
