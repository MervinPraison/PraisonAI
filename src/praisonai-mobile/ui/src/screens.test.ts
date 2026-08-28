/**
 * Screen transitions.
 *
 * Almost every case here is about what should be KEPT rather than what should
 * be shown. A dispatcher that rebuilt everything on every navigation would
 * pass any test asserting "the right screen is visible" — and would dump a
 * reader at the bottom of a conversation every time they checked a setting.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { RETAINED, screenFor, transition, type ScreenId } from "./screens.ts";
import type { Route } from "./router.ts";

const chats: Route = { name: "chats" };
const chat = (chatId = "c1"): Route => ({ name: "chat", chatId });
const settings: Route = { name: "settings" };
const about: Route = { name: "about" };

const live = (...ids: ScreenId[]): ReadonlySet<ScreenId> => new Set(ids);

test("every route maps to a screen", () => {
  assert.equal(screenFor(chats), "chats");
  assert.equal(screenFor(chat()), "chat");
  assert.equal(screenFor(settings), "settings");
  assert.equal(screenFor(about), "about");
});

test("the first navigation mounts the target and unmounts nothing", () => {
  const change = transition(null, chats, live());
  assert.deepEqual(change.mount, ["chats"]);
  assert.deepEqual(change.unmount, []);
  assert.equal(change.show, "chats");
});

test("leaving the chat screen HIDES it rather than destroying it", () => {
  // The case this file exists for. Destroying the transcript throws away every
  // row node and the scroll position with them, so a reader who scrolls up,
  // opens settings and comes back is dumped at the bottom.
  const change = transition(chat(), settings, live("chat"));
  assert.deepEqual(change.hide, ["chat"]);
  assert.deepEqual(change.unmount, [], "the chat screen must not be destroyed");
});

test("returning to a retained chat screen mounts nothing", () => {
  // The other half: if coming back rebuilt it, retaining it bought nothing.
  const change = transition(settings, chat(), live("chat", "settings"));
  assert.deepEqual(change.mount, [], "the chat screen is already there");
  assert.equal(change.show, "chat");
});

test("leaving a NON-retained screen destroys it", () => {
  // The pair for the retention rule. Keeping settings alive would show stale
  // values on return, and "retain everything" would satisfy the tests above.
  const change = transition(settings, chats, live("settings"));
  assert.deepEqual(change.unmount, ["settings"]);
  assert.deepEqual(change.hide, []);
});

test("moving between two chats is a content change, not a screen change", () => {
  // Rebuilding here would drop the transcript on every navigation WITHIN the
  // same screen, which is the most common navigation in the app.
  const change = transition(chat("c1"), chat("c2"), live("chat"));
  assert.equal(change.noop, true);
  assert.deepEqual(change.mount, []);
  assert.deepEqual(change.unmount, []);
});

test("re-entering the same route when the screen is NOT built still mounts it", () => {
  // The pair: treating same-route as always-noop would leave a blank app after
  // a crash recovery or an initial deep link.
  const change = transition(chat("c1"), chat("c1"), live());
  assert.equal(change.noop, false);
  assert.deepEqual(change.mount, ["chat"]);
});

test("a stale non-retained screen is cleaned up", () => {
  // `about` was left live by an earlier navigation and is not being returned
  // to. Leaving it in the DOM accumulates screens for the app's lifetime.
  const change = transition(chats, settings, live("chats", "about"));
  assert.ok(change.unmount.includes("about"));
  assert.ok(change.unmount.includes("chats"));
});

test("a stale RETAINED screen is hidden, not destroyed", () => {
  const change = transition(chats, settings, live("chats", "chat"));
  assert.ok(change.hide.includes("chat"), "chat is retained even when stale");
  assert.ok(!change.unmount.includes("chat"));
});

test("the target screen is never in unmount or hide", () => {
  // A dispatcher that hid what it was about to show would render a blank page,
  // and the bug would look like a routing failure rather than an ordering one.
  for (const [from, to, l] of [
    [chats, chat(), live("chats", "chat")],
    [settings, chats, live("settings", "chats")],
    [chat(), about, live("chat", "about")],
  ] as const) {
    const change = transition(from, to, l);
    assert.ok(!change.unmount.includes(change.show));
    assert.ok(!change.hide.includes(change.show));
  }
});

test("only the chat screen is retained", () => {
  // Retention is a cost: a retained screen holds its DOM for the app's
  // lifetime. It is worth it for a live transcript with scroll state, and not
  // for a settings form that should re-read its values.
  assert.deepEqual([...RETAINED], ["chat"]);
});
