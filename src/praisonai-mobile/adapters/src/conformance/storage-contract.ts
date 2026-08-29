/**
 * The StoragePort contract, as a runnable suite.
 *
 * Every adapter runs this — the fake, the web adapter, and later the Tauri
 * one. That is what stops the three drifting: if the fake returns `undefined`
 * for a missing key while the real adapter returns `null`, every test that
 * uses the fake passes and the app still breaks on a device.
 *
 * Like the engine conformance suite, this one has to be able to FAIL.
 * `contracts.test.ts` runs it against deliberately broken adapters and asserts
 * which case each one fails.
 */
import test from "node:test";
import rawAssert from "node:assert/strict";
import { ledger, type Ledger } from "./assert-ledger.ts";

/** How many assertions the cases below make in one run. Deleting one makes
 *  the count short and the last case fail by name. */
const EXPECTED_ASSERTIONS = 15;

import type { StoragePort } from "../../../core/src/ports/storage.ts";

export function describeStorageContract(
  name: string,
  make: () => StoragePort | Promise<StoragePort>,
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

  test(`${name}: a missing key reads as null, never undefined`, async () => {
    // The distinction matters to every `??` in a caller. `undefined` and `null`
    // behave the same for `??` but differently for `===`, and a repository that
    // checks `=== null` silently treats undefined as present.
    const storage = await make();
    const value = await storage.read({ namespace: "chats", id: "nope" });
    assert.equal(value, null);
    assert.notEqual(value, undefined, "must be null specifically, not undefined");
  });

  test(`${name}: a written value reads back exactly`, async () => {
    const storage = await make();
    // Deliberately awkward: newlines, quotes, unicode, and a lone surrogate
    // pair, because a naive file or SQL adapter mangles at least one.
    const payload = '{"a":"line1\\nline2","b":"quo\\"te","c":"日本語 🎉"}';
    await storage.write({ namespace: "chats", id: "c1" }, payload);
    assert.equal(await storage.read({ namespace: "chats", id: "c1" }), payload);
  });

  test(`${name}: a rewrite replaces rather than appends`, async () => {
    const storage = await make();
    await storage.write({ namespace: "chats", id: "c1" }, "first");
    await storage.write({ namespace: "chats", id: "c1" }, "second");
    assert.equal(await storage.read({ namespace: "chats", id: "c1" }), "second");
  });

  test(`${name}: namespaces are isolated`, async () => {
    // The reason a bare string key is unrepresentable. Without isolation a
    // chat id colliding with a settings id silently overwrites one of them.
    const storage = await make();
    await storage.write({ namespace: "chats", id: "same" }, "chat value");
    await storage.write({ namespace: "settings", id: "same" }, "settings value");

    assert.equal(await storage.read({ namespace: "chats", id: "same" }), "chat value");
    assert.equal(await storage.read({ namespace: "settings", id: "same" }), "settings value");
  });

  test(`${name}: listIds returns only its own namespace`, async () => {
    const storage = await make();
    await storage.write({ namespace: "chats", id: "a" }, "1");
    await storage.write({ namespace: "chats", id: "b" }, "2");
    await storage.write({ namespace: "settings", id: "c" }, "3");

    assert.deepEqual((await storage.listIds("chats")).slice().sort(), ["a", "b"]);
    assert.deepEqual(await storage.listIds("settings"), ["c"]);
  });

  test(`${name}: listIds is empty for an untouched namespace`, async () => {
    const storage = await make();
    assert.deepEqual(await storage.listIds("drafts"), []);
  });

  test(`${name}: removing an absent key succeeds`, async () => {
    // The caller wanted it gone and it is gone. Throwing here forces every
    // delete path to wrap itself in a try.
    const storage = await make();
    await assert.doesNotReject(() => storage.remove({ namespace: "chats", id: "ghost" }));
  });

  test(`${name}: a removed key reads as null again`, async () => {
    const storage = await make();
    await storage.write({ namespace: "chats", id: "c1" }, "x");
    await storage.remove({ namespace: "chats", id: "c1" });
    assert.equal(await storage.read({ namespace: "chats", id: "c1" }), null);
  });

  test(`${name}: clear empties one namespace and leaves the others`, async () => {
    const storage = await make();
    await storage.write({ namespace: "chats", id: "a" }, "1");
    await storage.write({ namespace: "chats", id: "b" }, "2");
    await storage.write({ namespace: "settings", id: "keep" }, "3");

    await storage.clear("chats");
    assert.deepEqual(await storage.listIds("chats"), []);
    assert.deepEqual(await storage.listIds("settings"), ["keep"]);
  });

  test(`${name}: clear removes every key, not every other one`, async () => {
    // The index-shifting bug. An adapter iterating by index while removing
    // skips alternate entries and reports success.
    const storage = await make();
    for (const id of ["a", "b", "c", "d", "e"]) {
      await storage.write({ namespace: "chats", id }, id);
    }
    await storage.clear("chats");
    assert.deepEqual(await storage.listIds("chats"), []);
  });

  test(`${name}: an empty string is a value, not an absence`, async () => {
    // `""` is falsy, so an adapter using `||` instead of `??` turns a
    // deliberately-empty setting back into its default on every read.
    const storage = await make();
    await storage.write({ namespace: "settings", id: "empty" }, "");
    assert.equal(await storage.read({ namespace: "settings", id: "empty" }), "");
  });

  // Registered last, so every case above has already run by the time it does.
  // Not a style check: the fixture in ./contract-fixture.ts can only protect
  // the FIRST assertion in each case, so without this an assertion can be
  // deleted and the run just reports one test fewer. See ./assert-ledger.ts.
  test(`${name}: this contract made every assertion it is supposed to make`, () => {
    const actual = made();
    rawAssert.equal(
      actual,
      EXPECTED_ASSERTIONS,
      `${name}: this contract ran ${actual} assertions, not ${EXPECTED_ASSERTIONS}. ` +
        `If you deliberately added or removed one, update the constant in ` +
        `${'storage-contract.ts'} -- and consider whether the new assertion also needs a break ` +
        `mode in contract-fixture.ts, which is what proves it has teeth.`,
    );
  });
}
