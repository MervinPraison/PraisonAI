/**
 * The crash handler.
 *
 * A throw inside a click handler used to produce a UI that simply stopped
 * responding: no message, no recovery, and on a phone no console to read. The
 * cases here are about the two ways a crash handler makes things worse — by
 * swallowing the error, and by looping.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { installCrashHandler } from "./crash.ts";

/** A Window with just the two listeners this touches. */
function fakeView() {
  const handlers = new Map<string, Set<(e: unknown) => void>>();
  return {
    view: {
      addEventListener(type: string, cb: (e: unknown) => void) {
        const set = handlers.get(type) ?? new Set();
        set.add(cb);
        handlers.set(type, set);
      },
      removeEventListener(type: string, cb: (e: unknown) => void) {
        handlers.get(type)?.delete(cb);
      },
    } as unknown as Window,
    error: (payload: unknown) => {
      for (const cb of [...(handlers.get("error") ?? [])]) cb({ error: payload });
    },
    reject: (reason: unknown) => {
      for (const cb of [...(handlers.get("unhandledrejection") ?? [])]) cb({ reason });
    },
    count: () => [...handlers.values()].reduce((n, s) => n + s.size, 0),
  };
}

test("an uncaught error reaches the crash screen", () => {
  const fake = fakeView();
  let shown: unknown = null;
  installCrashHandler({ view: fake.view, onCrash: (e) => void (shown = e), report: () => {} });
  fake.error(new Error("boom"));
  assert.equal((shown as Error).message, "boom");
});

test("an unhandled rejection reaches it too", () => {
  // The one people forget. An async click handler that rejects produces no
  // `error` event at all -- only this.
  const fake = fakeView();
  let shown: unknown = null;
  installCrashHandler({ view: fake.view, onCrash: (e) => void (shown = e), report: () => {} });
  fake.reject(new Error("async boom"));
  assert.equal((shown as Error).message, "async boom");
});

test("the error is still reported, never swallowed", () => {
  // A handler that quietly absorbs everything turns a crash into a mystery --
  // the device log is the only forensics available on a phone.
  const fake = fakeView();
  const reported: unknown[] = [];
  installCrashHandler({ view: fake.view, onCrash: () => {}, report: (_l, e) => void reported.push(e) });
  fake.error(new Error("keep me"));
  assert.equal(reported.length, 1);
});

test("the crash screen is drawn ONCE however many faults follow", () => {
  // A crash cascades: the failed render throws again on the next frame. A
  // handler that repaints each time turns one fault into a loop that pins the
  // CPU and drains the battery.
  const fake = fakeView();
  let draws = 0;
  installCrashHandler({ view: fake.view, onCrash: () => void draws++, report: () => {} });
  fake.error(new Error("1"));
  fake.error(new Error("2"));
  fake.reject(new Error("3"));
  assert.equal(draws, 1);
});

test("every later fault is still reported", () => {
  // The pair for the test above: drawing once must not mean logging once, or
  // the cascade that explains the root cause is invisible.
  const fake = fakeView();
  const reported: unknown[] = [];
  installCrashHandler({ view: fake.view, onCrash: () => {}, report: (_l, e) => void reported.push(e) });
  fake.error(new Error("1"));
  fake.error(new Error("2"));
  assert.equal(reported.length, 2);
});

test("a crash screen that itself throws does not loop", () => {
  // Nothing further is safe to attempt at that point, and looping is worse
  // than a blank page.
  const fake = fakeView();
  const reported: string[] = [];
  installCrashHandler({
    view: fake.view,
    onCrash: () => { throw new Error("the screen broke too"); },
    report: (label) => void reported.push(label),
  });
  assert.doesNotThrow(() => fake.error(new Error("boom")));
  assert.ok(reported.includes("crash-screen-failed"));
});

test("crashed() reports the state", () => {
  const fake = fakeView();
  const handle = installCrashHandler({ view: fake.view, onCrash: () => {}, report: () => {} });
  assert.equal(handle.crashed(), false);
  fake.error(new Error("x"));
  assert.equal(handle.crashed(), true);
});

test("remove() detaches both listeners", () => {
  const fake = fakeView();
  const handle = installCrashHandler({ view: fake.view, onCrash: () => {}, report: () => {} });
  assert.equal(fake.count(), 2);
  handle.remove();
  assert.equal(fake.count(), 0);
});
