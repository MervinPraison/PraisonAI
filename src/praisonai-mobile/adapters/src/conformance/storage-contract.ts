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
 *  the count short and the last case fail by name. The durability branch adds
 *  three, so the expected total depends on whether the adapter claims to
 *  survive a relaunch. */
const EXPECTED_ASSERTIONS = 17;
const DURABLE_ASSERTIONS = 3;

import type { StoragePort } from "../../../core/src/ports/storage.ts";

/**
 * Build a SECOND port over the same backing store, as the next launch does.
 *
 * Supplied only by adapters that claim durability, which is the property the
 * crash screen's "Your conversations are saved" depends on. The fake is
 * in-memory by design and does not claim it, so it is not asked to.
 */
export type Reopen = (storage: StoragePort) => Promise<StoragePort> | StoragePort;

export function describeStorageContract(
  name: string,
  make: () => StoragePort | Promise<StoragePort>,
  /** Present for a store that must survive the process ending. */
  reopen?: Reopen,
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

  test(`${name}: a concurrent read never sees a torn value`, async () => {
    // The port's atomicity clause, exercised rather than asserted in prose.
    //
    // "A concurrent read sees either the old value or the new one, never a
    // truncated file." On a phone this is not theoretical: iOS kills a
    // suspended app with no further callback, so a write interrupted halfway
    // is a normal occurrence. The standard implementation is write-to-temp
    // then rename; a plain truncate-and-write fails here, and the fixture's
    // `storage_torn_write` mode is exactly that defect.
    const storage = await make();
    const key = { namespace: "chats", id: "hot" } as const;
    const payloads = ["a", "b", "c"].map((c) => c.repeat(4096));

    await storage.write(key, payloads[0]!);
    const observed = new Set<string>();
    let running = true;
    const reader = (async () => {
      while (running) {
        const value = await storage.read(key);
        if (value !== null) observed.add(value);
      }
    })();

    try {
      // Several rounds, because one interleaving proves less than several.
      for (let round = 0; round < 5; round++) {
        await Promise.all(payloads.map((payload) => storage.write(key, payload)));
      }
    } finally {
      running = false;
      await reader;
    }

    const torn = [...observed].filter((value) => !payloads.includes(value));
    assert.deepEqual(
      torn.map((value) => `${value.length} bytes`),
      [],
      "a reader saw a value that was never written whole",
    );
    // The control. A reader that observed nothing at all would report no
    // tearing while proving nothing.
    assert.ok(observed.size > 0, "the reader never observed a value; this case proved nothing");
  });

  test(`${name}: an empty string is a value, not an absence`, async () => {
    // `""` is falsy, so an adapter using `||` instead of `??` turns a
    // deliberately-empty setting back into its default on every read.
    const storage = await make();
    await storage.write({ namespace: "settings", id: "empty" }, "");
    assert.equal(await storage.read({ namespace: "settings", id: "empty" }), "");
  });

  if (reopen !== undefined) {
    test(`${name}: a written value survives a relaunch`, async () => {
      // THE claim. ui/src/i18n/strings.ts tells the user after a crash that
      // "Your conversations are saved", and this is the only place that is
      // decided: a store that forgets when the process ends makes that string
      // a lie, and nothing else in the suite would notice.
      const storage = await make();
      await storage.write({ namespace: "chats", id: "c1" }, "the conversation");
      const relaunched = await reopen(storage);
      assert.equal(
        await relaunched.read({ namespace: "chats", id: "c1" }),
        "the conversation",
        "the conversation did not come back after a relaunch",
      );
    });

    test(`${name}: the chat list survives a relaunch`, async () => {
      // Reading a key you already know the id of is not enough: the chat list
      // is built from listIds, so a store that keeps values but rebuilds its
      // index empty shows the user no conversations at all.
      const storage = await make();
      await storage.write({ namespace: "chats", id: "a" }, "1");
      await storage.write({ namespace: "chats", id: "b" }, "2");
      const relaunched = await reopen(storage);
      assert.deepEqual((await relaunched.listIds("chats")).slice().sort(), ["a", "b"]);
    });

    test(`${name}: a deletion survives a relaunch too`, async () => {
      // The pair. A store that persisted writes and forgot deletes would
      // resurrect a conversation the user deliberately removed on every
      // launch -- which is worse than losing one.
      const storage = await make();
      await storage.write({ namespace: "chats", id: "gone" }, "x");
      await storage.remove({ namespace: "chats", id: "gone" });
      const relaunched = await reopen(storage);
      assert.equal(await relaunched.read({ namespace: "chats", id: "gone" }), null);
    });
  }

  // Registered last, so every case above has already run by the time it does.
  // Not a style check: the fixture in ./contract-fixture.ts can only protect
  // the FIRST assertion in each case, so without this an assertion can be
  // deleted and the run just reports one test fewer. See ./assert-ledger.ts.
  test(`${name}: this contract made every assertion it is supposed to make`, () => {
    const actual = made();
    const expected = EXPECTED_ASSERTIONS + (reopen === undefined ? 0 : DURABLE_ASSERTIONS);
    rawAssert.equal(
      actual,
      expected,
      `${name}: this contract ran ${actual} assertions, not ${expected}. ` +
        `If you deliberately added or removed one, update the constant in ` +
        `${'storage-contract.ts'} -- and consider whether the new assertion also needs a break ` +
        `mode in contract-fixture.ts, which is what proves it has teeth.`,
    );
  });
}
