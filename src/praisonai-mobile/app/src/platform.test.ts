/**
 * Platform detection — the one function that decides which of the two shells
 * actually ships.
 *
 * It had no test. A mutation audit found that making it ALWAYS return the web
 * shell left the whole suite green: an on-device build would silently fall
 * back to the browser shell, with no safe-area insets, no OS back gesture and
 * no lifecycle — and the app would look like it worked.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { detectPlatform } from "./platform.ts";
import { createFakeWindow } from "../../adapters/src/web/fake-window.ts";

const view = () => createFakeWindow().window;

test("a native host gets the Tauri shell", () => {
  // The whole point of the file. Falling back here loses every capability the
  // native shell exists to provide, and nothing errors.
  const p = detectPlatform({ isNative: () => true, view: view() });
  assert.equal(p.kind, "tauri");
  assert.equal(p.shell.kind, "tauri");
});

test("a browser gets the web shell", () => {
  // The pair. Always returning Tauri would be just as wrong in the other
  // direction, and would fail on a host with no __TAURI_INTERNALS__ at all.
  const p = detectPlatform({ isNative: () => false, view: view() });
  assert.equal(p.kind, "web");
  assert.equal(p.shell.kind, "web");
});

test("`kind` and the shell it built never disagree", () => {
  // `kind` is what the About screen and the not-hardware-backed warning read.
  // A kind that says "tauri" over a web shell reports a safety the platform is
  // not providing.
  for (const native of [true, false]) {
    const p = detectPlatform({ isNative: () => native, view: view() });
    assert.equal(p.kind, p.shell.kind, `kind ${p.kind} but shell ${p.shell.kind}`);
  }
});

test("every port is present, whichever platform was chosen", () => {
  // A missing port is a boot-time crash on a device and nothing here.
  for (const native of [true, false]) {
    const p = detectPlatform({ isNative: () => native, view: view() });
    for (const key of ["shell", "storage", "secrets", "http", "time"] as const) {
      assert.ok(p[key] !== undefined && p[key] !== null, `${key} missing on ${p.kind}`);
    }
  }
});

test("the probe is synchronous", () => {
  // `ShellPort.insets` must be readable during the first paint, so the
  // decision cannot be a promise -- an async answer makes the first frame
  // guess, paint wrong, and jump.
  const p = detectPlatform({ isNative: () => true, view: view() });
  assert.equal(typeof (p as unknown as { then?: unknown }).then, "undefined");
  assert.equal(typeof p.shell.insets, "object", "insets must be readable immediately");
});

test("the web platform stores chats in localStorage, not sessionStorage", () => {
  // `view.localStorage` -> `view.sessionStorage` survived. Every chat would
  // die with the tab, which on a phone is every time the OS reclaims the
  // webview. platform.ts's own comment is about localStorage EVICTION being a
  // risk; nothing asserted which store it actually reached for.
  const used: string[] = [];
  const spy = (name: string): Storage =>
    ({
      getItem: () => { used.push(name); return null; },
      setItem: () => void used.push(name),
      removeItem: () => void used.push(name),
      key: () => null,
      clear: () => void used.push(name),
      length: 0,
    }) as unknown as Storage;

  // A real fake window, because createWebShell needs getComputedStyle and a
  // hand-rolled stub cannot keep up with what the adapter reads.
  const fake = createFakeWindow();
  const view = fake.window as unknown as { localStorage: Storage; sessionStorage: Storage };
  view.localStorage = spy("local");
  view.sessionStorage = spy("session");

  const platform = detectPlatform({ isNative: () => false, view: fake.window as unknown as Window });
  void platform.storage.read({ namespace: "chats", id: "any" });

  assert.ok(used.includes("local"), `the chat store must be localStorage, got ${used.join(",") || "none"}`);
  assert.equal(used.includes("session"), false, "sessionStorage dies with the tab");
});
