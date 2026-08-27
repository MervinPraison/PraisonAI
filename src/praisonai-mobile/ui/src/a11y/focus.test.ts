/**
 * Focus policy.
 *
 * Both guarantees are about the same end state: focus must never be left on
 * `<body>`, where a screen reader reads nothing and the next Tab restarts from
 * the top of the document.
 *
 * The live bug is in app/src/dom.ts, which sets `b.disabled = !row.actionable`
 * on all three approval buttons the moment a decision goes in flight. The user
 * pressed one of them, so focus is on it, and disabling a focused element drops
 * focus with no event and no sound -- at the exact moment the row starts saying
 * "Sending your answer", which the user is now nowhere near.
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
  approvalButtonId,
  approvalGroupId,
  focusAfterDisable,
  focusForRoute,
  headingId,
  screenAnnouncement,
} from "./focus.ts";
import { en } from "../i18n/strings.ts";
import type { Route } from "../router.ts";

const chats: Route = { name: "chats" };
const chatA: Route = { name: "chat", chatId: "a" };
const chatB: Route = { name: "chat", chatId: "b" };
const settings: Route = { name: "settings" };

const GROUP = approvalGroupId("ap1");
const ALLOW = approvalButtonId("ap1", "allow");
const ALWAYS = approvalButtonId("ap1", "always");
const DENY = approvalButtonId("ap1", "deny");

test("disabling the focused button moves focus instead of dropping it", () => {
  // THE BUG, in the shape dom.ts produces it: all three go disabled at once,
  // so there is no sibling left and focus must land on the row.
  const target = focusAfterDisable({
    focusedId: ALLOW,
    disabledIds: [ALLOW, ALWAYS, DENY],
    enabledIds: [],
    containerId: GROUP,
  });
  assert.deepEqual(target, { kind: "element", id: GROUP });
  assert.notEqual(target.kind, "none", "a `none` here is focus on <body>");
});

test("a surviving sibling is preferred to the container", () => {
  // Less disorienting: the user stays inside the control group they were
  // operating rather than being bumped up a level.
  const target = focusAfterDisable({
    focusedId: ALLOW,
    disabledIds: [ALLOW],
    enabledIds: [ALWAYS, DENY],
    containerId: GROUP,
  });
  assert.deepEqual(target, { kind: "element", id: ALWAYS });
});

test("focus is NOT moved when the focused element is not the one being disabled", () => {
  // The pair to the first test. An implementation that always moved focus would
  // pass it, and would yank the caret out of the composer every time an
  // approval resolved in the background.
  assert.deepEqual(
    focusAfterDisable({
      focusedId: "composer",
      disabledIds: [ALLOW, ALWAYS, DENY],
      enabledIds: [],
      containerId: GROUP,
    }),
    { kind: "none" },
  );
  assert.deepEqual(
    focusAfterDisable({
      focusedId: null,
      disabledIds: [ALLOW],
      enabledIds: [ALWAYS],
      containerId: GROUP,
    }),
    { kind: "none" },
  );
});

test("the ids for two outstanding approvals never collide", () => {
  // Two concurrent tool calls is the normal case, not an exotic one, and the
  // whole approvals layer exists because binding by position authorises the
  // wrong command.
  assert.notEqual(approvalGroupId("ap1"), approvalGroupId("ap2"));
  assert.notEqual(approvalButtonId("ap1", "allow"), approvalButtonId("ap2", "allow"));
  assert.notEqual(approvalButtonId("ap1", "allow"), approvalButtonId("ap1", "deny"));
});

test("a route change moves focus to the new screen's heading", () => {
  // Swapping the DOM is not a navigation, so nothing moves focus on its own:
  // the reader keeps reading the screen the user left, or falls to <body> when
  // that node is removed. Tapping a chat is then completely silent.
  assert.deepEqual(focusForRoute(chats, chatA, "push"), { kind: "element", id: headingId(chatA) });
  assert.deepEqual(focusForRoute(null, chats, "replace"), { kind: "element", id: headingId(chats) });
  assert.deepEqual(focusForRoute(chatA, settings, "replace"), {
    kind: "element",
    id: headingId(settings),
  });
});

test("moving between two chats is a focus change, not a no-op", () => {
  // The heading id carries the chat id for exactly this: same route NAME,
  // different screen.
  assert.notEqual(headingId(chatA), headingId(chatB));
  assert.deepEqual(focusForRoute(chatA, chatB, "replace"), {
    kind: "element",
    id: headingId(chatB),
  });
});

test("a redundant push does NOT move focus", () => {
  // The pair. The router deliberately swallows a push of the route already on
  // top; moving focus anyway would yank the caret out of the composer -- and on
  // a streaming turn the view publishes several times a second.
  assert.deepEqual(focusForRoute(chatA, chatA, "push"), { kind: "none" });
  assert.deepEqual(focusForRoute(chats, chats, "replace"), { kind: "none" });
});

test("going back restores where the user was, with a fallback for a deleted row", () => {
  // Dumping the user at the top of a two-hundred-row list on every back gesture
  // is its own bug. Restoring to a node that no longer exists -- the chat they
  // just deleted -- silently focuses nothing, hence the fallback.
  assert.deepEqual(focusForRoute(chatA, chats, "pop"), {
    kind: "restore",
    fallbackId: headingId(chats),
  });
});

test("the screen change is announced, so it is not silent even if focus is quiet", () => {
  assert.equal(screenAnnouncement(en, chats), "Chats screen");
  assert.notEqual(screenAnnouncement(en, settings), screenAnnouncement(en, chats));
});
