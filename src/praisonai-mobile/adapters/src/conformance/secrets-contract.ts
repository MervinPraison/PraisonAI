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
import assert from "node:assert/strict";

import type { SecretsPort } from "../../../core/src/ports/secrets.ts";

export function describeSecretsContract(
  name: string,
  make: () => SecretsPort | Promise<SecretsPort>,
): void {
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
}
